package epochescrow

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	bolt "go.etcd.io/bbolt"
)

const journalByteLimit = 8 << 20

const PreparedUnsigned = "PREPARED_UNSIGNED"
const UnknownNoReplay = "UNKNOWN_NO_REPLAY"

var records = []byte("epoch-v3-decisions")
var economic = []byte("epoch-v3-entitlements")
var nonces = []byte("epoch-v3-nonces")
var events = []byte("epoch-v3-append-only-events")
var metadata = []byte("epoch-v3-policy")

type Decision struct {
	OperationID string  `json:"operation_id"`
	Fingerprint string  `json:"fingerprint"`
	Status      string  `json:"status"`
	Request     Request `json:"request"`
	Reason      string  `json:"reason"`
}
type transition struct {
	Sequence                                                         uint64
	OperationID, Fingerprint, Status, Reason, PreviousSHA256, SHA256 string
}
type Journal struct {
	db     *bolt.DB
	policy Policy
	now    func() time.Time
}

// OpenJournal reuses the service's bbolt durability model: private existing
// parent, exclusive lock, synchronous commits and directory fsync. An empty or
// restored journal never grants signing authority; an independent off-host
// reservation/checkpoint is still missing. No migration or reset API exists.
func OpenJournal(path string, p Policy) (*Journal, error) {
	if e := p.Validate(); e != nil {
		return nil, e
	}
	refuse := func() (*Journal, error) { return nil, errors.New("epoch_private_journal_required") }
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return refuse()
	}
	parent := filepath.Dir(path)
	real, e := filepath.EvalSymlinks(parent)
	if e != nil || real != parent {
		return refuse()
	}
	st, e := os.Lstat(parent)
	if e != nil || !st.IsDir() || st.Mode().Perm() != 0700 {
		return refuse()
	}
	owner, ok := st.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != uint32(os.Geteuid()) {
		return refuse()
	}
	if st, e := os.Lstat(path); e == nil {
		owner, ok := st.Sys().(*syscall.Stat_t)
		if !ok || owner.Uid != uint32(os.Geteuid()) || owner.Nlink != 1 || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Size() > 1<<30 {
			return refuse()
		}
	} else if !os.IsNotExist(e) {
		return refuse()
	}
	dir, e := os.Open(parent)
	if e != nil {
		return refuse()
	}
	defer dir.Close()
	db, e := bolt.Open(path, 0600, &bolt.Options{Timeout: time.Second, NoGrowSync: false})
	if e != nil {
		return nil, e
	}
	if e = dir.Sync(); e != nil {
		db.Close()
		return nil, e
	}
	e = db.Update(func(tx *bolt.Tx) error {
		names := [][]byte{metadata, records, economic, nonces, events}
		if m := tx.Bucket(metadata); m != nil {
			if string(m.Get([]byte("policy"))) != PolicyDigest(p) {
				return errors.New("epoch_journal_policy_conflict")
			}
			for _, name := range names {
				if tx.Bucket(name) == nil {
					return errors.New("epoch_journal_corrupt")
				}
			}
			return nil
		}
		// Never repair a legacy or partially missing journal into a fresh namespace.
		existing := false
		_ = tx.ForEach(func(_ []byte, _ *bolt.Bucket) error { existing = true; return nil })
		if existing {
			return errors.New("epoch_journal_corrupt")
		}
		for _, name := range names {
			if _, err := tx.CreateBucket(name); err != nil {
				return err
			}
		}
		return tx.Bucket(metadata).Put([]byte("policy"), []byte(PolicyDigest(p)))
	})
	if e != nil {
		db.Close()
		return nil, e
	}
	encoded, _ := json.Marshal(p)
	var frozen Policy
	_ = json.Unmarshal(encoded, &frozen)
	j := &Journal{db, frozen, time.Now}
	if e = j.db.View(j.verifyHistory); e != nil {
		db.Close()
		return nil, e
	}
	return j, nil
}
func (j *Journal) Close() error { return j.db.Close() }
func freezeRequest(r Request) Request {
	b, _ := json.Marshal(r)
	var copy Request
	_ = json.Unmarshal(b, &copy)
	return copy
}
func readDecision(tx *bolt.Tx, id string) (Decision, error) {
	var d Decision
	b := tx.Bucket(records).Get([]byte(id))
	if b == nil {
		return d, errors.New("epoch_operation_not_found")
	}
	if json.Unmarshal(b, &d) != nil || d.OperationID != id || d.Request.OperationID != id || d.Fingerprint != Fingerprint(d.Request) || (d.Status != PreparedUnsigned && d.Status != UnknownNoReplay) {
		return Decision{}, errors.New("epoch_journal_corrupt")
	}
	return d, nil
}
func appendTransition(tx *bolt.Tx, d Decision) error {
	b := tx.Bucket(events)
	sequence, e := b.NextSequence()
	if e != nil {
		return e
	}
	if sequence > 100000 {
		return errors.New("epoch_journal_capacity_hold")
	}
	previous := string(tx.Bucket(metadata).Get([]byte("last_event")))
	event := transition{Sequence: sequence, OperationID: d.OperationID, Fingerprint: d.Fingerprint, Status: d.Status, Reason: d.Reason, PreviousSHA256: previous}
	event.SHA256 = hash(event)
	data, _ := json.Marshal(event)
	var key [8]byte
	binary.BigEndian.PutUint64(key[:], sequence)
	if b.Get(key[:]) != nil {
		return errors.New("epoch_journal_event_collision")
	}
	if e := b.Put(key[:], data); e != nil {
		return e
	}
	return tx.Bucket(metadata).Put([]byte("last_event"), []byte(event.SHA256))
}

