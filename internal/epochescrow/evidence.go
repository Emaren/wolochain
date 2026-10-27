package epochescrow

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

// Proofs contains portable native transcripts, not caller-asserted balances or
// receipt booleans. The verifier is always built from the protected policy root.
type Proofs struct {
	Funding map[string]satchel.PortableProof `json:"funding"`
	Vault   satchel.BankProof                `json:"vault"`
	Escrow  satchel.BankProof                `json:"escrow"`
}

// VerifiedPreparation cannot be constructed by a transport or config decoder.
// Its zero value has no journal admission authority. It grants no signing power.
type VerifiedPreparation struct {
	policy      Policy
	request     Request
	fingerprint string
	expiresAt   time.Time
	verified    bool
}

func (v VerifiedPreparation) Fingerprint() string { return v.fingerprint }

func VerifyPreparation(ctx context.Context, p Policy, r Request, proofs Proofs) (VerifiedPreparation, error) {
	if ctx == nil || ctx.Err() != nil {
		return VerifiedPreparation{}, errors.New("epoch_context_unavailable")
	}
	now := time.Now()
	if e := p.ValidateRequest(r, now); e != nil {
		return VerifiedPreparation{}, e
	}
	verifier, e := satchel.NewProofVerifier(p.TrustAnchor)
	if e != nil {
		return VerifiedPreparation{}, e
	}
	refuse := func() (VerifiedPreparation, error) {
		return VerifiedPreparation{}, blocked("BANK_PROOF_STALE", "Native funding or same-root current account proofs are missing or inconsistent.", "refresh-native-proofs")
	}
	if len(proofs.Funding) != len(r.Plan.Wagers) {
		return refuse()
	}
	var latestFundingHeight int64
	for _, w := range r.Plan.Wagers {
		proof, ok := proofs.Funding[w.FundingTxHash]
		if !ok {
			return refuse()
		}
		ev, e := verifier.VerifyTransferProof(ctx, satchel.TransferIntent{Sender: p.Vault, Recipient: p.Escrow, AmountUWolo: w.PrincipalUWolo, Memo: FundingMemo(p.EpochID, w.TicketID)}, w.FundingTxHash, proof)
		if e != nil || !ev.ConsensusAuthenticated() || ev.CreditAuthorized() || ev.Observation().Height <= p.HStar || ev.Receipt().TransferIndex != 0 || ev.Receipt().ID() != "wolo-1:"+w.FundingTxHash+":0" {
			return refuse()
		}
		if ev.Observation().Height > latestFundingHeight {
			latestFundingHeight = ev.Observation().Height
		}
	}
	vault, e := verifier.VerifyBankProof(ctx, p.Vault, proofs.Vault.Height, proofs.Vault)
	if e != nil {
		return refuse()
	}
	escrow, e := verifier.VerifyBankProof(ctx, p.Escrow, proofs.Escrow.Height, proofs.Escrow)
	if e != nil {
		return refuse()
	}
	// Both accounts must be committed under the same current H+1 header/root.
	if !vault.CurrentAt(now) || !escrow.CurrentAt(now) || vault.CreditAuthorized() || escrow.CreditAuthorized() || vault.Height() != escrow.Height() || vault.CommitHeight() != escrow.CommitHeight() || vault.AppHash() != escrow.AppHash() || vault.BlockHash() != escrow.BlockHash() || vault.HeadHeight() != escrow.HeadHeight() || vault.HeadBlockHash() != escrow.HeadBlockHash() || vault.Height() <= p.HStar || vault.Height() < latestFundingHeight+2 || vault.Height() != r.BankStateHeight || vault.CommitHeight() != r.BankCommitHeight || vault.BlockHash() != r.BankCommitHash || vault.AppHash() != r.BankAppHash {
		return refuse()
	}
	debit, _ := number(r.AmountUWolo, false)
	gas, _ := number(p.GasFeeUWolo, false)
	if !reserveCovers(r.VaultReserve, p.Vault, vault.BalanceUWolo(), 0) || !reserveCovers(r.EscrowReserve, p.Escrow, escrow.BalanceUWolo(), debit+gas) {
		return VerifiedPreparation{}, blocked("RESERVE_COVERAGE_DEFICIT", "Each account must cover its own complete liabilities, unknown outflows, gas, floor and exact debit.", "reconcile-account-local-liabilities")
	}
	// Freeze all caller-owned slices before retaining authenticated authority.
	var frozen struct {
		Policy  Policy
		Request Request
	}
	b, _ := json.Marshal(struct {
		Policy  Policy
		Request Request
	}{p, r})
	if json.Unmarshal(b, &frozen) != nil {
		return refuse()
	}
	expires := time.Unix(r.ExpiresAt, 0)
	for _, t := range []time.Time{vault.ExpiresAt(), escrow.ExpiresAt()} {
		if t.Before(expires) {
			expires = t
		}
	}
	if ctx.Err() != nil || !time.Now().Before(expires) {
		return refuse()
	}
	return VerifiedPreparation{frozen.Policy, frozen.Request, Fingerprint(frozen.Request), expires, true}, nil
}
func reserveCovers(r Reserve, account, balance string, debit uint64) bool {
	if r.Account != account || !digest(r.InventorySHA256) || !digest(r.NonOverlapSHA256) {
		return false
	}
	bank, e := number(balance, true)
	if e != nil {
		return false
	}
	total := debit
	for i, s := range []string{r.LiabilitiesUWolo, r.MaximumUnknownOutflowUWolo, r.GasReserveUWolo, r.OperatingFloorUWolo} {
		n, e := number(s, i < 2)
		if e != nil {
			return false
		}
		total += n
	}
	return bank >= total
}

// ObserveReturn authenticates one exact v3 physical effect without posting a
// credit or consuming an HD receipt. Native bank state and economic ownership
// must subsequently be consumed atomically by HD's global accounting authority.
func ObserveReturn(ctx context.Context, p Policy, r Request, hash string, proof satchel.PortableProof) (satchel.AuthenticatedEvidence, error) {
	if ctx == nil || ctx.Err() != nil || r.Command != ReturnCommand || !txhash(hash) {
		return satchel.AuthenticatedEvidence{}, errors.New("epoch_return_observation_refused")
	}
	if e := p.ValidateRequest(r, time.Unix(r.IssuedAt, 0)); e != nil {
		return satchel.AuthenticatedEvidence{}, e
	}
	v, e := satchel.NewProofVerifier(p.TrustAnchor)
	if e != nil {
		return satchel.AuthenticatedEvidence{}, e
	}
	evidence, e := v.VerifyTransferProof(ctx, satchel.TransferIntent{Sender: p.Escrow, Recipient: p.Vault, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, hash, proof)
	if e != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || evidence.Observation().Height <= p.HStar || evidence.Receipt().TransferIndex != 0 || evidence.Receipt().ID() != "wolo-1:"+strings.ToUpper(hash)+":0" || hash == r.FundingTxHash {
		return satchel.AuthenticatedEvidence{}, errors.New("epoch_return_observation_refused")
	}
	return evidence, nil
}
