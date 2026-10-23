package satchelservice

// Runtime execution qualification, distinct from the dormant C2 source
// capability. No signed review alone, JSON boolean or configured address can
// construct the opaque value below. Reviewers remain responsible for genuine
// financial completeness and independence; this code does not discover it.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"math/big"
	"os"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

var errCustodyUnavailable = errors.New("custody_qualification_unavailable")

type CustodyAuthority struct {
	engine                                                            *Engine
	native                                                            *KeyringBackend
	reader                                                            *satchel.TrustedReader
	config                                                            Config
	configPath, configDigest, binaryDigest, tokenDigest, unlockDigest string
	stateIdentity                                                     os.FileInfo
}

// RuntimeCustodyCapability is nonconstructible outside this package and grants
// no app credit or release authority. Every use rechecks revocable source files.
type RuntimeCustodyCapability struct{ grant *custodyExecutionGrant }
type custodyExecutionGrant struct {
	authority                                 *CustodyAuthority
	bank                                      satchel.AuthenticatedBankEvidence
	reserve                                   QualifiedReserveReview
	reviewDigest, permitDigest, journalDigest string
	expiresAt                                 time.Time
	operationFingerprint, signedHash          string
}
type custodyGrantContextKey struct{}

func custodySHA(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }

func runtimeCustodyBinaryDigest() (string, error) {
	path, err := os.Executable()
	if err != nil {
		return "", errCustodyUnavailable
	}
	if runtime.GOOS == "linux" {
		path = "/proc/self/exe"
	}
	f, err := os.Open(path)
	if err != nil {
		return "", errCustodyUnavailable
	}
	defer f.Close()
	s, err := f.Stat()
	if err != nil || !s.Mode().IsRegular() || s.Size() <= 0 || s.Size() > 512<<20 {
		return "", errCustodyUnavailable
	}
	h := sha256.New()
	n, err := io.Copy(h, io.LimitReader(f, (512<<20)+1))
	if err != nil || n != s.Size() {
		return "", errCustodyUnavailable
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// NewCustodyAuthority binds existing live handles, not assertions about them.
// The native lease and fully validated journal are checked on every issuance.
// Missing review provisioning keeps the authority unavailable, preserving old
// configurations for read-only diagnostics/recovery rather than enabling them.
func NewCustodyAuthority(e *Engine, native *KeyringBackend, reader *satchel.TrustedReader, configPath, configDigest, binaryDigest string) (*CustodyAuthority, error) {
	if e == nil || native == nil || reader == nil {
		return nil, errCustodyUnavailable
	}
	backend, ok := e.backend.(interface{ NativeCustodyBackend() *KeyringBackend })
	if !ok || backend.NativeCustodyBackend() != native || native.cfg.AuthorizeSign == nil || native.cfg.AuthorizeBroadcast == nil {
		return nil, errCustodyUnavailable
	}
	c, d, err := LoadConfig(configPath)
	if err != nil || d != configDigest || c.Vault != e.policy.Vault || c.Vault != native.cfg.Vault || c.StatePath != e.db.Path() ||
		c.PublicKeyHex != native.cfg.PublicKeyHex || c.KeyringDir != native.cfg.KeyringDir || c.KeyName != native.cfg.KeyName || c.PassphraseFile != native.cfg.PassphraseFile ||
		c.FeesUWolo != native.cfg.FeesUWolo || c.GasLimit != native.cfg.GasLimit || c.TimeoutBlocks != native.cfg.TimeoutBlocks ||
		strconv.FormatUint(c.MaxAmountUWolo, 10) != native.cfg.MaxAmountUWolo || c.RPC != native.cfg.RPC || c.REST != native.cfg.REST || c.WitnessRPC != native.cfg.WitnessRPC {
		return nil, errCustodyUnavailable
	}
	withdrawal, _ := hex.DecodeString(c.WithdrawalApprovalKeyHex)
	wager, _ := hex.DecodeString(c.WagerApprovalKeyHex)
	if hashJSON(e.policy) != hashJSON(Policy{Vault: c.Vault, BettingEscrow: c.BettingEscrow, ProtectedAddresses: c.ProtectedAddresses, MaxAmountUWolo: c.MaxAmountUWolo, WithdrawalApprovalKey: withdrawal, WagerApprovalKey: wager}) {
		return nil, errCustodyUnavailable
	}
	actual, err := runtimeCustodyBinaryDigest()
	if err != nil || actual != binaryDigest {
		return nil, errCustodyUnavailable
	}
	token, err := ReadPrivateFile(c.TokenFile, 4096)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	tokenDigest := custodySHA(token)
	for i := range token {
		token[i] = 0
	}
	unlock, err := ReadPrivateFile(c.PassphraseFile, 4096)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	unlockDigest := custodySHA(unlock)
	for i := range unlock {
		unlock[i] = 0
	}
	identity, err := os.Lstat(c.StatePath)
	if err != nil || !identity.Mode().IsRegular() || identity.Mode().Perm() != 0600 {
		return nil, errCustodyUnavailable
	}
	return &CustodyAuthority{engine: e, native: native, reader: reader, config: c, configPath: configPath, configDigest: d, binaryDigest: actual, tokenDigest: tokenDigest, unlockDigest: unlockDigest, stateIdentity: identity}, nil
}

// RequireCustodyAuthority is a one-time runtime binding, not a way to activate
// an arbitrary backend. Production calls it before opening the HTTP listener.
func (e *Engine) RequireCustodyAuthority(a *CustodyAuthority) error {
	if e == nil {
		return errCustodyUnavailable
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if a == nil || a.engine != e || e.custodyAuthority != nil {
		return errCustodyUnavailable
	}
	e.custodyAuthority = a
	return nil
}

func (a *CustodyAuthority) nativeLeaseHeld() bool {
	if a == nil || a.native == nil {
		return false
	}
	a.native.mu.Lock()
	defer a.native.mu.Unlock()
	return !a.native.closed.Load() && a.native.signer != nil && a.native.keyringLease != nil && a.native.keyringLeaseCurrent()
}

// No cached permit or source/configuration assertion can survive rotation.
func (a *CustodyAuthority) currentFiles(ctx context.Context) (string, time.Time, error) {
	if ctx == nil || ctx.Err() != nil {
		return "", time.Time{}, errCustodyUnavailable
	}
	_, d, err := LoadConfig(a.configPath)
	if err != nil || d != a.configDigest {
		return "", time.Time{}, errCustodyUnavailable
	}
	current, err := os.Lstat(a.config.StatePath)
	if err != nil || !current.Mode().IsRegular() || current.Mode().Perm() != 0600 || !os.SameFile(a.stateIdentity, current) {
		return "", time.Time{}, errCustodyUnavailable
	}
	st, ok := current.Sys().(*syscall.Stat_t)
	if !ok || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 {
		return "", time.Time{}, errCustodyUnavailable
	}
	token, err := ReadPrivateFile(a.config.TokenFile, 4096)
	if err != nil {
		return "", time.Time{}, errCustodyUnavailable
	}
	tokenMatches := custodySHA(token) == a.tokenDigest
	for i := range token {
		token[i] = 0
	}
	if !tokenMatches {
		return "", time.Time{}, errCustodyUnavailable
	}
	unlock, err := ReadPrivateFile(a.config.PassphraseFile, 4096)
	if err != nil {
		return "", time.Time{}, errCustodyUnavailable
	}
	unlockMatches := custodySHA(unlock) == a.unlockDigest
	for i := range unlock {
		unlock[i] = 0
	}
	if !unlockMatches {
		return "", time.Time{}, errCustodyUnavailable
	}
	data, err := ReadPrivateFile(a.config.PermitFile, 16384)
	if err != nil {
		return "", time.Time{}, errCustodyUnavailable
	}
	var p ExecutionPermit
	if !chainjson.ValidFolded(data) || strictHTTPJSON(data, &p) != nil || !validPermitAt(a.config, a.configDigest, a.binaryDigest, time.Now(), p) || ctx.Err() != nil {
		return "", time.Time{}, errCustodyUnavailable
	}
	return custodySHA(data), time.Unix(p.ExpiresAt, 0), nil
}

func (a *CustodyAuthority) Capability(ctx context.Context) RuntimeCustodyCapability {
	if a == nil || a.engine == nil || a.native == nil || a.reader == nil || ctx == nil || ctx.Err() != nil {
		return RuntimeCustodyCapability{}
	}
	a.engine.mu.Lock()
	defer a.engine.mu.Unlock()
	g, err := a.qualifyLocked(ctx)
	if err != nil {
		return RuntimeCustodyCapability{}
	}
	return RuntimeCustodyCapability{grant: g}
}

func (c RuntimeCustodyCapability) Available(ctx context.Context) bool {
	if c.grant == nil {
		return false
	}
	a := c.grant.authority
	a.engine.mu.Lock()
	defer a.engine.mu.Unlock()
	journal, err := a.engine.custodyJournalLocked()
	return err == nil && journal.JournalDigest == c.grant.journalDigest && journal.UnresolvedCount == 0 && a.nativeLeaseHeld() && c.grant.current(ctx)
}
func (c RuntimeCustodyCapability) ExpiresAt() time.Time {
	if c.grant == nil {
		return time.Time{}
	}
	return c.grant.expiresAt
}

// Caller owns engine.mu. The shared journal scanner authenticates payloads,
// receipt uniqueness and accounting structure on this actual recovered DB.
func (a *CustodyAuthority) qualifyLocked(ctx context.Context) (*custodyExecutionGrant, error) {
	if ctx == nil || ctx.Err() != nil || a.engine.custodyAuthority != a || !a.nativeLeaseHeld() || a.config.ReserveReviewFile == "" {
		return nil, errCustodyUnavailable
	}
	permitDigest, permitExpiry, err := a.currentFiles(ctx)
	if err != nil {
		return nil, err
	}
	journal, err := a.engine.custodyJournalLocked()
	if err != nil || journal.UnresolvedCount != 0 || journal.HeldOutboundUWolo != "0" {
		return nil, errCustodyUnavailable
	}
	if err := a.engine.db.View(func(tx *bolt.Tx) error {
		if len(tx.Bucket(meta).Get([]byte("active"))) != 0 {
			return errCustodyUnavailable
		}
		return nil
	}); err != nil {
		return nil, errCustodyUnavailable
	}
	data, err := ReadPrivateFile(a.config.ReserveReviewFile, 16384)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	var review SignedReserveReview
	if !chainjson.ValidFolded(data) || strictHTTPJSON(data, &review) != nil || review.JournalSnapshotSHA256 != journal.JournalDigest {
		return nil, errCustodyUnavailable
	}
	accounting, _ := hex.DecodeString(a.config.AccountingReviewerKeyHex)
	custody, _ := hex.DecodeString(a.config.CustodyReviewerKeyHex)
	execution, _ := hex.DecodeString(a.config.ActivationAuthorityKeyHex)
	wager, _ := hex.DecodeString(a.config.WagerApprovalKeyHex)
	withdrawal, _ := hex.DecodeString(a.config.WithdrawalApprovalKeyHex)
	_, proof, err := a.reader.ReadCurrentBankProof(ctx, a.config.Vault)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	// Bind even an in-process reader to this exact protected configuration's
	// root. An opaque result authenticated under some other root is insufficient.
	verifier, err := satchel.NewProofVerifier(a.config.TrustAnchor)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	bank, err := verifier.VerifyBankProof(ctx, a.config.Vault, proof.Height, proof)
	if err != nil {
		return nil, errCustodyUnavailable
	}
	qualified, err := EvaluateProofBoundReserveReview(time.Now(), bank, review, ReserveReviewAuthority{
		AccountingReviewerKey: accounting, CustodyReviewerKey: custody, ExecutionAuthorityKey: execution, WagerApprovalKey: wager, WithdrawalApprovalKey: withdrawal,
		ExpectedVault: a.config.Vault, ExpectedBuildSHA256: a.binaryDigest, ExpectedConfigSHA256: a.configDigest, ExpectedPermitSHA256: permitDigest})
	if err != nil || !qualified.Sufficient {
		return nil, errCustodyUnavailable
	}
	free, freeOK := reserveUint(qualified.UncommittedUWolo)
	fee, feeOK := reserveUint(a.config.FeesUWolo)
	if !freeOK || !feeOK || free.Cmp(fee) <= 0 {
		return nil, errCustodyUnavailable
	}
	expires := qualified.ExpiresAt
	if permitExpiry.Before(expires) {
		expires = permitExpiry
	}
	g := &custodyExecutionGrant{authority: a, bank: bank, reserve: qualified, reviewDigest: custodySHA(data), permitDigest: permitDigest, journalDigest: journal.JournalDigest, expiresAt: expires}
	if !g.current(ctx) || !a.nativeLeaseHeld() {
		return nil, errCustodyUnavailable
	}
	return g, nil
}

func (g *custodyExecutionGrant) current(ctx context.Context) bool {
	if g == nil || ctx == nil || ctx.Err() != nil || !time.Now().Before(g.expiresAt) || !g.bank.CurrentAt(time.Now()) {
		return false
	}
	permit, _, err := g.authority.currentFiles(ctx)
	if err != nil || permit != g.permitDigest {
		return false
	}
	review, err := ReadPrivateFile(g.authority.config.ReserveReviewFile, 16384)
	return err == nil && custodySHA(review) == g.reviewDigest && ctx.Err() == nil && time.Now().Before(g.expiresAt) && g.bank.CurrentAt(time.Now())
}

func (a *CustodyAuthority) AuthorizeSign(ctx context.Context, r TransferRequest) bool {
	if a == nil || ctx == nil {
		return false
	}
	g, _ := ctx.Value(custodyGrantContextKey{}).(*custodyExecutionGrant)
	return g != nil && g.authority == a && g.operationFingerprint == fingerprint(r) && g.signedHash == "" && g.current(ctx)
}
func (a *CustodyAuthority) AuthorizeBroadcast(ctx context.Context, s SignedTransaction) bool {
	if a == nil || ctx == nil {
		return false
	}
	g, _ := ctx.Value(custodyGrantContextKey{}).(*custodyExecutionGrant)
	return g != nil && g.authority == a && g.signedHash != "" && g.signedHash == s.Hash && strings.EqualFold(custodySHA(s.Bytes), s.Hash) && g.current(ctx)
}

func (g *custodyExecutionGrant) covers(r TransferRequest) bool {
	amount, ok := reserveUint(r.AmountUWolo)
	fee, feeOK := reserveUint(g.authority.config.FeesUWolo)
	free, freeOK := reserveUint(g.reserve.UncommittedUWolo)
	return ok && feeOK && freeOK && new(big.Int).Add(amount, fee).Cmp(free) <= 0
}
