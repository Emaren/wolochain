package satchelservice

// Protected composition of the existing engine, separately leased SDK role,
// signed reserve qualification and durable execution fence. No second journal,
// payment controller, key creation, or legacy settlement transport is added.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"path/filepath"
	"runtime/debug"
	"strconv"
	"strings"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

const escrowSignerEnrollmentScope = "aoe2war/satchel/escrow-signer-enrollment/v1"
const escrowOperationPermitScope = "aoe2war/satchel/escrow-operation-permit/v1"

type EscrowSignerEnrollment struct {
	Version             int    `json:"version"`
	Scope               string `json:"scope"`
	SourceCommit        string `json:"source_commit"`
	PublicKeyHex        string `json:"public_key_hex"`
	KeyringDir          string `json:"keyring_dir"`
	KeyName             string `json:"key_name"`
	PassphraseFile      string `json:"passphrase_file"`
	OperationPermitFile string `json:"operation_permit_file"`
}

// Separate transaction-specific owner/execution permission, under the existing
// independently enrolled activation key. This never signs its own permission.
type EscrowReturnOperationPermit struct {
	Version             int    `json:"version"`
	Scope               string `json:"scope"`
	ChainID             string `json:"chain_id"`
	Denom               string `json:"denom"`
	SourceCommit        string `json:"source_commit"`
	BinarySHA256        string `json:"binary_sha256"`
	ConfigSHA256        string `json:"config_sha256"`
	EnrollmentSHA256    string `json:"enrollment_sha256"`
	Vault               string `json:"vault"`
	Escrow              string `json:"escrow"`
	ClaimID             string `json:"claim_id"`
	ApprovalSHA256      string `json:"approval_sha256"`
	ReserveReviewSHA256 string `json:"reserve_review_sha256"`
	AmountUWolo         string `json:"amount_uwolo"`
	FeeUWolo            string `json:"fee_uwolo"`
	Nonce               string `json:"nonce"`
	IssuedAt            int64  `json:"issued_at"`
	ExpiresAt           int64  `json:"expires_at"`
	Signature           string `json:"signature"`
}

func EscrowReturnOperationPermitMessage(p EscrowReturnOperationPermit) []byte {
	p.Signature = ""
	b, _ := json.Marshal([]any{escrowOperationPermitScope, p})
	return b
}

type EnrolledEscrowExecutor struct {
	issuer       *CustodyAuthority
	enrollment   EscrowSignerEnrollment
	native       *KeyringBackend
	unlockDigest string
}

type enrolledEscrowOperation struct {
	executor           *EnrolledEscrowExecutor
	request            TransferRequest
	permitDigest       string
	permitRaw          []byte
	reviewRaw          []byte
	globalPermitDigest string
	nonce              string
	reviewDigest       string
	stateHeight        int64
	commitHash         string
	expires            time.Time
}
type enrolledEscrowOperationKey struct{}

func cleanEscrowSourceCommit() (string, error) {
	i, ok := debug.ReadBuildInfo()
	if !ok {
		return "", ErrEscrowRuntimeHeld
	}
	var revision, modified string
	for _, setting := range i.Settings {
		if setting.Key == "vcs.revision" {
			revision = setting.Value
		}
		if setting.Key == "vcs.modified" {
			modified = setting.Value
		}
	}
	if len(revision) != 40 || modified != "false" {
		return "", ErrEscrowRuntimeHeld
	}
	b, err := hex.DecodeString(revision)
	if err != nil || len(b) != 20 || bytesAllZero(b) {
		return "", ErrEscrowRuntimeHeld
	}
	return revision, nil
}

func NewEnrolledEscrowExecutor(issuer *CustodyAuthority) (*EnrolledEscrowExecutor, error) {
	return newEnrolledEscrowExecutor(issuer, cleanEscrowSourceCommit)
}

