package nativeverifier

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"strings"
	"time"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

// Verify is offline and non-signing. Pins and runtime identity must come from
// protected installation IO; stdin cannot enroll an authority. Nothing is stored
// or globally consumed by this stateless boundary.
func Verify(ctx context.Context, p Pins, identity Identity, raw []byte) (Verdict, error) {
	if ctx == nil {
		return Verdict{}, reject("NATIVE_VERIFIER_TIMEOUT")
	}
	ctx, cancel := context.WithTimeout(ctx, 4*time.Second)
	defer cancel()
	fail := func(code string) (Verdict, error) {
		if ctx.Err() != nil {
			code = "NATIVE_VERIFIER_TIMEOUT"
		}
		return Verdict{}, reject(code)
	}
	if ctx.Err() != nil {
		return fail("NATIVE_VERIFIER_TIMEOUT")
	}
	if e := ValidatePins(p); e != nil {
		return Verdict{}, e
	}
	if identity != p.ExpectedIdentity || identity.Modified {
		return fail("NATIVE_VERIFIER_IDENTITY_MISMATCH")
	}
	if len(raw) > MaxBundleBytes {
		return fail("NATIVE_VERIFIER_INPUT_TOO_LARGE")
	}
	var b Bundle
	if e := strictJSON(raw, MaxBundleBytes, &b); e != nil {
		return Verdict{}, e
	}
	if b.Version != 1 || !validTxHash(b.TxHash) || !identifier.MatchString(b.EconomicKey) {
		return fail("NATIVE_VERIFIER_INPUT_INVALID")
	}
	verifier, e := satchel.NewProofVerifier(p.Policy.TrustAnchor)
	if e != nil {
		return fail("NATIVE_VERIFIER_ANCHOR_INVALID")
	}
	var selected satchel.AuthenticatedEvidence
	var intent satchel.TransferIntent
	var owner, principal string
	expires := time.Now().Add(120 * time.Second)
	var latest int64
	// Existing exact request/ticket validators authenticate all immutable legs and
	// the full original owner mandate before selecting any economic effect.
	switch b.Purpose {
	case "wager_funding", "escrow_return", "fee":
		if b.Request == nil || b.Deposit != nil || b.Withdrawal != nil {
			return fail("NATIVE_VERIFIER_PURPOSE_INVALID")
		}
		r := *b.Request
		if p.Policy.ValidateRequest(r, time.Now()) != nil || !enrolled(p, r.OwnerUID, r.OwnerWallet, r.OwnerPublicKeyHex) {
			return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
		}
		owner = r.OwnerUID
		expires = minTime(expires, time.Unix(r.ExpiresAt, 0))
		if len(b.Funding) != len(r.Tickets) {
			return fail("NATIVE_VERIFIER_FUNDING_INVALID")
		}
		found := false
		for _, t := range r.Tickets {
			if !enrolled(p, t.OwnerUID, t.OwnerWallet, t.OwnerPublicKeyHex) {
				return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
			}
			proof, ok := b.Funding[t.FundingTxHash]
			if !ok {
				return fail("NATIVE_VERIFIER_FUNDING_INVALID")
			}
			in := satchel.TransferIntent{Sender: p.Policy.Vault, Recipient: p.Policy.Escrow, AmountUWolo: t.OriginalFundingPrincipalUWolo, Memo: epochescrow.FundingMemo(p.Policy.EpochID, t.TicketID)}
			ev, err := verifier.VerifyMessageTransferProof(ctx, in, t.FundingTxHash, proof)
			if err != nil || !receiptValid(ev, t.FundingTxHash, p.Policy.HStar) {
				return fail("NATIVE_VERIFIER_FUNDING_INVALID")
			}
			if ev.Observation().Height > latest {
				latest = ev.Observation().Height
			}
			if t.TicketID == r.TicketID {
				principal = t.OriginalFundingPrincipalUWolo
			}
			if b.Purpose == "wager_funding" && b.TxHash == t.FundingTxHash {
				if ProofDigest(b.Effect) != ProofDigest(proof) || b.EconomicKey != epochescrow.OriginalOperationID(p.Policy.EpochID, t.TicketID) {
					return fail("NATIVE_VERIFIER_FUNDING_INVALID")
				}
				selected = ev
				intent = in
				owner = t.OwnerUID
				principal = t.OriginalFundingPrincipalUWolo
				found = true
			}
		}
		if b.Purpose == "wager_funding" {
			if !found {
				return fail("NATIVE_VERIFIER_ECONOMIC_KEY_INVALID")
			}
		} else {
			if b.EconomicKey != r.OperationID || (b.Purpose == "escrow_return" && r.Command != epochescrow.ReturnCommand) || (b.Purpose == "fee" && r.Command != epochescrow.FeeCommand) || b.Preparation == nil {
				return fail("NATIVE_VERIFIER_ECONOMIC_KEY_INVALID")
			}
			// Authenticate the signed historical preparation bank event separately.
			// Its H/H+1 is never used as the current post-effect root below.
			if e := verifyPreparationBanks(ctx, verifier, p.Policy, r, *b.Preparation, b.Funding, latest); e != nil {
				return fail("NATIVE_VERIFIER_PREPARATION_INVALID")
			}
			if _, exists := b.Funding[b.TxHash]; exists {
				return fail("NATIVE_VERIFIER_DUPLICATE_PHYSICAL_RECEIPT")
			}
			intent = satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}
			selected, e = verifier.VerifyMessageTransferProof(ctx, intent, b.TxHash, b.Effect)
			if e != nil || !receiptValid(selected, b.TxHash, p.Policy.HStar) || selected.Observation().Height <= r.BankCommitHeight {
				return fail("NATIVE_VERIFIER_EFFECT_INVALID")
			}
		}
	case "deposit":
		if b.Deposit == nil || b.Request != nil || b.Withdrawal != nil || len(b.Funding) != 0 || b.Preparation != nil {
			return fail("NATIVE_VERIFIER_PURPOSE_INVALID")
		}
		d := *b.Deposit
		now := time.Now().Unix()
		key, _ := hex.DecodeString(d.OwnerPublicKeyHex)
		sig, se := base64.StdEncoding.Strict().DecodeString(d.OwnerSignature)
		if d.PolicySHA256 != epochescrow.PolicyDigest(p.Policy) || d.EpochID != p.Policy.EpochID || d.EconomicKey != b.EconomicKey || d.TxHash != b.TxHash || !enrolled(p, d.OwnerUID, d.OwnerWallet, d.OwnerPublicKeyHex) || d.IssuedAt <= 0 || d.IssuedAt > now || d.ExpiresAt <= now || d.ExpiresAt <= d.IssuedAt || d.ExpiresAt-d.IssuedAt > 120 || se != nil || len(sig) != 64 || base64.StdEncoding.EncodeToString(sig) != d.OwnerSignature || !(&secp.PubKey{Key: key}).VerifySignature(DepositMandateMessage(d), sig) {
			return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
		}
		if _, err := canonicalAmount(d.AmountUWolo, true); err != nil {
			return fail("NATIVE_VERIFIER_AMOUNT_INVALID")
		}
		selected, e = verifier.VerifyDepositProof(ctx, satchel.Intent{OwnerID: d.OwnerUID, Sender: d.OwnerWallet, Vault: p.Policy.Vault, AmountUWolo: d.AmountUWolo, Memo: d.Memo, CreatedAt: time.Unix(d.IssuedAt, 0), ExpiresAt: time.Unix(d.ExpiresAt, 0)}, b.TxHash, b.Effect)
		if e != nil || !receiptValid(selected, b.TxHash, p.Policy.HStar) {
			return fail("NATIVE_VERIFIER_EFFECT_INVALID")
		}
		intent = satchel.TransferIntent{Sender: d.OwnerWallet, Recipient: p.Policy.Vault, AmountUWolo: d.AmountUWolo, Memo: d.Memo}
		owner = d.OwnerUID
		principal = d.AmountUWolo
		expires = minTime(expires, time.Unix(d.ExpiresAt, 0))
	case "withdrawal":
		if b.Withdrawal == nil || b.Request != nil || b.Deposit != nil || len(b.Funding) != 0 || b.Preparation != nil {
			return fail("NATIVE_VERIFIER_PURPOSE_INVALID")
		}
		r := *b.Withdrawal
		k, _ := hex.DecodeString(p.FinancialKeys.WithdrawalApprovalKeyHex)
		wp := satchelservice.Policy{Vault: p.Policy.Vault, BettingEscrow: p.Policy.Escrow, ProtectedAddresses: []string{p.Policy.Escrow, p.Policy.FeeRecipient}, MaxAmountUWolo: 50000000000, WithdrawalApprovalKey: k}
		n, ne := canonicalAmount(r.AmountUWolo, true)
		if r.OwnerMandate == nil || r.Approval == nil || r.Reservation != nil || r.Kind != "withdrawal" || r.ChainID != satchel.ChainID || r.Denom != satchel.Denom || r.Sender != p.Policy.Vault || r.Recipient == p.Policy.Escrow || r.Recipient == p.Policy.FeeRecipient || satchel.IsKnownRoleAddress(r.Recipient) || r.OperationID != b.EconomicKey || ne != nil || n > wp.MaxAmountUWolo || wp.VerifyWithdrawal(r) != nil {
			return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
		}
		pub, pe := base64.StdEncoding.Strict().DecodeString(r.OwnerMandate.PubKey.Value)
		if pe != nil || !enrolled(p, r.OwnerID, r.Recipient, hex.EncodeToString(pub)) {
			return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
		}
		selected, e = verifier.VerifyMessageTransferProof(ctx, satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, b.TxHash, b.Effect)
		if e != nil || !receiptValid(selected, b.TxHash, p.Policy.HStar) {
			return fail("NATIVE_VERIFIER_EFFECT_INVALID")
		}
		intent = satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}
		owner = r.OwnerID
		principal = r.AmountUWolo
		expires = minTime(expires, time.Unix(r.Approval.ExpiresAt, 0))
	default:
		return fail("NATIVE_VERIFIER_PURPOSE_UNSUPPORTED")
	}
	if selected.Observation().Height > latest {
		latest = selected.Observation().Height
	}
	vault, e := verifier.VerifyBankProof(ctx, p.Policy.Vault, b.VaultBank.Height, b.VaultBank)
	if e != nil {
		return fail("NATIVE_VERIFIER_BANK_INVALID")
	}
	escrow, e := verifier.VerifyBankProof(ctx, p.Policy.Escrow, b.EscrowBank.Height, b.EscrowBank)
	if e != nil {
		return fail("NATIVE_VERIFIER_BANK_INVALID")
	}
	completed := time.Now().UTC()
	if !sameBankRoot(vault, escrow) || !vault.CurrentAt(completed) || !escrow.CurrentAt(completed) || vault.Height() <= p.Policy.HStar || latest > 9007199254740989 || vault.Height() < latest+2 || vault.CommitHeight() > 9007199254740991 {
		return fail("NATIVE_VERIFIER_BANK_ROOT_OR_FRESHNESS_INVALID")
	}
	if b.Request != nil && p.Policy.ValidateRequest(*b.Request, completed) != nil {
		return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
	}
	if b.Withdrawal != nil {
		k, _ := hex.DecodeString(p.FinancialKeys.WithdrawalApprovalKeyHex)
		if (satchelservice.Policy{Vault: p.Policy.Vault, WithdrawalApprovalKey: k}).VerifyWithdrawal(*b.Withdrawal) != nil {
			return fail("NATIVE_VERIFIER_OWNER_OR_PERMIT_INVALID")
		}
	}
	expires = minTime(expires, vault.ExpiresAt())
	expires = minTime(expires, escrow.ExpiresAt())
	vr, er, reviewExpiry, err := verifyReviews(completed, p, b, vault, escrow)
	if err != nil {
		return fail("NATIVE_VERIFIER_RESERVE_INVALID")
	}
	expires = minTime(expires, reviewExpiry)
	captureExpiry, err := verifyCaptures(completed, p, b, vault)
	if err != nil {
		return fail("NATIVE_VERIFIER_CAPTURE_INVALID")
	}
	expires = minTime(expires, captureExpiry)
	// Completion is sampled after all checks; neither replay nor CPU work renews a
	// native, owner, observer or reviewer expiry.
	completed = time.Now().UTC()
	if ctx.Err() != nil {
		return fail("NATIVE_VERIFIER_TIMEOUT")
	}
	if !completed.Before(expires) || !vault.CurrentAt(completed) || !escrow.CurrentAt(completed) {
		return fail("NATIVE_VERIFIER_EXPIRED")
	}
	o := selected.Observation()
	out := Verdict{WireVersion: 1, Protocol: epochescrow.Protocol, NativeVerdict: "COMET_ICS23_NATIVE_VERIFIED", ChainID: satchel.ChainID, Denom: satchel.Denom, EpochID: p.Policy.EpochID, OwnerUID: owner, Purpose: b.Purpose, EconomicKey: b.EconomicKey, AmountUWolo: intent.AmountUWolo, Sender: intent.Sender, Recipient: intent.Recipient, Memo: intent.Memo, TxHash: o.TxHash, MessageIndex: 0, MessageOrdinalKind: "SDK_MSG_SEND", FundingHeight: o.Height, ChainTime: o.BlockTime.UTC().Format(time.RFC3339Nano), TxSuccessProven: true, NativeConsensusAuthenticated: true, NativeICS23Authenticated: true, FundingMessageCount: 1, OriginalFundingPrincipalUWolo: principal, PrimaryHeadHeight: vault.HeadHeight(), WitnessHeadHeight: vault.CommitHeight(), BankStateHeight: vault.Height(), BankCommitHeight: vault.CommitHeight(), BlockSHA256: strings.ToUpper(vault.BlockHash()), AppSHA256: strings.ToUpper(vault.AppHash()), VaultAddress: p.Policy.Vault, EscrowAddress: p.Policy.Escrow, VaultBank: vr, EscrowBank: er, NativeVerifierSource: identity.SourceCommit, NativeVerifierBinarySHA256: identity.BinarySHA256, TrustAnchorSHA256: TrustAnchorDigest(p.Policy.TrustAnchor), RawProofBundleSHA256: hashBytes(raw), OwnerMandateAuthenticated: true, ProofSHA256: ProofDigest(b.Effect), ObservedAt: completed.Format(time.RFC3339Nano), ExpiresAt: expires.UTC().Format(time.RFC3339Nano), DisposableTestOnly: p.Mode == ModeDisposableTest, ProductionTrustEnrolled: p.ProductionTrustEnrolled}
	out.TxHash = strings.ToUpper(out.TxHash)
	out.VerificationRecordSHA256 = VerificationRecordDigest(out)
	return out, nil
}
func minTime(a, b time.Time) time.Time {
	if b.Before(a) {
		return b
	}
	return a
}
func validTxHash(s string) bool {
	return len(s) == 64 && s == strings.ToUpper(s) && validDigest(strings.ToLower(s))
}
func receiptValid(e satchel.AuthenticatedEvidence, hash string, hstar int64) bool {
	return e.ConsensusAuthenticated() && !e.CreditAuthorized() && e.Observation().Height > hstar && e.Receipt().TransferIndex == 0 && e.Receipt().ID() == "wolo-1:"+hash+":0"
}
func sameBankRoot(a, b satchel.AuthenticatedBankEvidence) bool {
	return a.Height() == b.Height() && a.CommitHeight() == b.CommitHeight() && a.BlockHash() == b.BlockHash() && a.AppHash() == b.AppHash() && a.HeadHeight() == b.HeadHeight() && a.HeadBlockHash() == b.HeadBlockHash() && !a.CreditAuthorized() && !b.CreditAuthorized()
}
func verifyPreparationBanks(ctx context.Context, v *satchel.ProofVerifier, p epochescrow.Policy, r epochescrow.Request, proofs epochescrow.Proofs, funding map[string]satchel.PortableProof, latest int64) error {
	if len(proofs.Funding) != len(funding) {
		return reject("NATIVE_VERIFIER_PREPARATION_INVALID")
	}
	for hash, proof := range funding {
		other, ok := proofs.Funding[hash]
		if !ok || ProofDigest(other) != ProofDigest(proof) {
			return reject("NATIVE_VERIFIER_PREPARATION_INVALID")
		}
	}
	a, e := v.VerifyBankProof(ctx, p.Vault, proofs.Vault.Height, proofs.Vault)
	if e != nil {
		return e
	}
	b, e := v.VerifyBankProof(ctx, p.Escrow, proofs.Escrow.Height, proofs.Escrow)
	if e != nil {
		return e
	}
	if !sameBankRoot(a, b) || a.Height() != r.BankStateHeight || a.CommitHeight() != r.BankCommitHeight || a.BlockHash() != r.BankCommitHash || a.AppHash() != r.BankAppHash || a.Height() < latest+2 {
		return reject("NATIVE_VERIFIER_PREPARATION_INVALID")
	}
	debit, de := canonicalAmount(r.AmountUWolo, true)
	gas, ge := canonicalAmount(p.GasFeeUWolo, true)
	if de != nil || ge != nil || debit > chainCap-gas {
		return reject("NATIVE_VERIFIER_PREPARATION_INVALID")
	}
	if !covers(r.VaultReserve, p.Vault, a.BalanceUWolo(), 0) || !covers(r.EscrowReserve, p.Escrow, b.BalanceUWolo(), debit+gas) {
		return reject("NATIVE_VERIFIER_PREPARATION_INVALID")
	}
	return nil
}
func covers(r epochescrow.Reserve, account, balance string, debit uint64) bool {
	if r.Account != account || !validDigest(r.InventorySHA256) || !validDigest(r.NonOverlapSHA256) {
		return false
	}
	bank, e := canonicalAmount(balance, false)
	if e != nil {
		return false
	}
	total := debit
	for i, s := range []string{r.LiabilitiesUWolo, r.MaximumUnknownOutflowUWolo, r.GasReserveUWolo, r.OperatingFloorUWolo} {
		n, e := canonicalAmount(s, i >= 2)
		if e != nil || n > chainCap-total {
			return false
		}
		total += n
	}
	return bank >= total
}
