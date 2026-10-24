// Package satchelservice implements a separately installed, private custody
// boundary. It does not grant the app credit authority or certify C2 custody.
package satchelservice

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/cosmos/btcutil/bech32"
	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

type TransferRequest struct {
	OperationID  string                  `json:"operation_id"`
	ChainID      string                  `json:"chain_id"`
	Denom        string                  `json:"denom"`
	Sender       string                  `json:"sender"`
	Recipient    string                  `json:"recipient"`
	AmountUWolo  string                  `json:"amount_uwolo"`
	Memo         string                  `json:"memo"`
	Kind         string                  `json:"kind"`
	OwnerID      string                  `json:"owner_id,omitempty"`
	Approval     *WithdrawalApproval     `json:"approval,omitempty"`
	OwnerMandate *OwnerWithdrawalMandate `json:"owner_mandate,omitempty"`
	Reservation  *WagerReservation       `json:"reservation,omitempty"`
}
type WithdrawalApproval struct {
	WithdrawalID      string `json:"withdrawal_id"`
	ChallengeID       string `json:"challenge_id"`
	OwnerID           string `json:"owner_id"`
	Recipient         string `json:"recipient"`
	AmountUWolo       string `json:"amount_uwolo"`
	Memo              string `json:"memo"`
	HoldDigest        string `json:"hold_digest"`
	ReservationDigest string `json:"reservation_digest"`
	IssuedAt          int64  `json:"issued_at"`
	ExpiresAt         int64  `json:"expires_at"`
	Signature         string `json:"signature"`
}
type SignedTransaction struct {
	Bytes                   []byte
	Hash                    string
	AccountNumber, Sequence uint64
}
type BroadcastResult struct {
	Status string
	Code   uint32
}
type Confirmation struct {
	Status, ReceiptID, BlockHash string
	Height                       int64
}
type Backend interface {
	Sign(context.Context, TransferRequest) (SignedTransaction, error)
	ValidateSigned(TransferRequest, SignedTransaction) error
	Broadcast(context.Context, SignedTransaction) (BroadcastResult, error)
	Confirm(context.Context, TransferRequest, SignedTransaction) (Confirmation, error)
}
type Result struct {
	OperationID   string `json:"operation_id"`
	Status        string `json:"status"`
	TxHash        string `json:"tx_hash,omitempty"`
	Reason        string `json:"reason,omitempty"`
	DurableFenced bool   `json:"durable_request_fenced"`
}
type Policy struct {
	Vault                 string   `json:"vault"`
	BettingEscrow         string   `json:"betting_escrow"`
	ProtectedAddresses    []string `json:"protected_addresses"`
	MaxAmountUWolo        uint64   `json:"max_amount_uwolo"`
	WithdrawalApprovalKey []byte   `json:"withdrawal_approval_key"`
	WagerApprovalKey      []byte   `json:"wager_approval_key"`
}
type record struct {
	Request      TransferRequest
	Fingerprint  string
	Result       Result
	Signed       SignedTransaction
	Confirmation Confirmation
}
type Engine struct {
	mu               sync.Mutex
	db               *bolt.DB
	policy           Policy
	backend          Backend
	now              func() time.Time
	custodyAuthority *CustodyAuthority
}

var operations = []byte("operations-v1")
var meta = []byte("custody-v1")
var effects = []byte("consumed-effects-v1")
var ids = regexp.MustCompile(`^[a-zA-Z0-9:_-]{1,128}$`)
var wagerIDs = regexp.MustCompile(`^satchel:ticket:[1-9][0-9]{0,11}$`)
var ticketMemo = regexp.MustCompile(`^AoE2HDBets bet ticket v1 · ticket [1-9][0-9]{0,11}$`)
var uuid = regexp.MustCompile(`^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$`)
var digestRE = regexp.MustCompile(`^[a-fA-F0-9]{64}$`)

