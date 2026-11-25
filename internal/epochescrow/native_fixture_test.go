package epochescrow

// The opt-in harness reuses satchel's continuous real SDK application/Comet
// exporter. Build before export, then consume without recompilation. All keys
// belong to that disposable fixture; the golden export contains public data only.
import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"runtime"
	"strings"
	"testing"
	"time"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/satchel"
)

type nativeV3Step struct {
	Name   string                `json:"name"`
	Hash   string                `json:"tx_hash"`
	Proof  satchel.PortableProof `json:"proof"`
	Vault  satchel.BankProof     `json:"vault_bank_proof"`
	Escrow satchel.BankProof     `json:"escrow_bank_proof"`
}

func TestNativeV3FeePayingProofPreparationAndObservation(t *testing.T) {
	path := os.Getenv("WOLO_EPOCH_NATIVE_FIXTURE")
	if path == "" {
		t.Skip("run scripts/check-epoch-escrow-native-v3.py for fresh native SDK proofs")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var f struct {
		FixtureOnly                bool                `json:"fixture_only"`
		MainnetAuthority           bool                `json:"mainnet_authority"`
		ProductionCustodyAvailable bool                `json:"production_custody_available"`
		Anchor                     satchel.TrustAnchor `json:"anchor"`
		Roles                      map[string]string   `json:"roles"`
		Steps                      []nativeV3Step      `json:"steps"`
	}
	if err = json.Unmarshal(data, &f); err != nil {
		t.Fatal(err)
	}
	if !f.FixtureOnly || f.MainnetAuthority || f.ProductionCustodyAvailable {
		t.Fatal("fixture cannot assert production authority")
	}
	steps := map[string]nativeV3Step{}
	for _, s := range f.Steps {
		steps[s.Name] = s
	}
	for _, name := range []string{"funding_one", "funding_two", "epoch_return", "epoch_fee", "epoch_void_return"} {
		if _, ok := steps[name]; !ok {
			t.Fatal("missing native step", name)
		}
	}
	one, two, returned, fee, voided := steps["funding_one"], steps["funding_two"], steps["epoch_return"], steps["epoch_fee"], steps["epoch_void_return"]
	p, r := fixture(t)
	p.Vault, p.Escrow = f.Roles["vault"], f.Roles["escrow"]
	p.VaultPublicKeyHex, p.EscrowPublicKeyHex = f.Roles["vault_public_key_hex"], f.Roles["escrow_public_key_hex"]
	p.FeeRecipient, p.GasFeeUWolo, p.TrustAnchor = f.Roles["fee_recipient"], "1", f.Anchor
	if source := os.Getenv("WOLO_EPOCH_SOURCE_COMMIT"); source != "" {
		p.SourceCommit = source
	}
	executable, err := os.Executable()
	if err != nil {
		t.Fatal("native test executable unavailable")
	}
	binary, err := os.Open(executable)
	if err != nil {
		t.Fatal("native test executable unreadable")
	}
	binaryDigest := sha256.New()
	_, err = io.Copy(binaryDigest, binary)
	closeErr := binary.Close()
	if err != nil || closeErr != nil {
		t.Fatal("native test executable checksum unavailable")
	}
	p.BinarySHA256 = hex.EncodeToString(binaryDigest.Sum(nil))
	disposableKey := func(role string) *secp.PrivKey {
		raw, e := hex.DecodeString(f.Roles[role+"_private_key_hex_test_only"])
		if e != nil || len(raw) != 32 {
			t.Fatal("missing disposable fixture owner key")
		}
		return &secp.PrivKey{Key: raw}
	}
	owner, opponent := disposableKey("owner"), disposableKey("opponent")
	signTicket := func(ticket *OriginalTicket, key *secp.PrivKey) {
		sig, e := key.Sign(OriginalTicketMessage(p, *ticket))
		if e != nil {
			t.Fatal(e)
		}
		ticket.OwnerSignature = base64.StdEncoding.EncodeToString(sig)
	}
	ownerTicket := OriginalTicket{EpochID: p.EpochID, TicketID: 200, OwnerUID: f.Roles["owner_id"], OwnerWallet: f.Roles["owner"], OwnerPublicKeyHex: f.Roles["owner_public_key_hex"], FundingTxHash: one.Hash, OriginalFundingPrincipalUWolo: "100000000", Allocations: []TicketAllocation{{MarketID: 77, LegID: 11, WagerID: 1, Side: "left", AmountUWolo: "40000000"}, {MarketID: 78, LegID: 12, WagerID: 2, Side: "left", AmountUWolo: "60000000"}}}
	opponentTicket := OriginalTicket{EpochID: p.EpochID, TicketID: 300, OwnerUID: f.Roles["opponent_id"], OwnerWallet: f.Roles["opponent"], OwnerPublicKeyHex: f.Roles["opponent_public_key_hex"], FundingTxHash: two.Hash, OriginalFundingPrincipalUWolo: "40000000", Allocations: []TicketAllocation{{MarketID: 77, LegID: 21, WagerID: 3, Side: "right", AmountUWolo: "40000000"}}}
	signTicket(&ownerTicket, owner)
	signTicket(&opponentTicket, opponent)
	r.OwnerUID, r.OwnerWallet, r.OwnerPublicKeyHex = ownerTicket.OwnerUID, ownerTicket.OwnerWallet, ownerTicket.OwnerPublicKeyHex
	r.WagerID, r.TicketID, r.MarketID, r.LegID = 1, 200, 77, 11
	r.OriginalOperationID = OriginalOperationID(p.EpochID, r.TicketID)
	r.EntitlementID = EntitlementID(p.EpochID, r.MarketID, r.TicketID, r.LegID)
	r.OperationID, r.Memo = r.EntitlementID+":return", ReturnMemo(p.EpochID, r.EntitlementID)
	r.Sender, r.Recipient, r.AmountUWolo, r.FundingTxHash = p.Escrow, p.Vault, "78000000", one.Hash
	r.PolicySHA256, r.SourceCommit, r.BinarySHA256 = PolicyDigest(p), p.SourceCommit, p.BinarySHA256
	r.Tickets = []OriginalTicket{ownerTicket, opponentTicket}
	r.OriginalMandateSHA256 = OriginalTicketDigest(p, ownerTicket)
	r.Plan = Plan{EpochID: p.EpochID, MarketID: 77, Resolution: "left", Wagers: []Wager{{1, 77, 200, 11, ownerTicket.OwnerUID, "left", "40000000", one.Hash, 0}, {3, 77, 300, 21, opponentTicket.OwnerUID, "right", "40000000", two.Hash, 0}}}
	r.VaultReserve.Account, r.EscrowReserve.Account = p.Vault, p.Escrow
	r.VaultReserve.LiabilitiesUWolo, r.EscrowReserve.LiabilitiesUWolo = "0", "62000000" // other return60 + economic fee2
	r.VaultReserve.GasReserveUWolo, r.EscrowReserve.GasReserveUWolo = "1", "1"
	verifier, err := satchel.NewProofVerifier(p.TrustAnchor)
	if err != nil {
		t.Fatal(err)
	}
	beforeReplay := time.Now()
	bank, err := verifier.VerifyBankProof(context.Background(), p.Vault, two.Vault.Height, two.Vault)
	if err != nil {
		t.Fatal(err)
	}
	escrowBank, err := verifier.VerifyBankProof(context.Background(), p.Escrow, two.Escrow.Height, two.Escrow)
	if err != nil {
		t.Fatal(err)
	}
	completedAt := time.Now()
	t.Logf("native_bank state=%d commit=%d head=%d escrow_state=%d escrow_commit=%d escrow_head=%d current_vault=%t current_escrow=%t app_root_equal=%t commit_hash_equal=%t head_hash_equal=%t before_replay_current=%t",
		bank.Height(), bank.CommitHeight(), bank.HeadHeight(), escrowBank.Height(), escrowBank.CommitHeight(), escrowBank.HeadHeight(), bank.CurrentAt(completedAt), escrowBank.CurrentAt(completedAt), bank.AppHash() == escrowBank.AppHash(), bank.BlockHash() == escrowBank.BlockHash(), bank.HeadBlockHash() == escrowBank.HeadBlockHash(), bank.CurrentAt(beforeReplay))
	if !bank.CurrentAt(completedAt) || !escrowBank.CurrentAt(completedAt) || bank.CurrentAt(beforeReplay) || escrowBank.CurrentAt(beforeReplay) {
		t.Fatal("genuine bank replay must be evaluated after its observations")
	}
	if bank.CurrentAt(completedAt.Add(31*time.Second)) || escrowBank.CurrentAt(completedAt.Add(31*time.Second)) {
		t.Fatal("completion-time evaluation extended native proof freshness")
	}
	if bank.CurrentAt(beforeReplay.Add(-6*time.Second)) || escrowBank.CurrentAt(beforeReplay.Add(-6*time.Second)) {
		t.Fatal("genuine bank evidence accepted observations from the future")
	}
	r.BankStateHeight, r.BankCommitHeight, r.BankCommitHash, r.BankAppHash = bank.Height(), bank.CommitHeight(), bank.BlockHash(), bank.AppHash()
	r.IssuedAt = time.Now().Unix()
	r.ExpiresAt = r.IssuedAt + 90
	sign := func(req *Request) {
		sig, e := owner.Sign(RequestMessage(*req))
		if e != nil {
			t.Fatal(e)
		}
		req.OwnerSignature = base64.StdEncoding.EncodeToString(sig)
		req.ReviewerSignature = base64.StdEncoding.EncodeToString(ed25519.Sign(ed25519.NewKeyFromSeed(bytes32(7)), RequestMessage(*req)))
	}
	sign(&r)
	proofs := Proofs{map[string]satchel.PortableProof{one.Hash: one.Proof, two.Hash: two.Proof}, two.Vault, two.Escrow}
	prepare := func(req Request, native Proofs) VerifiedPreparation {
		v, e := VerifyPreparation(context.Background(), p, req, native)
		if e != nil {
			var blocker *Blocker
			if errors.As(e, &blocker) {
				t.Logf("native_preparation code=%s cause=%s", blocker.Code, blocker.Cause)
			}
			t.Fatal("genuine fee-paying SDK funding/bank proofs refused", e)
		}
		return v
	}
	v := prepare(r, proofs)
	j, _ := journalFixture(t, p)
	defer j.Close()
	if d, e := j.Prepare(context.Background(), v); e != nil || d.Status != PreparedUnsigned {
		t.Fatal(d, e)
	}
	feeRequest := freezeRequest(r)
	feeRequest.Command, feeRequest.OperationID, feeRequest.Recipient, feeRequest.AmountUWolo = FeeCommand, r.EntitlementID+":fee", p.FeeRecipient, "2000000"
	feeRequest.Memo, feeRequest.Nonce = "aoe2war/satchel/epoch-v3/"+p.EpochID+"/fee/"+r.EntitlementID, strings.Repeat("e", 64)
	feeRequest.EscrowReserve.LiabilitiesUWolo = "138000000" // both principal returns
	sign(&feeRequest)
	if _, err = j.Prepare(context.Background(), prepare(feeRequest, proofs)); err != nil {
		t.Fatal(err)
	}
	voidRequest := freezeRequest(r)
	voidRequest.WagerID, voidRequest.MarketID, voidRequest.LegID = 2, 78, 12
	voidRequest.EntitlementID = EntitlementID(p.EpochID, 78, 200, 12)
	voidRequest.OperationID, voidRequest.Memo = voidRequest.EntitlementID+":return", ReturnMemo(p.EpochID, voidRequest.EntitlementID)
	voidRequest.AmountUWolo, voidRequest.Nonce = "60000000", strings.Repeat("f", 64)
	voidRequest.Plan = Plan{EpochID: p.EpochID, MarketID: 78, Resolution: "void", Wagers: []Wager{{2, 78, 200, 12, ownerTicket.OwnerUID, "left", "60000000", one.Hash, 0}}}
	voidRequest.Tickets = []OriginalTicket{ownerTicket}
	voidRequest.EscrowReserve.LiabilitiesUWolo = "80000000" // matched return78 + fee2
	sign(&voidRequest)
	voidProofs := Proofs{map[string]satchel.PortableProof{one.Hash: one.Proof}, two.Vault, two.Escrow}
	t.Run("global_partition_rebind", func(t *testing.T) {
		changed := freezeRequest(voidRequest)
		changed.Tickets[0].Allocations[0].AmountUWolo, changed.Tickets[0].Allocations[1].AmountUWolo = "41000000", "59000000"
		signTicket(&changed.Tickets[0], owner)
		changed.OriginalMandateSHA256 = OriginalTicketDigest(p, changed.Tickets[0])
		changed.Plan.Wagers[0].PrincipalUWolo, changed.AmountUWolo = "59000000", "59000000"
		changed.EscrowReserve.LiabilitiesUWolo = "81000000"
		sign(&changed)
		altered := prepare(changed, voidProofs)
		_, e := j.Prepare(context.Background(), altered)
		var blocker *Blocker
		if !errors.As(e, &blocker) || blocker.Code != "RETURN_ENTITLEMENT_COLLISION" {
			t.Fatal("already bound original receipt accepted a conserved but altered cross-market partition", e)
		}
	})
	if _, err = j.Prepare(context.Background(), prepare(voidRequest, voidProofs)); err != nil {
		t.Fatal("original ticket could not admit both immutable market legs", err)
	}
	authenticateEffect := func(req Request, step nativeV3Step) satchel.AuthenticatedEvidence {
		evidence, e := verifier.VerifyMessageTransferProof(context.Background(), satchel.TransferIntent{Sender: req.Sender, Recipient: req.Recipient, AmountUWolo: req.AmountUWolo, Memo: req.Memo}, step.Hash, step.Proof)
		if e != nil || !evidence.ConsensusAuthenticated() || evidence.Receipt().TransferIndex != 0 || evidence.CreditAuthorized() {
			t.Fatal("genuine native effect refused or credited", e)
		}
		if evidence.Observation().TransferIndex == nil || *evidence.Observation().TransferIndex != 1 {
			t.Fatal("canonical message identity changed native bank-event order")
		}
		legacy, e := verifier.VerifyTransferProof(context.Background(), satchel.TransferIntent{Sender: req.Sender, Recipient: req.Recipient, AmountUWolo: req.AmountUWolo, Memo: req.Memo}, step.Hash, step.Proof)
		if e != nil || legacy.Receipt().TransferIndex != 1 {
			t.Fatal("legacy event-ordinal API changed", e)
		}
		if req.Command == ReturnCommand {
			if _, e = ObserveReturn(context.Background(), p, req, step.Hash, step.Proof); e != nil {
				t.Fatal("native return observation refused", e)
			}
		}
		return evidence
	}
	returnEffect, feeEffect, voidEffect := authenticateEffect(r, returned), authenticateEffect(feeRequest, fee), authenticateEffect(voidRequest, voided)
	if _, err = j.Execute(context.Background(), r.OperationID, Fingerprint(r)); err == nil {
		t.Fatal("native proof substituted for independent custody authority")
	}
	for _, name := range []string{"wrong_message_ordinal", "wrong_signed_root", "escrow_deficit", "vault_deficit", "wrong_owner", "wrong_denom", "stale_permit", "future_permit", "forged_trust_root", "account_root_disagreement", "partition_overallocation", "partition_wrong_owner", "partition_wrong_epoch", "duplicate_physical_receipt", "ticket_message_ordinal", "physical_amount_changed", "altered_funding_memo"} {
		t.Run(name, func(t *testing.T) {
			bad, badPolicy, badProofs := freezeRequest(r), p, proofs
			switch name {
			case "wrong_message_ordinal":
				bad.FundingMessageIndex = 1
			case "wrong_signed_root":
				bad.BankAppHash = strings.Repeat("C", 64)
			case "escrow_deficit":
				bad.EscrowReserve.LiabilitiesUWolo = "140000000"
			case "vault_deficit":
				bad.VaultReserve.LiabilitiesUWolo = "98"
			case "wrong_owner":
				bad.OwnerUID = "forged-owner"
			case "wrong_denom":
				bad.Denom = "uatom"
			case "stale_permit":
				bad.IssuedAt = time.Now().Unix() - 200
				bad.ExpiresAt = bad.IssuedAt + 90
			case "future_permit":
				bad.IssuedAt = time.Now().Unix() + 30
				bad.ExpiresAt = bad.IssuedAt + 90
			case "forged_trust_root":
				badPolicy.TrustAnchor.Hash = strings.Repeat("f", 64)
				bad.PolicySHA256 = PolicyDigest(badPolicy)
			case "account_root_disagreement":
				badProofs.Escrow = one.Escrow
			case "partition_overallocation":
				bad.Tickets[0].Allocations[1].AmountUWolo = "61000000"
			case "partition_wrong_owner":
				bad.Tickets[0].OwnerUID = "forged-owner"
			case "partition_wrong_epoch":
				bad.Tickets[0].EpochID = "other_epoch_20261026"
			case "duplicate_physical_receipt":
				bad.Tickets[1].FundingTxHash = one.Hash
			case "ticket_message_ordinal":
				bad.Tickets[0].FundingMessageIndex = 1
			case "physical_amount_changed":
				bad.Tickets[0].OriginalFundingPrincipalUWolo, bad.Tickets[0].Allocations[1].AmountUWolo = "101000000", "61000000"
			case "altered_funding_memo":
				bad.Tickets[0].TicketID, bad.Plan.Wagers[0].TicketID, bad.TicketID = 201, 201, 201
				bad.OriginalOperationID = OriginalOperationID(p.EpochID, 201)
				bad.EntitlementID = EntitlementID(p.EpochID, 77, 201, 11)
				bad.OperationID, bad.Memo = bad.EntitlementID+":return", ReturnMemo(p.EpochID, bad.EntitlementID)
			}
			signTicket(&bad.Tickets[0], owner)
			signTicket(&bad.Tickets[1], opponent)
			bad.OriginalMandateSHA256 = OriginalTicketDigest(p, bad.Tickets[0])
			sign(&bad)
			_, e := VerifyPreparation(context.Background(), badPolicy, bad, badProofs)
			if e == nil {
				t.Fatal("native proof admitted conflicting economic identity")
			}
			var blocker *Blocker
			if !errors.As(e, &blocker) {
				t.Fatal("missing bounded native refusal", e)
			}
			t.Logf("native_negative case=%s code=%s cause=%s", name, blocker.Code, blocker.Cause)
			if (name == "vault_deficit" || name == "escrow_deficit") && blocker.Code != "RESERVE_COVERAGE_DEFICIT" {
				t.Fatal("account-local deficit refused at the wrong stage", blocker.Code)
			}
			if name == "wrong_signed_root" && (blocker.Code != "BANK_PROOF_STALE" || blocker.Cause != "Native proof refused at request_root_agreement.") {
				t.Fatal("request root disagreement refused at the wrong stage", blocker.Code, blocker.Cause)
			}
			if name == "account_root_disagreement" && (blocker.Code != "BANK_PROOF_STALE" || blocker.Cause != "Native proof refused at account_root_agreement.") {
				t.Fatal("authentic account root disagreement refused at the wrong stage", blocker.Code, blocker.Cause)
			}
			if (name == "physical_amount_changed" || name == "altered_funding_memo") && (blocker.Code != "BANK_PROOF_STALE" || blocker.Cause != "Native proof refused at funding_authentication.") {
				t.Fatal("altered physical funding did not reach exact native transfer authentication", blocker.Code, blocker.Cause)
			}
			if (name == "stale_permit" || name == "future_permit") && blocker.Code != "EPOCH_REPLAY_REJECTED" {
				t.Fatal("invalid permit refused at the wrong stage", blocker.Code)
			}
		})
	}
	if goldenPath := os.Getenv("WOLO_EPOCH_GOLDEN_OUT"); goldenPath != "" {
		// Explicit public schema: never copy f.Roles or the fixture's private keys.
		bankExport := func(step nativeV3Step) map[string]any {
			vault, e := verifier.VerifyBankProof(context.Background(), p.Vault, step.Vault.Height, step.Vault)
			if e != nil {
				t.Fatal("golden vault authentication refused", e)
			}
			escrow, e := verifier.VerifyBankProof(context.Background(), p.Escrow, step.Escrow.Height, step.Escrow)
			if e != nil {
				t.Fatal("golden escrow authentication refused", e)
			}
			observedAt := time.Now()
			if !vault.CurrentAt(observedAt) || !escrow.CurrentAt(observedAt) || vault.Height() != escrow.Height() || vault.AppHash() != escrow.AppHash() || vault.BlockHash() != escrow.BlockHash() {
				t.Fatal("golden bank checkpoint is not current under one authenticated root")
			}
			expiresAt := vault.ExpiresAt()
			if escrow.ExpiresAt().Before(expiresAt) {
				expiresAt = escrow.ExpiresAt()
			}
			return map[string]any{"vault_proof": step.Vault, "escrow_proof": step.Escrow, "state_height": vault.Height(), "commit_height": vault.CommitHeight(), "head_height": vault.HeadHeight(), "commit_hash": vault.BlockHash(), "app_hash": vault.AppHash(), "vault_state_height": vault.Height(), "vault_commit_height": vault.CommitHeight(), "vault_head_height": vault.HeadHeight(), "escrow_state_height": escrow.Height(), "escrow_commit_height": escrow.CommitHeight(), "escrow_head_height": escrow.HeadHeight(), "vault_balance_uwolo": vault.BalanceUWolo(), "escrow_balance_uwolo": escrow.BalanceUWolo(), "current_vault": true, "current_escrow": true, "app_root_equal": vault.AppHash() == escrow.AppHash(), "commit_hash_equal": vault.BlockHash() == escrow.BlockHash(), "head_hash_equal": vault.HeadBlockHash() == escrow.HeadBlockHash(), "observed_at": observedAt, "expires_at": expiresAt}
		}
		transferExport := func(name string, step nativeV3Step, evidence satchel.AuthenticatedEvidence, intent satchel.TransferIntent) map[string]any {
			observation := evidence.Observation()
			receipt := evidence.Receipt()
			return map[string]any{"name": name, "intent": map[string]any{"sender": intent.Sender, "recipient": intent.Recipient, "amount_uwolo": intent.AmountUWolo, "memo": intent.Memo}, "tx_hash": step.Hash, "tx_bytes_b64": base64.StdEncoding.EncodeToString(observation.TxBytes), "proof": step.Proof, "receipt": map[string]any{"chain_id": receipt.ChainID, "tx_hash": receipt.TxHash, "message_index": receipt.TransferIndex, "id": receipt.ID()}, "height": observation.Height, "chain_time": observation.BlockTime, "bank": bankExport(step)}
		}
		funding := []map[string]any{}
		for i, ticket := range r.Tickets {
			step := []nativeV3Step{one, two}[i]
			intent := satchel.TransferIntent{Sender: p.Vault, Recipient: p.Escrow, AmountUWolo: ticket.OriginalFundingPrincipalUWolo, Memo: FundingMemo(p.EpochID, ticket.TicketID)}
			evidence, e := verifier.VerifyMessageTransferProof(context.Background(), intent, step.Hash, step.Proof)
			if e != nil {
				t.Fatal("golden funding authentication refused", e)
			}
			funding = append(funding, transferExport(step.Name, step, evidence, intent))
		}
		requests := []map[string]any{}
		for i, req := range []Request{r, feeRequest, voidRequest} {
			requests = append(requests, map[string]any{"name": []string{"matched_return", "matched_fee", "void_return"}[i], "request": req, "message_b64": base64.StdEncoding.EncodeToString(RequestMessage(req)), "fingerprint": Fingerprint(req)})
		}
		tickets := []map[string]any{}
		for _, ticket := range r.Tickets {
			tickets = append(tickets, map[string]any{"ticket": ticket, "message_b64": base64.StdEncoding.EncodeToString(OriginalTicketMessage(p, ticket)), "digest_sha256": OriginalTicketDigest(p, ticket)})
		}
		outcomes := map[string]any{}
		for i, plan := range []Plan{r.Plan, voidRequest.Plan} {
			settled, e := PlanSettlement(plan)
			if e != nil {
				t.Fatal(e)
			}
			rows := []map[string]any{}
			for _, outcome := range settled {
				rows = append(rows, map[string]any{"wager": outcome.Wager, "matched_uwolo": outcome.MatchedUWolo, "unmatched_uwolo": outcome.UnmatchedUWolo, "payout_uwolo": outcome.PayoutUWolo, "fee_uwolo": outcome.FeeUWolo})
			}
			outcomes[[]string{"market_77", "market_78"}[i]] = rows
		}
		effects := []map[string]any{}
		for i, req := range []Request{r, feeRequest, voidRequest} {
			effects = append(effects, transferExport([]string{"matched_return", "matched_fee", "void_return"}[i], []nativeV3Step{returned, fee, voided}[i], []satchel.AuthenticatedEvidence{returnEffect, feeEffect, voidEffect}[i], satchel.TransferIntent{Sender: req.Sender, Recipient: req.Recipient, AmountUWolo: req.AmountUWolo, Memo: req.Memo}))
		}
		golden := map[string]any{"schema_version": 1, "fixture_only": true, "mainnet_authority": false, "production_custody_available": false, "generated_at": time.Now(), "source_sha": p.SourceCommit, "compiler": runtime.Version(), "native_test_binary_sha256": p.BinarySHA256, "binary_authority": "disposable-native-test-only", "policy": p, "tickets": tickets, "requests": requests, "funding": funding, "bank": bankExport(two), "final_bank": bankExport(voided), "outcomes": outcomes, "effects": effects}
		encoded, e := json.MarshalIndent(golden, "", "  ")
		if e != nil || os.WriteFile(goldenPath, encoded, 0600) != nil {
			t.Fatal("sanitized native golden export failed")
		}
		sum := sha256.Sum256(encoded)
		t.Logf("native_golden schema=1 sha256=%x source=%s compiler=%s native_test_binary_sha256=%s", sum, p.SourceCommit, runtime.Version(), p.BinarySHA256)
	}
}