func newEnrolledEscrowExecutor(issuer *CustodyAuthority, source func() (string, error)) (*EnrolledEscrowExecutor, error) {
	if issuer == nil || issuer.engine == nil || issuer.engine.custodyAuthority != issuer || source == nil {
		return nil, ErrEscrowRuntimeHeld
	}
	c := issuer.config
	if _, _, err := issuer.currentFiles(context.Background()); err != nil || !issuer.nativeLeaseHeld() {
		return nil, ErrEscrowRuntimeHeld
	}
	if c.EscrowSignerEnrollmentFile == "" || !validReserveDigest(c.EscrowSignerEnrollmentSHA256) {
		return nil, ErrEscrowRuntimeHeld
	}
	raw, err := ReadPrivateFile(c.EscrowSignerEnrollmentFile, 64<<10)
	var enrollment EscrowSignerEnrollment
	if err != nil || custodySHA(raw) != c.EscrowSignerEnrollmentSHA256 || !chainjson.ValidFolded(raw) || strictHTTPJSON(raw, &enrollment) != nil ||
		enrollment.Version != 1 || enrollment.Scope != escrowSignerEnrollmentScope {
		return nil, ErrEscrowRuntimeHeld
	}
	revision, err := source()
	if err != nil || revision != enrollment.SourceCommit {
		return nil, ErrEscrowRuntimeHeld
	}
	for _, path := range []string{enrollment.KeyringDir, enrollment.PassphraseFile, enrollment.OperationPermitFile} {
		if !filepath.IsAbs(path) || filepath.Clean(path) != path {
			return nil, ErrEscrowRuntimeHeld
		}
	}
	if enrollment.KeyringDir == c.KeyringDir || enrollment.KeyName == c.KeyName || enrollment.KeyName == "" ||
		enrollment.PassphraseFile == c.PassphraseFile || enrollment.OperationPermitFile == c.PermitFile ||
		enrollment.PublicKeyHex == c.PublicKeyHex {
		return nil, ErrEscrowRuntimeHeld
	}
	unlock, err := ReadPrivateFile(enrollment.PassphraseFile, 4096)
	if err != nil {
		return nil, ErrEscrowRuntimeHeld
	}
	s := &EnrolledEscrowExecutor{issuer: issuer, enrollment: enrollment, unlockDigest: custodySHA(unlock)}
	for i := range unlock {
		unlock[i] = 0
	}
	s.native, err = NewKeyringBackend(BackendConfig{RPC: c.RPC, REST: c.REST, WitnessRPC: c.WitnessRPC,
		Vault: c.BettingEscrow, PublicKeyHex: enrollment.PublicKeyHex, KeyringDir: enrollment.KeyringDir, KeyName: enrollment.KeyName, PassphraseFile: enrollment.PassphraseFile,
		FeesUWolo: c.FeesUWolo, MaxAmountUWolo: strconv.FormatUint(c.MaxAmountUWolo, 10), GasLimit: c.GasLimit, TimeoutBlocks: c.TimeoutBlocks,
		ApprovedDestinations: []string{c.Vault}, ProtectedAddresses: []string{c.Vault}, ReturnDestination: c.Vault,
		ReturnVerifier: func(req TransferRequest) error {
			if req.ReturnApproval == nil {
				return ErrEscrowRuntimeHeld
			}
			return issuer.engine.db.View(func(tx *bolt.Tx) error {
				if issuer.engine.validateReturnAt(tx, *req.ReturnApproval, true) != nil {
					return ErrEscrowRuntimeHeld
				}
				b := tx.Bucket(returns)
				var record returnRecord
				if b == nil || json.Unmarshal(b.Get([]byte(req.ReturnApproval.ClaimID)), &record) != nil || record.Receipt != nil || hashJSON(record.Approval) != hashJSON(*req.ReturnApproval) {
					return ErrEscrowRuntimeHeld
				}
				return nil
			})
		},
		AuthorizeSign: func(ctx context.Context, req TransferRequest) bool {
			escrowBoundary(ctx, "sign_authorization")
			return s.authorizeIrreversible(ctx, req)
		},
		AuthorizeBroadcast: func(ctx context.Context, tx SignedTransaction) bool {
			escrowBoundary(ctx, "broadcast_authorization")
			g, _ := ctx.Value(enrolledEscrowOperationKey{}).(*enrolledEscrowOperation)
			return g != nil && s.authorizeIrreversible(ctx, g.request) && s.native.ValidateSigned(g.request, tx) == nil
		},
		ConfirmTransaction: func(ctx context.Context, req TransferRequest, tx SignedTransaction) (Confirmation, error) {
			evidence, err := issuer.reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: req.Sender, Recipient: req.Recipient, AmountUWolo: req.AmountUWolo, Memo: req.Memo}, tx.Hash)
			if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || !bytes.Equal(evidence.Observation().TxBytes, tx.Bytes) {
				return Confirmation{Status: "UNKNOWN"}, ErrEscrowRuntimeHeld
			}
			o := evidence.Observation()
			return Confirmation{Status: "CONFIRMED", ReceiptID: evidence.Receipt().ID(), Height: o.Height, BlockHash: o.BlockHash}, nil
		},
	})
	if err != nil {
		return nil, ErrEscrowRuntimeHeld
	}
	return s, nil
}