// Prepare retains one immutable native-verified decision. Local nonce and
// entitlement indexes prevent duplicates but are NOT the off-host signing
// nonce authority. Expiry, timeout and restart never free these indexes.
func (j *Journal) Prepare(ctx context.Context, v VerifiedPreparation) (Decision, error) {
	if ctx == nil || ctx.Err() != nil || !v.verified || v.fingerprint != Fingerprint(v.request) || PolicyDigest(v.policy) != PolicyDigest(j.policy) || !j.now().Before(v.expiresAt) {
		return Decision{}, errors.New("epoch_native_preparation_required")
	}
	if e := j.policy.ValidateRequest(v.request, j.now()); e != nil {
		return Decision{}, e
	}
	var out Decision
	e := j.db.Update(func(tx *bolt.Tx) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if e := j.verifyHistory(tx); e != nil {
			return e
		}
		// Waiting for another writer and scanning prior history cannot extend the
		// native proof or transaction-specific approval's admission lifetime.
		if !j.now().Before(v.expiresAt) {
			return errors.New("epoch_native_preparation_expired")
		}
		if e := j.policy.ValidateRequest(v.request, j.now()); e != nil {
			return e
		}
		if tx.Bucket(records).Get([]byte(v.request.OperationID)) != nil {
			var e error
			out, e = readDecision(tx, v.request.OperationID)
			if e != nil {
				return e
			}
			if out.Fingerprint != v.fingerprint {
				return errors.New("epoch_operation_fingerprint_conflict")
			}
			return nil
		}
		key := v.request.EntitlementID + ":" + v.request.Command
		for _, check := range []struct {
			bucket []byte
			key    string
		}{{economic, key}, {nonces, v.request.Nonce}} {
			if tx.Bucket(check.bucket).Get([]byte(check.key)) != nil {
				return errors.New("epoch_economic_identity_already_consumed")
			}
		}
		// Complete original-ticket partitions share one physical receipt across
		// markets while preserving immutable ownership and allocation identities.
		pins := preparationPins(j.policy, v.request)
		for key, value := range pins {
			if old := tx.Bucket(metadata).Get([]byte(key)); old != nil && string(old) != value {
				return blocked("RETURN_ENTITLEMENT_COLLISION", "Market resolution or original physical funding was already bound to another immutable plan.", "review-original-ticket-partition")
			}
		}
		for key, value := range pins {
			if e := tx.Bucket(metadata).Put([]byte(key), []byte(value)); e != nil {
				return e
			}
		}
		if tx.Bucket(records).Stats().KeyN >= 100000 {
			return errors.New("epoch_journal_capacity_hold")
		}
		out = Decision{v.request.OperationID, v.fingerprint, PreparedUnsigned, freezeRequest(v.request), "native_verified_unsigned"}
		data, _ := json.Marshal(out)
		if e := tx.Bucket(records).Put([]byte(out.OperationID), data); e != nil {
			return e
		}
		if e := tx.Bucket(economic).Put([]byte(key), []byte(out.OperationID)); e != nil {
			return e
		}
		if e := tx.Bucket(nonces).Put([]byte(v.request.Nonce), []byte(out.OperationID)); e != nil {
			return e
		}
		if err := appendTransition(tx, out); err != nil {
			return err
		}
		if err := j.verifyHistory(tx); err != nil {
			return err
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if !j.now().Before(v.expiresAt) {
			return errors.New("epoch_native_preparation_expired")
		}
		return j.policy.ValidateRequest(v.request, j.now())
	})
	return out, e
}