func validAddress(s string) bool {
	if s != strings.ToLower(s) {
		return false
	}
	h, w, e := bech32.Decode(s, 90)
	if e != nil || h != "wolo" {
		return false
	}
	b, e := bech32.ConvertBits(w, 5, 8, false)
	return e == nil && len(b) == 20
}
func amount(s string, max uint64) bool {
	if len(s) == 0 || len(s) > 15 || s[0] < '1' || s[0] > '9' {
		return false
	}
	var n uint64
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
		n = n*10 + uint64(c-'0')
	}
	return n > 0 && n <= max
}
func hashJSON(v any) string {
	b, _ := json.Marshal(v)
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}
func fingerprint(r TransferRequest) string {
	// Approval renewal cannot change an economic operation's identity. The
	// original accepted approval is retained durably, never replaced by a retry.
	fields := []string{"satchel-operation-v1", r.OperationID, r.Kind, r.ChainID, r.Denom, r.Sender, r.Recipient, r.AmountUWolo, r.Memo, r.OwnerID}
	if r.OwnerMandate != nil {
		fields = append(fields, OwnerMandateDigest(*r.OwnerMandate))
	}
	if r.Reservation != nil {
		fields = append(fields, "wager-reservation-v1", hashJSON(r.Reservation))
	}
	return hashJSON(fields)
}

// ApprovalMessage is a domain-separated, ordered JSON array, not a client
// boolean. Its key must belong to the independent withdrawal approval boundary.
func ApprovalMessage(a WithdrawalApproval, vault string) []byte {
	b, _ := json.Marshal([]any{"aoe2war/satchel/withdraw-approval/v1", "wolo-1", "uwolo", vault, a.WithdrawalID, a.ChallengeID, a.OwnerID, a.Recipient, a.AmountUWolo, a.Memo, a.HoldDigest, a.IssuedAt, a.ExpiresAt})
	return b
}
func (p Policy) VerifyWithdrawal(r TransferRequest) error { return p.verifyWithdrawal(r, time.Now()) }
func (p Policy) verifyWithdrawal(r TransferRequest, now time.Time) error {
	a := r.Approval
	if a == nil || len(p.WithdrawalApprovalKey) != ed25519.PublicKeySize || !uuid.MatchString(a.WithdrawalID) || !uuid.MatchString(a.ChallengeID) ||
		r.OperationID != "satchel:withdrawal:"+a.WithdrawalID || a.OwnerID == "" || len(a.OwnerID) > 128 || r.OwnerID != a.OwnerID || r.Recipient != a.Recipient || r.AmountUWolo != a.AmountUWolo || r.Memo != a.Memo ||
		a.Memo != "aoe2war/satchel/withdraw/v1/"+a.WithdrawalID || !nonzeroDigest(a.HoldDigest) || a.IssuedAt > now.Unix() || a.ExpiresAt <= now.Unix() || a.ExpiresAt <= a.IssuedAt || uint64(a.ExpiresAt)-uint64(a.IssuedAt) > 300 {
		return errors.New("withdrawal_approval_invalid")
	}
	sig, e := base64.StdEncoding.Strict().DecodeString(a.Signature)
	if e != nil || len(sig) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(sig) != a.Signature || !ed25519.Verify(p.WithdrawalApprovalKey, ApprovalMessage(*a, p.Vault), sig) {
		return errors.New("withdrawal_approval_invalid")
	}
	return verifyOwnerWithdrawal(r, now)
}

// Exact owner product ceiling. A lower configured backend/signer policy remains
// binding; a higher withdrawal allowance never raises the wager maximum.
const maxWarSatchelWagerUWolo uint64 = ProductMaxWagerUWolo

func (p Policy) validate(r TransferRequest, now time.Time) error {
	if !ids.MatchString(r.OperationID) || r.ChainID != "wolo-1" || r.Denom != "uwolo" || r.Sender != p.Vault || !validAddress(r.Recipient) || r.Recipient == p.Vault || !amount(r.AmountUWolo, p.MaxAmountUWolo) {
		return errors.New("transfer_policy_refused")
	}
	switch r.Kind {
	case "wager":
		// Ticket memo is server issued; bind its whole exact bytes to this durable
		// request. App admission/owner/game caps remain the HD ledger's authority.
		n, _ := strconv.ParseUint(r.AmountUWolo, 10, 64)
		if n > maxWarSatchelWagerUWolo || n%1000000 != 0 || !wagerIDs.MatchString(r.OperationID) || r.Recipient != p.BettingEscrow || r.Approval != nil || r.OwnerMandate != nil || (r.OwnerID != "" && !ownerUIDPattern.MatchString(r.OwnerID)) || !ticketMemo.MatchString(r.Memo) {
			return errors.New("wager_policy_refused")
		}
		return p.verifyWager(r, now)
	case "withdrawal":
		if r.Reservation != nil {
			return errors.New("withdrawal_authority_conflict")
		}
		if satchel.IsKnownRoleAddress(r.Recipient) {
			return errors.New("withdrawal_destination_refused")
		}
		for _, a := range p.ProtectedAddresses {
			if r.Recipient == a {
				return errors.New("withdrawal_destination_refused")
			}
		}
		return p.verifyWithdrawal(r, now)
	default:
		return errors.New("operation_kind_refused")
	}
}
func validMemo(s string) bool {
	for _, c := range s {
		if c < 32 || c > 126 {
			return false
		}
	}
	return true
}