func (s *EnrolledEscrowExecutor) Close() {
	if s != nil && s.native != nil {
		s.native.Close()
	}
}

// No escrow mutex acquisition here: SDK callbacks already own that mutex.
// KeyringBackend itself rechecks the real escrow lease before each callback.
func (s *EnrolledEscrowExecutor) authorized(ctx context.Context, req TransferRequest) bool {
	if s == nil || ctx == nil || ctx.Err() != nil {
		return false
	}
	g, _ := ctx.Value(enrolledEscrowOperationKey{}).(*enrolledEscrowOperation)
	if g == nil || g.executor != s || hashJSON(req) != hashJSON(g.request) {
		return false
	}
	if !s.protectedCurrent(ctx, g) {
		return false
	}
	completed := time.Now()
	return ctx.Err() == nil && completed.Before(g.expires) &&
		validReviewTime(req.ReturnApproval.IssuedAt, req.ReturnApproval.ExpiresAt, completed.Unix(), true) &&
		validReviewTime(req.ReturnApproval.Allocation.IssuedAt, req.ReturnApproval.Allocation.ExpiresAt, completed.Unix(), true)
}

// Fresh bank collection belongs at the irreversible SDK boundaries, after its
// account/head I/O and immediately before the actual signing/broadcast call.
// Outer guards retain protected permission checks without repeating this I/O.
func (s *EnrolledEscrowExecutor) authorizeIrreversible(ctx context.Context, req TransferRequest) bool {
	if !s.authorized(ctx, req) {
		return false
	}
	g, _ := ctx.Value(enrolledEscrowOperationKey{}).(*enrolledEscrowOperation)
	a := s.issuer
	bank, proof, err := a.reader.ReadCurrentBankProof(ctx, a.config.BettingEscrow)
	if err != nil {
		return false
	}
	verifier, err := satchel.NewProofVerifier(a.config.TrustAnchor)
	if err != nil {
		return false
	}
	bank, err = verifier.VerifyBankProof(ctx, a.config.BettingEscrow, bank.Height(), proof)
	if err != nil || !s.protectedCurrent(ctx, g) {
		return false
	}
	completed := time.Now() // after final proof, lease and revocation I/O
	return err == nil && bank.Height() == g.stateHeight && strings.EqualFold(bank.BlockHash(), g.commitHash) && bank.CurrentAt(completed) &&
		ctx.Err() == nil && completed.Before(g.expires) && validReviewTime(req.ReturnApproval.IssuedAt, req.ReturnApproval.ExpiresAt, completed.Unix(), true) &&
		validReviewTime(req.ReturnApproval.Allocation.IssuedAt, req.ReturnApproval.Allocation.ExpiresAt, completed.Unix(), true)
}

