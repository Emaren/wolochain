package satchelservice

// Qualified escrow-account execution binds the EXISTING sealed reserve-review
// issuer, exclusive vault journal, distinct native escrow keyring and #122's
// durable sign/broadcast fence. This is an internal runtime composition point,
// NOT a new listener, permit authority, or enabled financial deployment.
import (
	"context"
	"errors"
	"path/filepath"

	"github.com/emaren/wolochain/internal/chainjson"
)

var ErrEscrowRuntimeHeld = errors.New("escrow_return_runtime_not_authorized")

// ExecuteEnrolledEscrowReturn can only use a separately leased native SDK
// escrow-account signer. The engine already has an independently enrolled
// custody issuer; its signed bank/reserve review is requalified for the exact
// previously PREPARED original return. No public request can supply a sender,
// destination, signer, reserve balance or executable approval.
func (e *Engine) ExecuteEnrolledEscrowReturn(
	ctx context.Context, approval ReturnApproval, signer *KeyringBackend,
	external EscrowReturnSpendGuard,
) (EscrowReturnSpendResult, error) {
	none := EscrowReturnSpendResult{}
	if e == nil || e.db == nil || e.custodyAuthority == nil ||
		ctx == nil || ctx.Err() != nil || signer == nil ||
		external.Permit == nil || external.PreBroadcast == nil {
		return none, ErrEscrowRuntimeHeld
	}
	escrowBoundary(ctx, "enrolled_signer")
	issuer := e.custodyAuthority
	if issuer.engine != e || issuer.native == nil || signer == issuer.native ||
		signer.cfg.Vault != e.policy.BettingEscrow ||
		signer.cfg.ReturnDestination != e.policy.Vault ||
		len(signer.cfg.ApprovedDestinations) != 1 ||
		signer.cfg.ApprovedDestinations[0] != e.policy.Vault ||
		len(signer.cfg.ProtectedAddresses) != 1 ||
		signer.cfg.ProtectedAddresses[0] != e.policy.Vault ||
		signer.cfg.ReturnVerifier == nil ||
		signer.cfg.AuthorizeSign == nil || signer.cfg.AuthorizeBroadcast == nil ||
		signer.cfg.ConfirmTransaction == nil ||
		filepath.Clean(signer.cfg.KeyringDir) == filepath.Clean(issuer.native.cfg.KeyringDir) ||
		signer.cfg.KeyName == issuer.native.cfg.KeyName ||
		signer.cfg.PassphraseFile == issuer.native.cfg.PassphraseFile ||
		signer.cfg.KeyringDir == "" || !escrowKeyringLeaseCurrent(signer) {
		return none, ErrEscrowRuntimeHeld
	}
	// Qualify AFTER original claim preparation, against its NEW current Bolt
	// snapshot; before first intent write, any stale reserve review fails.
	escrowBoundary(ctx, "engine_lock")
	e.mu.Lock()
	qualified, err := issuer.qualifyEscrowReturnLocked(ctx, approval)
	e.mu.Unlock()
	if err != nil || !qualified.CurrentFor(ctx, approval) {
		return none, ErrEscrowRuntimeHeld
	}
	// Each irreversible transition uses live signed-file/config and independent
	// escrow-review byte identity, not cached affirmative booleans from the
	// original HTTP preparation. After durable intent the journal necessarily
	// changes, so no second spend qualification is synthesized.
	current := func(ctx context.Context, req TransferRequest) bool {
		if ctx == nil || ctx.Err() != nil ||
			req.Kind != "claim_return" || req.Sender != e.policy.BettingEscrow ||
			req.Recipient != e.policy.Vault ||
			req.OperationID != "satchel:claim-return:"+approval.ClaimID ||
			req.AmountUWolo != approval.AmountUWolo ||
			req.ReturnApproval == nil || hashJSON(*req.ReturnApproval) != hashJSON(approval) ||
			!qualified.now().Before(qualified.expires) ||
			!qualified.bank.CurrentAt(qualified.now()) || !escrowKeyringLeaseCurrent(signer) {
			return false
		}
		if _, _, err := issuer.currentFiles(ctx); err != nil || !issuer.nativeLeaseHeld() {
			return false
		}
		raw, err := ReadPrivateFile(issuer.config.EscrowReturnExecutionFile, 64<<10)
		if err != nil || custodySHA(raw) != issuer.config.EscrowReturnExecutionSHA256 ||
			!chainjson.ValidFolded(raw) {
			return false
		}
		var enrollment escrowReturnRuntimeEnrollment
		if strictHTTPJSON(raw, &enrollment) != nil ||
			enrollment.Version != 1 || enrollment.Scope != escrowReturnEnrollmentScope {
			return false
		}
		signed, err := readPrivateFileBounded(enrollment.ReviewFile,
			escrowReturnExecutionMaxBytes, escrowReturnExecutionMaxBytes)
		if err != nil || !chainjson.ValidFolded(signed) {
			return false
		}
		var bundle EscrowReturnExecutionBundle
		completed := qualified.now() // after all lease and file I/O
		return strictHTTPJSON(signed, &bundle) == nil &&
			hashJSON(bundle) == qualified.bundleHash && ctx.Err() == nil &&
			completed.Before(qualified.expires) && qualified.bank.CurrentAt(completed)
	}
	guards := EscrowReturnSpendGuard{
		Permit: func(ctx context.Context, req TransferRequest) bool {
			return current(ctx, req) && external.Permit(ctx, req)
		},
		PreBroadcast: func(ctx context.Context, req TransferRequest, tx SignedTransaction) bool {
			return current(ctx, req) &&
				external.PreBroadcast(ctx, req, tx)
		},
	}
	escrowBoundary(ctx, "durable_intent")
	return e.ExecuteQualifiedEscrowReturn(ctx, approval, qualified, signer, guards)
}

// Inspect the native lease without claiming the lease's separate authority.
// Never touch a legacy 8092 signer or accept a mock backend with no keyring.
func escrowKeyringLeaseCurrent(b *KeyringBackend) bool {
	if b == nil {
		return false
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	return !b.closed.Load() && b.signer != nil &&
		b.keyringLease != nil && b.keyringLeaseCurrent()
}