// Lookup is fingerprint-bound and never signs, broadcasts or changes a record.
func (j *Journal) Lookup(id, fingerprint string) (Decision, error) {
	var d Decision
	e := j.db.View(func(tx *bolt.Tx) error {
		if e := j.verifyHistory(tx); e != nil {
			return e
		}
		var e error
		d, e = readDecision(tx, id)
		if e == nil && d.Fingerprint != fingerprint {
			return errors.New("epoch_operation_fingerprint_conflict")
		}
		return e
	})
	return d, e
}

// Quarantine preserves an uncertain external attempt as a permanent no-replay
// decision. It cannot turn an unsigned decision into permission to transmit.
func (j *Journal) Quarantine(id, fingerprint string) (Decision, error) {
	var d Decision
	e := j.db.Update(func(tx *bolt.Tx) error {
		if e := j.verifyHistory(tx); e != nil {
			return e
		}
		var e error
		d, e = readDecision(tx, id)
		if e != nil {
			return e
		}
		if d.Fingerprint != fingerprint {
			return errors.New("epoch_operation_fingerprint_conflict")
		}
		if d.Status == UnknownNoReplay {
			return nil
		}
		d.Status = UnknownNoReplay
		d.Reason = "UNCERTAIN_BROADCAST"
		data, _ := json.Marshal(d)
		if e := tx.Bucket(records).Put([]byte(id), data); e != nil {
			return e
		}
		if err := appendTransition(tx, d); err != nil {
			return err
		}
		return j.verifyHistory(tx)
	})
	return d, e
}

// Execute is intentionally a hard unavailable gate. ProductionEnabled is a
// compile-time false constant, not an operator-editable config switch. Until
// actual independent authority and off-host nonce enrollment are implemented,
// no existing SDK/keyring backend is opened or called from this package.
func (j *Journal) Execute(ctx context.Context, id, fingerprint string) (Decision, error) {
	d, e := j.Lookup(id, fingerprint)
	if e != nil {
		return d, e
	}
	if d.Status == UnknownNoReplay {
		return d, blocked("UNCERTAIN_BROADCAST", "An uncertain economic decision cannot be retransmitted.", "observe-original-physical-effect")
	}
	if ctx == nil || ctx.Err() != nil {
		return d, errors.New("epoch_context_unavailable")
	}
	return d, UnavailableExecution()
}