// Open requires an existing private directory. Bolt's exclusive file lock
// prevents two signer processes sharing this history. No state auto-reset or
// pruning API exists: restoring an old DB can resurrect spending authority.
func Open(path string, p Policy, b Backend) (*Engine, error) {
	if b == nil || (len(p.WithdrawalApprovalKey) == ed25519.PublicKeySize && len(p.WagerApprovalKey) == ed25519.PublicKeySize && bytes.Equal(p.WithdrawalApprovalKey, p.WagerApprovalKey)) || !validAddress(p.Vault) || satchel.IsKnownRoleAddress(p.Vault) || !validAddress(p.BettingEscrow) || p.Vault == p.BettingEscrow || p.MaxAmountUWolo == 0 || p.MaxAmountUWolo > 50000000000 {
		return nil, errors.New("invalid_custody_policy")
	}
	for _, a := range p.ProtectedAddresses {
		if !validAddress(a) || a == p.Vault {
			return nil, errors.New("signer_role_collision")
		}
	}
	// At least the configured escrow must also be explicitly inventoried. The
	// built-in complete registered-role catalog is always excluded independently.
	found := false
	for _, a := range p.ProtectedAddresses {
		found = found || a == p.BettingEscrow
	}
	if !found {
		return nil, errors.New("protected_inventory_missing")
	}
	if !filepath.IsAbs(path) {
		return nil, errors.New("private_state_path_required")
	}
	dir := filepath.Dir(path)
	st, e := os.Lstat(dir)
	if e != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm() != 0700 {
		return nil, errors.New("private_state_directory_required")
	}
	if real, e := filepath.EvalSymlinks(dir); e != nil || real != dir {
		return nil, errors.New("state_symlink_refused")
	}
	if st, e := os.Lstat(path); e == nil && (!st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Size() > 1<<30) {
		return nil, errors.New("unsafe_state_file")
	} else if e != nil && !os.IsNotExist(e) {
		return nil, errors.New("state_unavailable")
	}
	parent, e := os.Open(dir)
	if e != nil {
		return nil, errors.New("state_unavailable")
	}
	defer parent.Close()
	db, e := bolt.Open(path, 0600, &bolt.Options{Timeout: time.Second, NoGrowSync: false})
	if e != nil {
		return nil, errors.New("state_unavailable")
	}
	if e = parent.Sync(); e != nil {
		db.Close()
		return nil, errors.New("state_directory_sync_failed")
	}
	p.ProtectedAddresses = append([]string(nil), p.ProtectedAddresses...)
	p.WithdrawalApprovalKey = append([]byte(nil), p.WithdrawalApprovalKey...)
	p.WagerApprovalKey = append([]byte(nil), p.WagerApprovalKey...)
	e = db.Update(func(tx *bolt.Tx) error {
		m, e := tx.CreateBucketIfNotExists(meta)
		if e != nil {
			return e
		}
		for _, n := range [][]byte{operations, effects} {
			if _, e = tx.CreateBucketIfNotExists(n); e != nil {
				return e
			}
		}
		h := hashJSON(p)
		old := m.Get([]byte("policy"))
		if old != nil && string(old) != h {
			return errors.New("persisted_policy_conflict")
		}
		return m.Put([]byte("policy"), []byte(h))
	})
	if e != nil {
		db.Close()
		return nil, e
	}
	return &Engine{db: db, policy: p, backend: b, now: time.Now}, nil
}
func (e *Engine) Close() error { e.mu.Lock(); defer e.mu.Unlock(); return e.db.Close() }
func load(tx *bolt.Tx, id string) (record, error) {
	var r record
	b := tx.Bucket(operations).Get([]byte(id))
	if b == nil {
		return r, errors.New("operation_not_found")
	}
	if json.Unmarshal(b, &r) != nil {
		return r, errors.New("state_corrupt")
	}
	if r.Request.OperationID != id || r.Fingerprint != fingerprint(r.Request) || r.Result.OperationID != id || !r.Result.DurableFenced {
		return r, errors.New("state_corrupt")
	}
	switch r.Result.Status {
	case "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING", "CONFIRMED", "FAILED", "REFUSED":
	default:
		return r, errors.New("state_corrupt")
	}
	if len(r.Signed.Bytes) > 0 {
		sum := sha256.Sum256(r.Signed.Bytes)
		if len(r.Signed.Bytes) > 65536 || !strings.EqualFold(hex.EncodeToString(sum[:]), r.Signed.Hash) || r.Result.TxHash != r.Signed.Hash {
			return r, errors.New("state_corrupt")
		}
	} else if r.Result.TxHash != "" || (r.Result.Status != "UNKNOWN" && r.Result.Status != "REFUSED") {
		return r, errors.New("state_corrupt")
	}
	if r.Result.Status == "CONFIRMED" || r.Result.Status == "FAILED" {
		if r.Confirmation.Status != r.Result.Status || !validConfirmation(r.Signed, r.Confirmation) {
			return r, errors.New("state_corrupt")
		}
	}
	return r, nil
}
func validConfirmation(s SignedTransaction, c Confirmation) bool {
	return c.Height > 0 && digestRE.MatchString(c.BlockHash) && (c.ReceiptID == "wolo-1:"+s.Hash+":0" || c.ReceiptID == "wolo-1:"+s.Hash+":1")
}
func save(tx *bolt.Tx, r record) error {
	b, err := json.Marshal(r)
	if err != nil {
		return err
	}
	return tx.Bucket(operations).Put([]byte(r.Request.OperationID), b)
}
func (e *Engine) Lookup(id string) (Result, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	var r record
	err := e.db.View(func(tx *bolt.Tx) error { var err error; r, err = load(tx, id); return err })
	return r.Result, err
}
func (e *Engine) write(r record) error {
	return e.db.Update(func(tx *bolt.Tx) error { return save(tx, r) })
}
func held(r record, reason string) record {
	r.Result.Status = "UNKNOWN"
	r.Result.Reason = reason
	return r
}