func (s *EnrolledEscrowExecutor) protectedCurrent(ctx context.Context, g *enrolledEscrowOperation) bool {
	a := s.issuer
	digest, _, err := a.currentFiles(ctx)
	if err != nil || digest != g.globalPermitDigest || !a.nativeLeaseHeld() {
		return false
	}
	raw, err := ReadPrivateFile(a.config.EscrowSignerEnrollmentFile, 64<<10)
	if err != nil || custodySHA(raw) != a.config.EscrowSignerEnrollmentSHA256 {
		return false
	}
	unlock, err := ReadPrivateFile(s.enrollment.PassphraseFile, 4096)
	if err != nil {
		return false
	}
	matches := custodySHA(unlock) == s.unlockDigest
	for i := range unlock {
		unlock[i] = 0
	}
	if !matches {
		return false
	}
	permit, err := ReadPrivateFile(s.enrollment.OperationPermitFile, 64<<10)
	if err != nil || custodySHA(permit) != g.permitDigest {
		return false
	}
	review, err := s.reviewBytes()
	return err == nil && custodySHA(review) == g.reviewDigest && ctx.Err() == nil && time.Now().Before(g.expires)
}

func (s *EnrolledEscrowExecutor) reviewBytes() ([]byte, error) {
	raw, err := ReadPrivateFile(s.issuer.config.EscrowReturnExecutionFile, 64<<10)
	var e escrowReturnRuntimeEnrollment
	if err != nil || custodySHA(raw) != s.issuer.config.EscrowReturnExecutionSHA256 || !chainjson.ValidFolded(raw) || strictHTTPJSON(raw, &e) != nil || e.Version != 1 || e.Scope != escrowReturnEnrollmentScope {
		return nil, ErrEscrowRuntimeHeld
	}
	return readPrivateFileBounded(e.ReviewFile, escrowReturnExecutionMaxBytes, escrowReturnExecutionMaxBytes)
}

