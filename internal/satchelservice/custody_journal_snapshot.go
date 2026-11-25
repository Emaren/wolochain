package satchelservice

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"hash"

	bolt "go.etcd.io/bbolt"
)

const custodyJournalSnapshotMaxEncoded = 16 << 20

var errCustodyJournalSnapshot = errors.New("custody_journal_snapshot_unverifiable")

// CustodyJournalProofSnapshot contains exact public-policy and raw database
// journal bytes, including stored signed transaction bytes. It is sensitive
// financial evidence. It is neither a custody grant nor independent evidence of
// liabilities, bank balances, completeness, or reviewer independence. The v1
// journal framing excludes Bolt bucket sequence counters and physical metadata.
type CustodyJournalProofSnapshot struct {
	Version int    `json:"version"`
	Policy  Policy `json:"policy"`
	Frames  []byte `json:"frames"`
}

// journalFrameRecorder retains the existing scanner's exact framed byte stream.
// The domain prefix is written separately, so Frames contains only frames.
type journalFrameRecorder struct {
	hash.Hash
	frames []byte
}

func (r *journalFrameRecorder) Write(p []byte) (int, error) {
	r.frames = append(r.frames, p...)
	return r.Hash.Write(p)
}

// CustodyJournalSnapshot exports one validated, read-only, bounded Bolt view
// while holding the execution mutex. It does not sign, transmit, or write.
func (e *Engine) CustodyJournalSnapshot() ([]byte, error) {
	if e == nil || !e.mu.TryLock() {
		return nil, errCustodyJournalSnapshot
	}
	defer e.mu.Unlock()
	if e.db == nil || e.backend == nil {
		return nil, errCustodyJournalSnapshot
	}
	var encoded []byte
	err := e.db.View(func(tx *bolt.Tx) error {
		journal, err := e.custodyJournalTx(tx)
		if err != nil {
			return err
		}
		h := sha256.New()
		h.Write([]byte("aoe2war/satchel/execution-journal/v1\x00"))
		recorder := &journalFrameRecorder{Hash: h}
		scan := custodyJournalScan{hash: recorder}
		if err := tx.ForEach(func(name []byte, b *bolt.Bucket) error { return scan.bucket(name, b, 0) }); err != nil {
			return err
		}
		if hex.EncodeToString(h.Sum(nil)) != journal.JournalDigest {
			return errCustodyJournalSnapshot
		}
		encoded, err = json.Marshal(CustodyJournalProofSnapshot{Version: 1, Policy: e.policy, Frames: recorder.frames})
		if err != nil {
			return err
		}
		if len(encoded) > custodyJournalSnapshotMaxEncoded {
			return errors.New("custody_journal_resource_limit")
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return encoded, nil
}

// VerifyCustodyJournalSnapshot checks canonical framing and digest equality
// against separately supplied expectations. The caller must authenticate those
// expectations through a genuine dual-signed reserve review and its policy
// binding. Matching attacker-selected expectations proves nothing independent.
// This function does not revalidate SDK signatures or issue runtime authority.
func VerifyCustodyJournalSnapshot(encoded []byte, expectedPolicyDigest, expectedJournalDigest string) (CustodyJournalProofSnapshot, error) {
	var out CustodyJournalProofSnapshot
	fail := func() (CustodyJournalProofSnapshot, error) {
		return CustodyJournalProofSnapshot{}, errCustodyJournalSnapshot
	}
	if len(encoded) == 0 || len(encoded) > custodyJournalSnapshotMaxEncoded || !nonzeroDigest(expectedPolicyDigest) || !nonzeroDigest(expectedJournalDigest) {
		return fail()
	}
	if json.Unmarshal(encoded, &out) != nil || out.Version != 1 || len(out.Frames) == 0 || len(out.Frames) > custodyJournalMaxBytes || hashJSON(out.Policy) != expectedPolicyDigest {
		return fail()
	}
	canonical, err := json.Marshal(out)
	if err != nil || !bytes.Equal(encoded, canonical) {
		return fail()
	}
	h := sha256.New()
	h.Write([]byte("aoe2war/satchel/execution-journal/v1\x00"))
	parser := journalSnapshotParser{remaining: out.Frames, scan: custodyJournalScan{hash: h}}
	var previous []byte
	var buckets int
	for len(parser.remaining) > 0 {
		kind, key, value, err := parser.next()
		if err != nil || kind != 'B' || len(key) == 0 || (previous != nil && bytes.Compare(previous, key) >= 0) || len(value) != 0 {
			return fail()
		}
		previous = key
		buckets++
		if err := parser.bucket(0); err != nil {
			return fail()
		}
	}
	if buckets == 0 || hex.EncodeToString(h.Sum(nil)) != expectedJournalDigest {
		return fail()
	}
	return out, nil
}

type journalSnapshotParser struct {
	remaining []byte
	scan      custodyJournalScan
}

func (p *journalSnapshotParser) next() (byte, []byte, []byte, error) {
	if len(p.remaining) < 17 {
		return 0, nil, nil, errCustodyJournalSnapshot
	}
	header := p.remaining[:17]
	keySize, valueSize := binary.BigEndian.Uint64(header[1:9]), binary.BigEndian.Uint64(header[9:17])
	data := p.remaining[17:]
	if keySize > uint64(len(data)) || valueSize > uint64(len(data))-keySize {
		return 0, nil, nil, errCustodyJournalSnapshot
	}
	key, value := data[:int(keySize)], data[int(keySize):int(keySize+valueSize)]
	if err := p.scan.frame(header[0], key, value); err != nil {
		return 0, nil, nil, err
	}
	p.remaining = data[int(keySize+valueSize):]
	return header[0], key, value, nil
}

func (p *journalSnapshotParser) bucket(depth int) error {
	if depth > custodyJournalMaxDepth {
		return errCustodyJournalSnapshot
	}
	var previous []byte
	for {
		kind, key, value, err := p.next()
		if err != nil {
			return err
		}
		if kind == 'E' {
			if len(key) != 0 || len(value) != 0 {
				return errCustodyJournalSnapshot
			}
			return nil
		}
		if len(key) == 0 || (previous != nil && bytes.Compare(previous, key) >= 0) {
			return errCustodyJournalSnapshot
		}
		previous = key
		switch kind {
		case 'B':
			if len(value) != 0 {
				return errCustodyJournalSnapshot
			}
			if err := p.bucket(depth + 1); err != nil {
				return err
			}
		case 'V':
		default:
			return errCustodyJournalSnapshot
		}
	}
}