func (e *Engine) Submit(ctx context.Context, req TransferRequest) (Result, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	// Keep accepted authority independent of mutable pointers retained by an
	// in-process caller. The original approvals stay bound to this journal.
	if req.Approval != nil {
		v := *req.Approval
		req.Approval = &v
	}
	if req.OwnerMandate != nil {
		v := *req.OwnerMandate
		req.OwnerMandate = &v
	}
	if req.Reservation != nil {
		v := *req.Reservation
		req.Reservation = &v
	}
	var grant *custodyExecutionGrant
	if e.custodyAuthority != nil {
		// Qualify only a new identity. Existing accepted/uncertain operations
		// remain replayable as observations after revocation, never as sends.
		var recorded bool
		if err := e.db.View(func(tx *bolt.Tx) error {
			recorded = tx.Bucket(operations).Get([]byte(req.OperationID)) != nil
			return nil
		}); err != nil {
			return Result{}, errCustodyUnavailable
		}
		if !recorded {
			var err error
			grant, err = e.custodyAuthority.qualifyLocked(ctx)
			if err != nil || !grant.covers(req) {
				return Result{}, errCustodyUnavailable
			}
			grant.operationFingerprint = fingerprint(req)
			ctx = context.WithValue(ctx, custodyGrantContextKey{}, grant)
			var cancel context.CancelFunc
			ctx, cancel = context.WithDeadline(ctx, grant.expiresAt)
			defer cancel()
		}
	}
	// Economic identity check precedes approval freshness: replay of an already
	// fenced request still works after its original short-lived approval expires.
	var r record
	var exists bool
	err := e.db.Update(func(tx *bolt.Tx) error {
		old := tx.Bucket(operations).Get([]byte(req.OperationID))
		if old != nil {
			var err error
			r, err = load(tx, req.OperationID)
			if err != nil {
				return err
			}
			if r.Fingerprint != fingerprint(req) {
				return errors.New("operation_id_conflict")
			}
			exists = true
			return nil
		}
		if grant != nil && !grant.current(ctx) {
			return errCustodyUnavailable
		}
		if err := e.policy.validate(req, e.now()); err != nil {
			return err
		}
		if req.Kind == "wager" {
			key := []byte("wager-memo:" + req.Memo)
			if tx.Bucket(meta).Get(key) != nil {
				return errors.New("ticket_memo_already_fenced")
			}
			if err := tx.Bucket(meta).Put(key, []byte(req.OperationID)); err != nil {
				return err
			}
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if tx.Bucket(operations).Stats().KeyN >= 100000 {
			return errors.New("operation_capacity_hold")
		}
		m := tx.Bucket(meta)
		if len(m.Get([]byte("active"))) != 0 {
			return errors.New("unresolved_signer_sequence_hold")
		}
		if req.Kind == "withdrawal" {
			challenge := []byte("challenge:" + req.Approval.ChallengeID)
			if m.Get(challenge) != nil {
				return errors.New("withdrawal_challenge_reused")
			}
			if err := m.Put(challenge, []byte(req.OperationID)); err != nil {
				return err
			}
		}
		if err := e.reserveExecutionAuthority(ctx, tx, req); err != nil {
			return err
		}
		r = record{Request: req, Fingerprint: fingerprint(req), Result: Result{OperationID: req.OperationID, Status: "UNKNOWN", Reason: "intent_persisted", DurableFenced: true}}
		if err := save(tx, r); err != nil {
			return err
		}
		return m.Put([]byte("active"), []byte(req.OperationID))
	})
	if err != nil {
		return Result{}, err
	}
	if exists {
		return r.Result, nil
	}
	if ctx.Err() != nil || e.policy.validate(req, e.now()) != nil || (grant != nil && !grant.current(ctx)) {
		// No signing invocation has started, but retain the accepted economic
		// identity and consumed authority so this operation cannot be renewed.
		r.Result.Status = "REFUSED"
		r.Result.Reason = "authority_expired_before_signing"
		err = e.db.Update(func(tx *bolt.Tx) error {
			if err := save(tx, r); err != nil {
				return err
			}
			if string(tx.Bucket(meta).Get([]byte("active"))) != req.OperationID {
				return errors.New("active_state_conflict")
			}
			return tx.Bucket(meta).Delete([]byte("active"))
		})
		if err != nil {
			return Result{}, errors.New("durability_failed")
		}
		return r.Result, nil
	}
	// Every persisted pre-send phase is a HOLD on retry. We deliberately trade
	// liveness for at-most-one signature and broadcast invocation per operation.
	r = held(r, "signing_started")
	if err = e.write(r); err != nil {
		return Result{}, errors.New("durability_failed")
	}
	signed, err := e.backend.Sign(ctx, req)
	if err != nil {
		if errors.Is(err, ErrPreSignRefused) {
			r.Result.Status = "REFUSED"
			r.Result.Reason = "pre_sign_refused_no_broadcast"
			err = e.db.Update(func(tx *bolt.Tx) error {
				if err := save(tx, r); err != nil {
					return err
				}
				if string(tx.Bucket(meta).Get([]byte("active"))) != req.OperationID {
					return errors.New("active_state_conflict")
				}
				return tx.Bucket(meta).Delete([]byte("active"))
			})
			if err != nil {
				return Result{}, errors.New("durability_failed")
			}
			return r.Result, nil
		}
		r = held(r, "signing_uncertain")
		_ = e.write(r)
		return r.Result, nil
	}
	sum := sha256.Sum256(signed.Bytes)
	if len(signed.Bytes) == 0 || len(signed.Bytes) > 65536 || !strings.EqualFold(signed.Hash, hex.EncodeToString(sum[:])) || e.backend.ValidateSigned(req, signed) != nil {
		r = held(r, "signed_payload_refused")
		_ = e.write(r)
		return r.Result, nil
	}
	signed.Hash = strings.ToUpper(signed.Hash)
	if grant != nil {
		grant.signedHash = signed.Hash
	}
	r.Signed = signed
	r.Result.TxHash = signed.Hash
	r = held(r, "signed_transaction_persisted")
	if err = e.write(r); err != nil {
		return Result{}, errors.New("durability_failed")
	}
	r = held(r, "broadcast_started")
	if err = e.write(r); err != nil {
		return Result{}, errors.New("durability_failed")
	}
	if ctx.Err() != nil || e.policy.validate(req, e.now()) != nil || (grant != nil && !grant.current(ctx)) {
		// A signature already exists: expiry cannot release its sequence/hold,
		// authorize a replacement or turn this into a retryable refusal.
		reason := "wager_authority_expired_before_broadcast"
		if req.Kind == "withdrawal" {
			reason = "withdrawal_authority_expired_before_broadcast"
		}
		r = held(r, reason)
		if err = e.write(r); err != nil {
			return Result{}, errors.New("durability_failed")
		}
		return r.Result, nil
	}
	out, err := e.backend.Broadcast(ctx, signed)
	if err == nil && out.Status == "ACCEPTED" && out.Code == 0 {
		r.Result.Status = "ACCEPTED"
		r.Result.Reason = "broadcast_accepted_only"
	} else {
		r = held(r, "broadcast_uncertain")
	}
	// Even an authenticated CheckTx rejection is retained as UNKNOWN until
	// canonical reconciliation: it cannot justify another transfer or release.
	if err = e.write(r); err != nil {
		return Result{}, errors.New("durability_failed")
	}
	return r.Result, nil
}

func (e *Engine) Reconcile(ctx context.Context, id string) (Result, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	var r record
	if err := e.db.View(func(tx *bolt.Tx) error { var err error; r, err = load(tx, id); return err }); err != nil {
		return Result{}, err
	}
	if r.Result.Status == "REFUSED" {
		return r.Result, nil
	}
	if r.Result.Status == "CONFIRMED" || r.Result.Status == "FAILED" {
		if e.backend.ValidateSigned(r.Request, r.Signed) != nil {
			return Result{}, errors.New("persisted_signed_payload_refused")
		}
		return r.Result, nil
	}
	if len(r.Signed.Bytes) == 0 {
		return r.Result, nil
	}
	if e.backend.ValidateSigned(r.Request, r.Signed) != nil {
		return Result{}, errors.New("persisted_signed_payload_refused")
	}
	c, err := e.backend.Confirm(ctx, r.Request, r.Signed)
	if err != nil {
		r = held(r, "confirmation_unavailable")
		if err = e.write(r); err != nil {
			return Result{}, errors.New("durability_failed")
		}
		return r.Result, nil
	}
	switch c.Status {
	case "CONFIRMED", "FAILED":
		// Only a consensus-authenticated backend may produce these terminal
		// outcomes. Effects are globally unique within this signer history.
		if !validConfirmation(r.Signed, c) {
			return Result{}, errors.New("confirmation_identity_refused")
		}
		r.Confirmation = c
		r.Result.Status = c.Status
		r.Result.Reason = "authenticated_committed_execution"
		err = e.db.Update(func(tx *bolt.Tx) error {
			key := []byte("wolo-1:" + r.Signed.Hash)
			old := tx.Bucket(effects).Get(key)
			if old != nil && string(old) != id {
				return errors.New("chain_effect_already_consumed")
			}
			if err := tx.Bucket(effects).Put(key, []byte(id)); err != nil {
				return err
			}
			if string(tx.Bucket(meta).Get([]byte("active"))) == id {
				if err := tx.Bucket(meta).Delete([]byte("active")); err != nil {
					return err
				}
			}
			return save(tx, r)
		})
	case "OBSERVED_NONCREDITING":
		r.Result.Status = c.Status
		r.Result.Reason = "untrusted_consensus_anchor"
		err = e.write(r)
	default:
		r = held(r, "confirmation_unverifiable")
		err = e.write(r)
	}
	if err != nil {
		return Result{}, err
	}
	return r.Result, nil
}

func (r Result) String() string { return fmt.Sprintf("%s:%s", r.OperationID, r.Status) }