func (s *EnrolledEscrowExecutor) Execute(ctx context.Context, a ReturnApproval) (EscrowReturnSpendResult, error) {
	if s == nil || ctx == nil || ctx.Err() != nil || !claimIDs.MatchString(a.ClaimID) || a.Allocation == nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	// Detach all caller-owned partition slices before any authorization or I/O.
	raw, err := json.Marshal(a)
	if err != nil || len(raw) > HTTPMaxBodyBytes {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	var detached ReturnApproval
	if strictHTTPJSON(raw, &detached) != nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	a = detached
	req := TransferRequest{OperationID: "satchel:claim-return:" + a.ClaimID, ChainID: "wolo-1", Denom: "uwolo", Sender: s.issuer.config.BettingEscrow, Recipient: s.issuer.config.Vault,
		Kind: "claim_return", AmountUWolo: a.AmountUWolo, OwnerID: a.OwnerID, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID, ReturnApproval: &a}
	// An existing identity is observation only, even after permission expiry.
	escrowBoundary(ctx, "prior_journal")
	var prior *EscrowReturnSpendResult
	err = s.issuer.engine.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(escrowReturnSpendBucket)
		if b == nil || b.Get([]byte(a.ClaimID)) == nil {
			return nil
		}
		var state escrowReturnSpendRecord
		if json.Unmarshal(b.Get([]byte(a.ClaimID)), &state) != nil || !s.issuer.engine.validEscrowSpendRecord(state, a.ClaimID) || state.ApprovalHash != hashJSON(req) || state.Result.OperationID != req.OperationID || state.Result.Status != "UNKNOWN" || !state.Result.DurableFenced ||
			(state.Result.TxHash != "" && (state.Result.TxHash != state.Signed.Hash || s.native.ValidateSigned(req, state.Signed) != nil)) || (state.Result.TxHash == "" && (len(state.Signed.Bytes) > 0 || state.Signed.Hash != "")) {
			return ErrEscrowRuntimeHeld
		}
		prior = &state.Result
		return nil
	})
	if err != nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	if prior != nil {
		return *prior, nil
	}
	escrowBoundary(ctx, "owner_permission")
	permitRaw, err := ReadPrivateFile(s.enrollment.OperationPermitFile, 64<<10)
	var permit EscrowReturnOperationPermit
	if err != nil || !chainjson.ValidFolded(permitRaw) || strictHTTPJSON(permitRaw, &permit) != nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	escrowBoundary(ctx, "reserve_review")
	reviewRaw, err := s.reviewBytes()
	var bundle EscrowReturnExecutionBundle
	if err != nil || !chainjson.ValidFolded(reviewRaw) || strictHTTPJSON(reviewRaw, &bundle) != nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	c := s.issuer.config
	escrowBoundary(ctx, "global_permission")
	globalDigest, globalExpiry, err := s.issuer.currentFiles(ctx)
	if err != nil {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	escrowBoundary(ctx, "owner_verification")
	key, _ := hex.DecodeString(c.ActivationAuthorityKeyHex)
	now := time.Now()
	if permit.Version != 1 || permit.Scope != escrowOperationPermitScope || permit.ChainID != "wolo-1" || permit.Denom != "uwolo" ||
		permit.SourceCommit != s.enrollment.SourceCommit || permit.BinarySHA256 != s.issuer.binaryDigest || permit.ConfigSHA256 != s.issuer.configDigest || permit.EnrollmentSHA256 != c.EscrowSignerEnrollmentSHA256 ||
		permit.Vault != c.Vault || permit.Escrow != c.BettingEscrow || permit.ClaimID != a.ClaimID || permit.ApprovalSHA256 != hashJSON(a) || permit.ReserveReviewSHA256 != custodySHA(reviewRaw) ||
		permit.AmountUWolo != a.AmountUWolo || permit.FeeUWolo != c.FeesUWolo || !validReserveDigest(permit.Nonce) || !validReviewTime(permit.IssuedAt, permit.ExpiresAt, now.Unix(), true) ||
		permit.ExpiresAt-permit.IssuedAt > 120 || !validReviewSignature(permit.Signature, ed25519.PublicKey(key), EscrowReturnOperationPermitMessage(permit)) {
		return EscrowReturnSpendResult{}, ErrEscrowRuntimeHeld
	}
	expires := time.Unix(permit.ExpiresAt, 0)
	if globalExpiry.Before(expires) {
		expires = globalExpiry
	}
	for _, end := range []int64{a.ExpiresAt, a.Allocation.ExpiresAt, bundle.Review.ExpiresAt} {
		if time.Unix(end, 0).Before(expires) {
			expires = time.Unix(end, 0)
		}
	}
	g := &enrolledEscrowOperation{executor: s, request: req, permitDigest: custodySHA(permitRaw), permitRaw: append([]byte(nil), permitRaw...), reviewRaw: append([]byte(nil), reviewRaw...), globalPermitDigest: globalDigest, nonce: permit.Nonce, reviewDigest: custodySHA(reviewRaw), stateHeight: bundle.Review.StateHeight, commitHash: bundle.Review.CommitBlockHash, expires: expires}
	ctx, cancel := context.WithDeadline(context.WithValue(ctx, enrolledEscrowOperationKey{}, g), expires)
	defer cancel()
	return s.issuer.engine.ExecuteEnrolledEscrowReturn(ctx, a, s.native, EscrowReturnSpendGuard{Permit: s.authorized, PreBroadcast: func(ctx context.Context, r TransferRequest, tx SignedTransaction) bool {
		return s.authorized(ctx, r) && s.native.ValidateSigned(r, tx) == nil
	}})
}
