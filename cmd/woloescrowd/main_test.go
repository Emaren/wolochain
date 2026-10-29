package main

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"github.com/cosmos/btcutil/bech32"
	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/satchel"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHeldCommandNeverAcceptsActivationOrMalformedPolicy(t *testing.T) {
	for _, args := range [][]string{nil, {"-enable"}, {"-config", "relative"}, {"-config", "/missing"}} {
		var out bytes.Buffer
		if code := run(args, &out); code != 2 || !strings.Contains(out.String(), "EPOCH_POLICY_INVALID") {
			t.Fatal(code, out.String())
		}
	}
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "policy.json")
	if e = os.WriteFile(path, []byte(`{"version":3,"version":3}`), 0600); e != nil {
		t.Fatal(e)
	}
	var out bytes.Buffer
	if code := run([]string{"-config", path, "-check"}, &out); code != 2 {
		t.Fatal(code, out.String())
	}
}

func TestCompleteStructuralPolicyStillCannotOpenExecutor(t *testing.T) {
	key := func(name string) string {
		return hex.EncodeToString(secp.GenPrivKeyFromSecret([]byte("disposable-held-command-test/" + name)).PubKey().Bytes())
	}
	addr := func(name string) string {
		k, _ := hex.DecodeString(key(name))
		a, _ := bech32.EncodeFromBase256("wolo", (&secp.PubKey{Key: k}).Address())
		return a
	}
	p := epochescrow.Policy{Version: 3, EpochID: "held_epoch_20261026", HStar: 1, Vault: addr("vault"), Escrow: addr("escrow"), VaultPublicKeyHex: key("vault"), EscrowPublicKeyHex: key("escrow"), VaultKeyringLineageSHA256: strings.Repeat("1", 64), EscrowKeyringLineageSHA256: strings.Repeat("2", 64), VaultUID: 1001, EscrowUID: 1002, LegacyUIDs: []uint32{1003}, LegacyPublicKeySHA256: []string{strings.Repeat("3", 64)}, LegacyKeyringLineageSHA256: []string{strings.Repeat("4", 64)}, ReviewerPublicKeyHex: strings.Repeat("5", 64), FeeRecipient: addr("fees"), GasFeeUWolo: "2500", SourceCommit: strings.Repeat("a", 40), BinarySHA256: strings.Repeat("b", 64), ConfigSHA256: strings.Repeat("c", 64), TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("d", 64), PeriodSeconds: 3600, EvidenceReference: "disposable-command-test-only"}}
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "policy.json")
	data, _ := json.Marshal(p)
	if e = os.WriteFile(path, data, 0600); e != nil {
		t.Fatal(e)
	}
	var out bytes.Buffer
	if code := run([]string{"-config", path, "-check"}, &out); code != 0 || !strings.Contains(out.String(), "STRUCTURAL_REVIEW_ONLY") || !strings.Contains(out.String(), `"signing_authorized":false`) {
		t.Fatal(code, out.String())
	}
	out.Reset()
	if code := run([]string{"-config", path}, &out); code != 2 || !strings.Contains(out.String(), "NEW_ESCROW_SIGNER_ABSENT") {
		t.Fatal(code, out.String())
	}
}

// This is a refusal contract, not a positive native wire verifier test. The
// transcript cannot establish independent observer provenance or a complete
// liability inventory, so this argv must not announce a successful verdict.
func TestHDWireV1InvocationRemainsHeldWithoutPublishedTrustContract(t *testing.T) {
	for _, args := range [][]string{
		{"--verify-epoch-v3-portable-proof", "--json-stdin"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--check"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--config", "/not-enrolled-verifier-policy"},
	} {
		var out bytes.Buffer
		if code := run(args, &out); code != 2 || out.String() != "{\"code\":\"EPOCH_POLICY_INVALID\"}\n" {
			t.Fatal("unprovisioned wire invocation gained authority")
		}
	}
}