// verifyHistory checks every append-only transition and its latest immutable
// decision/indexes. This is local tamper detection, not an off-host checkpoint
// or protection against an attacker restoring a complete older database.
func (j *Journal) verifyHistory(tx *bolt.Tx) error {
	refuse := func() error { return errors.New("epoch_journal_corrupt") }
	if string(tx.Bucket(metadata).Get([]byte("policy"))) != PolicyDigest(j.policy) {
		return refuse()
	}
	last := map[string]transition{}
	previous := ""
	var sequence uint64
	budget := journalByteLimit
	if e := tx.Bucket(events).ForEach(func(k, v []byte) error {
		budget -= len(k) + len(v)
		if budget < 0 {
			return errors.New("epoch_journal_capacity_hold")
		}
		if len(k) != 8 || v == nil {
			return refuse()
		}
		sequence++
		if binary.BigEndian.Uint64(k) != sequence {
			return refuse()
		}
		var event transition
		if json.Unmarshal(v, &event) != nil || event.Sequence != sequence || event.PreviousSHA256 != previous {
			return refuse()
		}
		actual := event.SHA256
		event.SHA256 = ""
		if !digest(actual) || actual != hash(event) {
			return refuse()
		}
		event.SHA256 = actual
		old, exists := last[event.OperationID]
		if (!exists && event.Status != PreparedUnsigned) || (exists && (old.Status != PreparedUnsigned || event.Status != UnknownNoReplay || old.Fingerprint != event.Fingerprint)) {
			return refuse()
		}
		last[event.OperationID] = event
		previous = actual
		return nil
	}); e != nil {
		return e
	}
	if tx.Bucket(events).Sequence() != sequence || string(tx.Bucket(metadata).Get([]byte("last_event"))) != previous || len(last) != bucketCount(tx.Bucket(records)) {
		return refuse()
	}
	if bucketCount(tx.Bucket(economic)) != len(last) || bucketCount(tx.Bucket(nonces)) != len(last) {
		return refuse()
	}
	var futureEvents uint64
	err := tx.Bucket(records).ForEach(func(id, value []byte) error {
		budget -= len(id) + len(value)
		if budget < 0 {
			return errors.New("epoch_journal_capacity_hold")
		}
		if value == nil {
			return refuse()
		}
		d, e := readDecision(tx, string(id))
		if e != nil {
			return e
		}
		event, ok := last[string(id)]
		if !ok || event.Fingerprint != d.Fingerprint || event.Status != d.Status || event.Reason != d.Reason || j.policy.ValidateRequest(d.Request, time.Unix(d.Request.IssuedAt, 0)) != nil {
			return refuse()
		}
		if string(tx.Bucket(economic).Get([]byte(d.Request.EntitlementID+":"+d.Request.Command))) != d.OperationID || string(tx.Bucket(nonces).Get([]byte(d.Request.Nonce))) != d.OperationID {
			return refuse()
		}
		for key, value := range preparationPins(j.policy, d.Request) {
			if string(tx.Bucket(metadata).Get([]byte(key))) != value {
				return refuse()
			}
		}
		if d.Status == PreparedUnsigned {
			futureEvents++
			// Reserve the exact replacement-record growth and an upper bound for one
			// future uncertainty event. Filling normal admission capacity can never
			// prevent retaining a later UNKNOWN_NO_REPLAY decision.
			unknown := d
			unknown.Status = UnknownNoReplay
			unknown.Reason = "UNCERTAIN_BROADCAST"
			encoded, _ := json.Marshal(unknown)
			growth := len(encoded) - len(value)
			if growth < 0 {
				growth = 0
			}
			event := transition{Sequence: 100000, OperationID: d.OperationID, Fingerprint: d.Fingerprint, Status: unknown.Status, Reason: unknown.Reason, PreviousSHA256: strings.Repeat("f", 64), SHA256: strings.Repeat("f", 64)}
			encoded, _ = json.Marshal(event)
			budget -= growth + 8 + len(encoded)
		}
		return nil
	})
	if err != nil {
		return err
	}
	if budget < 0 || sequence+futureEvents > 100000 {
		return errors.New("epoch_journal_capacity_hold")
	}
	return nil
}

func bucketCount(b *bolt.Bucket) int {
	n := 0
	_ = b.ForEach(func(k, v []byte) error { n++; return nil })
	return n
}
