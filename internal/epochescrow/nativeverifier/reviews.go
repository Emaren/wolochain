package nativeverifier

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"strconv"
	"strings"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

func verifyReviews(now time.Time, p Pins, b Bundle, vault, escrow satchel.AuthenticatedBankEvidence) (BankVerdict, BankVerdict, time.Time, error) {
	bad := func() (BankVerdict, BankVerdict, time.Time, error) {
		return BankVerdict{}, BankVerdict{}, time.Time{}, reject("NATIVE_VERIFIER_RESERVE_INVALID")
	}
	i := b.Inventory
	if i.Version != 1 || i.EpochID != p.Policy.EpochID || i.StateHeight != vault.Height() || i.CommitBlockHash != strings.ToUpper(vault.BlockHash()) || i.AppHash != strings.ToUpper(vault.AppHash()) || len(i.Sources) != len(p.RequiredLiabilitySources) || len(i.Claims) == 0 || len(i.Claims) > 8192 || len(b.Reviews) != 2 {
		return bad()
	}
	sources := map[string]bool{}
	for n, s := range i.Sources {
		if s.SourceID != p.RequiredLiabilitySources[n] || !validDigest(s.SnapshotSHA256) {
			return bad()
		}
		sources[s.SourceID] = true
	}
	// A global claim ID is never counted twice, even across accounts or sources.
	// Explicit confirmed zero is permitted to make absent source exposure visible;
	// every pinned source must state exposure for each account.
	sums := map[string]uint64{"vault:confirmed": 0, "vault:unknown": 0, "escrow:confirmed": 0, "escrow:unknown": 0}
	coverage := map[string]bool{}
	prev := ""
	for _, c := range i.Claims {
		if !identifier.MatchString(c.ClaimID) || c.ClaimID <= prev || !sources[c.SourceID] || (c.AccountRole != "vault" && c.AccountRole != "escrow") || (c.Kind != "confirmed" && c.Kind != "unknown") {
			return bad()
		}
		prev = c.ClaimID
		n, e := canonicalAmount(c.AmountUWolo, c.Kind == "unknown")
		key := c.AccountRole + ":" + c.Kind
		if e != nil || n > chainCap-sums[key] {
			return bad()
		}
		sums[key] += n
		coverage[c.SourceID+":"+c.AccountRole] = true
	}
	for _, s := range i.Sources {
		for _, role := range []string{"vault", "escrow"} {
			if !coverage[s.SourceID+":"+role] {
				return bad()
			}
		}
	}
	for _, role := range []string{"vault", "escrow"} {
		if sums[role+":unknown"] == 0 {
			return bad()
		}
	}
	keys := p.FinancialKeys
	decode := func(s string) ed25519.PublicKey { b, _ := hex.DecodeString(s); return ed25519.PublicKey(b) }
	authority := satchelservice.ReserveReviewAuthority{AccountingReviewerKey: decode(keys.AccountingReviewerKeyHex), CustodyReviewerKey: decode(keys.CustodyReviewerKeyHex), ExecutionAuthorityKey: decode(keys.ExecutionAuthorityKeyHex), WagerApprovalKey: decode(keys.WagerApprovalKeyHex), WithdrawalApprovalKey: decode(keys.WithdrawalApprovalKeyHex), ExpectedBuildSHA256: p.ExpectedIdentity.BinarySHA256, ExpectedConfigSHA256: p.ConfigSHA256, ExpectedPermitSHA256: PermitDigest(b)}
	expires := now.Add(120 * time.Second)
	seen := map[string]bool{}
	out := map[string]BankVerdict{}
	for _, entry := range b.Reviews {
		role, r := entry.AccountRole, entry.Review
		if (role != "vault" && role != "escrow") || seen[role] || r.LiabilityInventorySHA256 != InventoryDigest(i) || r.NonOverlapWitnessSHA256 != NonOverlapDigest(i) || r.JournalSnapshotSHA256 != JournalSnapshotDigest(i) || r.ConfirmedLiabilitiesUWolo != strconv.FormatUint(sums[role+":confirmed"], 10) || r.UncertainMaxLiabilitiesUWolo != strconv.FormatUint(sums[role+":unknown"], 10) {
			return bad()
		}
		for idx, s := range []string{r.ObservedBankUWolo, r.ConfirmedLiabilitiesUWolo, r.UncertainMaxLiabilitiesUWolo, r.GasReserveUWolo, r.UnencumberedMinimumUWolo} {
			if _, e := canonicalAmount(s, idx >= 2); e != nil {
				return bad()
			}
		}
		bank, proof := vault, b.VaultBank
		if role == "escrow" {
			bank, proof = escrow, b.EscrowBank
		}
		authority.ExpectedVault = bank.VaultAddress()
		qualified, e := satchelservice.EvaluateProofBoundReserveReview(now, bank, r, authority)
		if e != nil || !qualified.Sufficient {
			return bad()
		}
		expires = minTime(expires, qualified.ExpiresAt)
		seen[role] = true
		out[role] = BankVerdict{AccountRole: role, Account: bank.VaultAddress(), BankStateHeight: bank.Height(), BankCommitHeight: bank.CommitHeight(), BlockSHA256: strings.ToUpper(bank.BlockHash()), AppSHA256: strings.ToUpper(bank.AppHash()), BankBalanceUWolo: bank.BalanceUWolo(), LiabilitiesUWolo: r.ConfirmedLiabilitiesUWolo, MaximumUnknownOutflowUWolo: r.UncertainMaxLiabilitiesUWolo, GasUWolo: r.GasReserveUWolo, OperatingFloorUWolo: r.UnencumberedMinimumUWolo, InventorySHA256: InventoryDigest(i), NonOverlapSHA256: NonOverlapDigest(i), ProofSHA256: BankProofDigest(proof)}
	}
	return out["vault"], out["escrow"], expires, nil
}
func verifyCaptures(now time.Time, p Pins, b Bundle, bank satchel.AuthenticatedBankEvidence) (time.Time, error) {
	bad := func() (time.Time, error) { return time.Time{}, reject("NATIVE_VERIFIER_CAPTURE_INVALID") }
	if len(b.Captures) != 2 {
		return bad()
	}
	pins := map[string]ObserverPin{}
	for _, o := range p.Observers {
		pins[o.Role] = o
	}
	seen := map[string]bool{}
	expiry := now.Add(120 * time.Second)
	payload := PayloadDigest(b)
	for _, c := range b.Captures {
		o, ok := pins[c.Role]
		if !ok || seen[c.Role] || c.Version != 1 || c.KeyID != o.KeyID || c.OperatorID != o.OperatorID || c.EndpointSHA256 != o.EndpointSHA256 || c.PayloadSHA256 != payload || c.StateHeight != bank.Height() || c.CommitHeight != bank.CommitHeight() || c.HeadHeight != bank.CommitHeight() || c.BlockSHA256 != strings.ToUpper(bank.BlockHash()) || c.AppSHA256 != strings.ToUpper(bank.AppHash()) || c.ObservedAt <= 0 || c.ObservedAt > now.Unix()+5 || now.Unix()-c.ObservedAt > 30 || c.ExpiresAt <= c.ObservedAt || c.ExpiresAt-c.ObservedAt > 120 || c.ExpiresAt <= now.Unix() || time.Unix(c.ExpiresAt, 0).After(bank.ExpiresAt()) {
			return bad()
		}
		key, _ := hex.DecodeString(o.PublicKeyHex)
		sig, e := base64.StdEncoding.Strict().DecodeString(c.Signature)
		if e != nil || len(sig) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(sig) != c.Signature || !ed25519.Verify(key, CaptureMessage(c), sig) {
			return bad()
		}
		seen[c.Role] = true
		expiry = minTime(expiry, time.Unix(c.ExpiresAt, 0))
	}
	return expiry, nil
}
