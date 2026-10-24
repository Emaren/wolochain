package satchelservice

// Opt-in integration fixture: authenticate an actual, committed SDK wager with
// a separately signed reviewer reservation through the production offline
// financial verifier. These deterministic reviewer keys have isolated test
// authority only. No production keyring, signing backend or network is opened.
import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

type wagerRoundtripCase struct {
	Name      string                `json:"name"`
	Authority map[string]any        `json:"authority"`
	Expected  FinancialProofContext `json:"expected"`
	Proof     FinancialProof        `json:"proof"`
}

func cloneWagerRoundtrip[T any](t *testing.T, value T) T {
	t.Helper()
	raw, e := json.Marshal(value)
	if e != nil {
		t.Fatal(e)
	}
	var result T
	if e = json.Unmarshal(raw, &result); e != nil {
		t.Fatal(e)
	}
	return result
}

func TestOfflineFinancialWagerProofFromCommittedSDKFixture(t *testing.T) {
	path := os.Getenv("SATCHEL_WAGER_SDK_FIXTURE")
	if path == "" {
		t.Skip("requires the genuine opt-in continuous SDK fixture")
	}
	if !filepath.IsAbs(path) {
		t.Fatal("fixture path must be absolute")
	}
	file, e := os.Open(path)
	if e != nil {
		t.Fatal(e)
	}
	defer file.Close()
	raw, e := io.ReadAll(io.LimitReader(file, 8<<20+1))
	if e != nil || len(raw) > 8<<20 {
		t.Fatal("fixture unavailable or too large")
	}
	var fixture struct {
		FixtureOnly      bool                `json:"fixture_only"`
		MainnetAuthority bool                `json:"mainnet_authority"`
		Now              time.Time           `json:"now"`
		Anchor           satchel.TrustAnchor `json:"anchor"`
		Roles            struct {
			OwnerID string `json:"owner_id"`
			Vault   string `json:"vault"`
			Escrow  string `json:"escrow"`
		} `json:"roles"`
		Steps []struct {
			Name        string                   `json:"name"`
			Intent      satchel.TransferIntent   `json:"intent"`
			TxHash      string                   `json:"tx_hash"`
			FeeUWolo    string                   `json:"fee_uwolo"`
			Observation satchel.Observation      `json:"observation"`
			Receipt     satchel.ReceiptCandidate `json:"receipt"`
			Proof       satchel.PortableProof    `json:"proof"`
		} `json:"steps"`
	}
	if json.Unmarshal(raw, &fixture) != nil || !fixture.FixtureOnly || fixture.MainnetAuthority || fixture.Now.IsZero() {
		t.Fatal("not an isolated SDK fixture")
	}
	index := -1
	for n, step := range fixture.Steps {
		if step.Name == "wager" {
			index = n
			break
		}
	}
	if index < 0 {
		t.Fatal("actual SDK wager missing")
	}
	step := fixture.Steps[index]
	if step.FeeUWolo != "1" || step.Intent.Sender != fixture.Roles.Vault || step.Intent.Recipient != fixture.Roles.Escrow || step.Intent.Memo != "AoE2HDBets bet ticket v1 · ticket 1" {
		t.Fatal("unexpected native wager contract")
	}
	key := func(label string) ed25519.PrivateKey {
		seed := sha256.Sum256([]byte("isolated-financial-wager-roundtrip-test-only/" + label))
		return ed25519.NewKeyFromSeed(seed[:])
	}
	wagerKey, withdrawalKey, wrongKey := key("wager"), key("withdrawal-return"), key("wrong-wager")
	publicHex := func(k ed25519.PrivateKey) string { return hex.EncodeToString(k.Public().(ed25519.PublicKey)) }
	reservation := WagerReservation{Version: 1, OperationID: "satchel:ticket:777", OwnerID: fixture.Roles.OwnerID, Vault: fixture.Roles.Vault, Recipient: fixture.Roles.Escrow, AmountUWolo: step.Intent.AmountUWolo, Memo: step.Intent.Memo,
		ReservationDigest: strings.Repeat("a", 64), LedgerRevision: strings.Repeat("b", 64), ConsentDigest: strings.Repeat("c", 64), FeeUWolo: step.FeeUWolo, IssuedAt: fixture.Now.Add(-3 * time.Second).Unix(), ExpiresAt: fixture.Now.Add(120 * time.Second).Unix()}
	sign := func(a *WagerReservation, k ed25519.PrivateKey) {
		a.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(k, WagerReservationMessage(*a)))
	}
	sign(&reservation, wagerKey)
	expected := FinancialProofContext{Protocol: 1, Kind: "wager", OwnerID: fixture.Roles.OwnerID, OperationID: reservation.OperationID, Sender: fixture.Roles.Vault, Recipient: fixture.Roles.Escrow, AmountUWolo: step.Intent.AmountUWolo, Memo: step.Intent.Memo, TxHash: step.TxHash, Reservation: &reservation}
	proof := FinancialProof{Protocol: 1, ChainID: satchel.ChainID, Denom: satchel.Denom, Context: expected, ContextDigest: FinancialContextDigest(expected), TxHash: step.TxHash, ReceiptID: step.Receipt.ID(), TransferIndex: step.Receipt.TransferIndex, MessageIndex: 0, Height: step.Observation.Height, BlockHash: step.Observation.BlockHash, ConsensusAuthenticated: true, CreditAuthorized: false, Proof: step.Proof}
	authority := map[string]any{"trust_anchor": fixture.Anchor, "vault": fixture.Roles.Vault, "betting_escrow": fixture.Roles.Escrow, "approval_public_key_hex": publicHex(withdrawalKey), "wager_approval_public_key_hex": publicHex(wagerKey)}
	decodeAuthority := func(a map[string]any) (FinancialProofVerifierConfig, error) {
		encoded, e := json.Marshal(a)
		if e != nil {
			return FinancialProofVerifierConfig{}, e
		}
		return DecodeFinancialProofVerifierConfig(encoded)
	}
	config, e := decodeAuthority(authority)
	if e != nil {
		t.Fatal("separate public wager authority refused:", e)
	}
	verified, e := VerifyFinancialProof(t.Context(), config, expected, proof)
	if e != nil {
		t.Fatal("actual committed SDK wager rejected:", e)
	}
	if verified.Kind != "wager" || verified.OperationID != "satchel:ticket:777" || verified.OwnerID != fixture.Roles.OwnerID || verified.TxHash != step.TxHash || verified.ReceiptID != step.Receipt.ID() || verified.CreditAuthorized {
		t.Fatal("wrong or authorizing financial receipt")
	}
	again, e := VerifyFinancialProof(t.Context(), config, expected, proof)
	if e != nil || !reflect.DeepEqual(verified, again) {
		t.Fatal("read-only proof retry changed physical identity")
	}
	cases := []wagerRoundtripCase{}
	for _, name := range []string{"missing_wager_key", "wrong_wager_key", "withdrawal_key_in_wager_role", "colliding_approval_keys", "withdrawal_signature_is_not_wager_approval", "wrong_owner", "wrong_signed_fee", "wrong_signed_ticket_memo", "wrong_signed_amount", "wrong_trust_root"} {
		t.Run(name, func(t *testing.T) {
			c := wagerRoundtripCase{Name: name, Authority: cloneWagerRoundtrip(t, authority), Expected: cloneWagerRoundtrip(t, expected), Proof: cloneWagerRoundtrip(t, proof)}
			switch name {
			case "missing_wager_key":
				delete(c.Authority, "wager_approval_public_key_hex")
			case "wrong_wager_key":
				c.Authority["wager_approval_public_key_hex"] = publicHex(wrongKey)
			case "withdrawal_key_in_wager_role":
				c.Authority["wager_approval_public_key_hex"], c.Authority["approval_public_key_hex"] = publicHex(withdrawalKey), publicHex(wagerKey)
			case "colliding_approval_keys":
				c.Authority["approval_public_key_hex"] = publicHex(wagerKey)
			case "withdrawal_signature_is_not_wager_approval":
				sign(c.Expected.Reservation, withdrawalKey)
			case "wrong_owner":
				c.Expected.OwnerID = "other-owner"
			case "wrong_signed_fee":
				c.Expected.Reservation.FeeUWolo = "2"
				sign(c.Expected.Reservation, wagerKey)
			case "wrong_signed_ticket_memo":
				c.Expected.Memo = "AoE2HDBets bet ticket v1 · ticket 2"
				c.Expected.Reservation.Memo = c.Expected.Memo
				sign(c.Expected.Reservation, wagerKey)
			case "wrong_signed_amount":
				c.Expected.AmountUWolo = "12000001"
				c.Expected.Reservation.AmountUWolo = c.Expected.AmountUWolo
				sign(c.Expected.Reservation, wagerKey)
			case "wrong_trust_root":
				anchor := cloneWagerRoundtrip(t, fixture.Anchor)
				anchor.Hash = strings.Repeat("F", 64)
				c.Authority["trust_anchor"] = anchor
			}
			// Rebind the envelope so fee/memo/owner attacks reach the economic or
			// chain check instead of failing only an unsigned context checksum.
			c.Proof.Context = cloneWagerRoundtrip(t, c.Expected)
			c.Proof.ContextDigest = FinancialContextDigest(c.Expected)
			cfg, e := decodeAuthority(c.Authority)
			if e == nil {
				_, e = VerifyFinancialProof(t.Context(), cfg, c.Expected, c.Proof)
			}
			if e == nil {
				t.Fatal("forged role, authority or native transfer accepted")
			}
			if name == "wrong_signed_fee" && e.Error() != "financial_wager_fee_mismatch" {
				t.Fatal("signed fee disagreement did not reach actual native fee check:", e)
			}
			cases = append(cases, c)
		})
	}
	if directory := os.Getenv("SATCHEL_WAGER_ROUNDTRIP_DIR"); directory != "" {
		if !filepath.IsAbs(directory) {
			t.Fatal("export directory must be absolute")
		}
		if e = os.MkdirAll(directory, 0700); e != nil {
			t.Fatal(e)
		}
		for name, value := range map[string]any{"wager-authority.json": authority, "wager-expected.json": expected, "wager-proof.json": proof, "wager-negative-cases.json": cases} {
			encoded, e := json.Marshal(value)
			if e != nil {
				t.Fatal(e)
			}
			if e = os.WriteFile(filepath.Join(directory, name), encoded, 0600); e != nil {
				t.Fatal(e)
			}
		}
	}
}
