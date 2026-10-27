package epochescrow

// The opt-in harness reuses satchel's continuous real SDK application/Comet
// exporter. It builds this test binary first, exports fresh native proofs, then
// executes this test without recompilation. No native chain fixture is copied.
import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/satchel"
)

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
		Steps                      []struct {
			Name   string                `json:"name"`
			Hash   string                `json:"tx_hash"`
			Proof  satchel.PortableProof `json:"proof"`
			Vault  satchel.BankProof     `json:"vault_bank_proof"`
			Escrow satchel.BankProof     `json:"escrow_bank_proof"`
		} `json:"steps"`
	}
	if err = json.Unmarshal(data, &f); err != nil {
		t.Fatal(err)
	}
	if !f.FixtureOnly || f.MainnetAuthority || f.ProductionCustodyAvailable {
		t.Fatal("fixture cannot assert production authority")
	}
	steps := map[string]int{}
	for i, s := range f.Steps {
		steps[s.Name] = i
	}
	for _, name := range []string{"funding_one", "funding_two", "epoch_return", "epoch_fee"} {
		if _, ok := steps[name]; !ok {
			t.Fatal("missing native step", name)
		}
	}
	one, two, returned, fee := f.Steps[steps["funding_one"]], f.Steps[steps["funding_two"]], f.Steps[steps["epoch_return"]], f.Steps[steps["epoch_fee"]]
	p, r := fixture(t)
	p.Vault = f.Roles["vault"]
	p.Escrow = f.Roles["escrow"]
	p.VaultPublicKeyHex = f.Roles["vault_public_key_hex"]
	p.EscrowPublicKeyHex = f.Roles["escrow_public_key_hex"]
	p.FeeRecipient = f.Roles["opponent"]
	p.GasFeeUWolo = "1"
	p.TrustAnchor = f.Anchor
	r.OwnerUID = f.Roles["owner_id"]
	r.OwnerWallet = f.Roles["owner"]
	r.OwnerPublicKeyHex = f.Roles["owner_public_key_hex"]
	r.Sender = p.Escrow
	r.Recipient = p.Vault
	r.AmountUWolo = "25000000"
	r.FundingTxHash = one.Hash
	r.PolicySHA256 = PolicyDigest(p)
	r.Plan.Wagers = []Wager{{1, 10, 1, 1, r.OwnerUID, "left", "13000000", one.Hash, 0}, {2, 10, 2, 2, r.OwnerUID, "right", "13000000", two.Hash, 0}}
	r.VaultReserve.Account = p.Vault
	r.EscrowReserve.Account = p.Escrow
	r.VaultReserve.LiabilitiesUWolo = "0"
	r.EscrowReserve.LiabilitiesUWolo = "0"
	r.VaultReserve.GasReserveUWolo = "1"
	r.EscrowReserve.GasReserveUWolo = "1"
	verifier, err := satchel.NewProofVerifier(p.TrustAnchor)
	if err != nil {
		t.Fatal(err)
	}
	bank, err := verifier.VerifyBankProof(context.Background(), p.Vault, two.Vault.Height, two.Vault)
	if err != nil {
		t.Fatal(err)
	}
	r.BankStateHeight = bank.Height()
	r.BankCommitHeight = bank.CommitHeight()
	r.BankCommitHash = bank.BlockHash()
	r.BankAppHash = bank.AppHash()
	r.IssuedAt = time.Now().Unix()
	r.ExpiresAt = r.IssuedAt + 90
	raw, err := hex.DecodeString(f.Roles["owner_private_key_hex_test_only"])
	if err != nil || len(raw) != 32 {
		t.Fatal("missing disposable owner fixture key")
	}
	owner := &secp.PrivKey{Key: raw}
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
	v, err := VerifyPreparation(context.Background(), p, r, proofs)
	if err != nil {
		t.Fatal("genuine fee-paying SDK funding/bank proofs refused", err)
	}
	j, _ := journalFixture(t, p)
	defer j.Close()
	if d, e := j.Prepare(context.Background(), v); e != nil || d.Status != PreparedUnsigned {
		t.Fatal(d, e)
	}
	evidence, err := ObserveReturn(context.Background(), p, r, returned.Hash, returned.Proof)
	if err != nil || evidence.Receipt().TransferIndex != 0 || evidence.CreditAuthorized() {
		t.Fatal("genuine native return refused or credited", err)
	}
	if evidence.Observation().TransferIndex == nil || *evidence.Observation().TransferIndex != 1 {
		t.Fatal("canonical message identity changed native bank-event order")
	}
	legacy, err := verifier.VerifyTransferProof(context.Background(), satchel.TransferIntent{Sender: p.Escrow, Recipient: p.Vault, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, returned.Hash, returned.Proof)
	if err != nil || legacy.Receipt().TransferIndex != 1 {
		t.Fatal("legacy event-ordinal API changed", err)
	}
	feeRequest := freezeRequest(r)
	feeRequest.Command = FeeCommand
	feeRequest.OperationID = feeRequest.EntitlementID + ":fee"
	feeRequest.Recipient = p.FeeRecipient
	feeRequest.AmountUWolo = "1000000"
	feeRequest.Memo = "aoe2war/satchel/epoch-v3/" + p.EpochID + "/fee/" + feeRequest.EntitlementID
	feeRequest.Nonce = strings.Repeat("e", 64)
	sign(&feeRequest)
	feePreparation, err := VerifyPreparation(context.Background(), p, feeRequest, proofs)
	if err != nil {
		t.Fatal("matched-only native fee preparation", err)
	}
	if _, err = j.Prepare(context.Background(), feePreparation); err != nil {
		t.Fatal(err)
	}
	feeEffect, err := verifier.VerifyMessageTransferProof(context.Background(), satchel.TransferIntent{Sender: p.Escrow, Recipient: p.FeeRecipient, AmountUWolo: "1000000", Memo: feeRequest.Memo}, fee.Hash, fee.Proof)
	if err != nil || feeEffect.Receipt().TransferIndex != 0 || feeEffect.CreditAuthorized() {
		t.Fatal("genuine native matched fee effect", err)
	}
	if _, err = j.Execute(context.Background(), r.OperationID, Fingerprint(r)); err == nil {
		t.Fatal("native proof substituted for independent custody authority")
	}
	for _, name := range []string{"wrong_message_ordinal", "wrong_signed_root", "escrow_deficit", "wrong_owner", "wrong_denom", "stale_permit", "forged_trust_root", "account_root_disagreement"} {
		t.Run(name, func(t *testing.T) {
			bad := freezeRequest(r)
			badPolicy := p
			badProofs := proofs
			switch name {
			case "wrong_message_ordinal":
				bad.FundingMessageIndex = 1
			case "wrong_signed_root":
				bad.BankAppHash = strings.Repeat("C", 64)
			case "escrow_deficit":
				bad.EscrowReserve.LiabilitiesUWolo = "26000000"
			case "wrong_owner":
				bad.OwnerUID = "forged-owner"
			case "wrong_denom":
				bad.Denom = "uatom"
			case "stale_permit":
				bad.IssuedAt = time.Now().Unix() - 200
				bad.ExpiresAt = bad.IssuedAt + 90
			case "forged_trust_root":
				badPolicy.TrustAnchor.Hash = strings.Repeat("f", 64)
				bad.PolicySHA256 = PolicyDigest(badPolicy)
			case "account_root_disagreement":
				badProofs.Escrow = one.Escrow
			}
			sign(&bad)
			if _, e := VerifyPreparation(context.Background(), badPolicy, bad, badProofs); e == nil {
				t.Fatal("native proof admitted conflicting economic identity")
			}
		})
	}
}
