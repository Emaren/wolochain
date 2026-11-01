package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/cosmos/btcutil/bech32"
	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/epochescrow/nativeverifier"
	"github.com/emaren/wolochain/internal/satchel"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
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

// Unit tests do not depend on enrollment installed on the host. The disposable
// SDK integration separately exercises the real fixed manifest and binary.
func TestHDWireV1InvocationRemainsHeldWithoutPublishedTrustContract(t *testing.T) {
	deps := portableTestDependencies(t)
	deps.loadPins = func(context.Context) (nativeverifier.Pins, error) {
		return nativeverifier.Pins{}, errors.New("/private/unsafe/enrollment")
	}
	var out bytes.Buffer
	if code := runPortable([]string{"--verify-epoch-v3-portable-proof", "--json-stdin"}, strings.NewReader(`{}`), &out, deps); code != 2 || out.String() != "{\"code\":\"PRODUCTION_TRUST_ENROLLMENT_REQUIRED\"}\n" {
		t.Fatal(code, out.String())
	}
	for _, args := range [][]string{
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--check"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--config", "/not-enrolled-verifier-policy"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--pins", "/tmp/pins.json"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--enable"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--sign"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--listen", ":8092"},
		{"--verify-epoch-v3-portable-proof", "--json-stdin", "--credit"},
		{"--verify-epoch-v3-portable-proof"},
		{"--json-stdin"},
		{"--verify-epoch-v3-portable-proof", "--verify-epoch-v3-portable-proof"},
	} {
		var out bytes.Buffer
		if code := run(args, &out); code != 2 || out.String() != "{\"code\":\"EPOCH_POLICY_INVALID\"}\n" {
			t.Fatal("unprovisioned wire invocation gained authority")
		}
	}
}

func portableTestDependencies(t *testing.T) portableDependencies {
	t.Helper()
	return portableDependencies{
		loadPins: func(context.Context) (nativeverifier.Pins, error) { return nativeverifier.Pins{}, nil },
		identity: func(context.Context) (nativeverifier.Identity, error) { return nativeverifier.Identity{}, nil },
		verify: func(context.Context, nativeverifier.Pins, nativeverifier.Identity, []byte) (nativeverifier.Verdict, error) {
			return nativeverifier.Verdict{NativeVerdict: "COMET_ICS23_NATIVE_VERIFIED", DisposableTestOnly: true}, nil
		},
		timeout: time.Second,
	}
}

func TestPortableExactArgumentsAndBoundedOutput(t *testing.T) {
	for _, args := range [][]string{{"--verify-epoch-v3-portable-proof", "--json-stdin"}, {"--json-stdin", "--verify-epoch-v3-portable-proof"}} {
		var out bytes.Buffer
		if code := runPortable(args, strings.NewReader(`{}`), &out, portableTestDependencies(t)); code != 0 {
			t.Fatal(code, out.String())
		}
		var result nativeverifier.Verdict
		if json.Unmarshal(out.Bytes(), &result) != nil || !result.DisposableTestOnly || result.CreditAuthorized || result.GlobalReceiptConsumed || result.LegacyPaymentAuthorized || result.ProductionTrustEnrolled || out.Len() > 256*1024 {
			t.Fatal(out.String())
		}
	}
}

func TestPortableInputBoundsAndIdentityFailure(t *testing.T) {
	args := []string{"--verify-epoch-v3-portable-proof", "--json-stdin"}
	for _, test := range []struct {
		name  string
		input io.Reader
		code  string
	}{
		{"empty", strings.NewReader(""), "NATIVE_VERIFIER_INPUT_INVALID"},
		{"invalid UTF8", bytes.NewReader([]byte{0xff}), "NATIVE_VERIFIER_INPUT_INVALID"},
		{"oversized", io.LimitReader(zeroReader{}, nativeverifier.MaxBundleBytes+1), "NATIVE_VERIFIER_INPUT_TOO_LARGE"},
	} {
		t.Run(test.name, func(t *testing.T) {
			deps := portableTestDependencies(t)
			deps.verify = func(context.Context, nativeverifier.Pins, nativeverifier.Identity, []byte) (nativeverifier.Verdict, error) {
				t.Error("invalid input reached verifier")
				return nativeverifier.Verdict{}, nil
			}
			var out bytes.Buffer
			if code := runPortable(args, test.input, &out, deps); code != 2 || out.String() != "{\"code\":\""+test.code+"\"}\n" {
				t.Fatal(code, out.String())
			}
		})
	}
	deps := portableTestDependencies(t)
	deps.identity = func(context.Context) (nativeverifier.Identity, error) {
		return nativeverifier.Identity{}, errors.New("/secret/executable: errno 13")
	}
	var out bytes.Buffer
	if code := runPortable(args, strings.NewReader(`{}`), &out, deps); code != 2 || out.String() != "{\"code\":\"NATIVE_VERIFIER_IDENTITY_MISMATCH\"}\n" {
		t.Fatal(code, out.String())
	}
}

type zeroReader struct{}

func (zeroReader) Read(p []byte) (int, error) { clear(p); return len(p), nil }

func TestPortableReadAndVerificationShareDeadline(t *testing.T) {
	args := []string{"--verify-epoch-v3-portable-proof", "--json-stdin"}
	for _, phase := range []string{"pins", "identity", "stdin", "verify"} {
		t.Run(phase, func(t *testing.T) {
			deps := portableTestDependencies(t)
			deps.timeout = 20 * time.Millisecond
			wait := func(ctx context.Context) { <-ctx.Done() }
			var in io.Reader = strings.NewReader(`{}`)
			switch phase {
			case "pins":
				deps.loadPins = func(ctx context.Context) (nativeverifier.Pins, error) {
					wait(ctx)
					return nativeverifier.Pins{}, ctx.Err()
				}
			case "identity":
				deps.identity = func(ctx context.Context) (nativeverifier.Identity, error) {
					wait(ctx)
					return nativeverifier.Identity{}, ctx.Err()
				}
			case "stdin":
				reader, writer := io.Pipe()
				defer reader.Close()
				defer writer.Close()
				in = reader
			case "verify":
				deps.verify = func(ctx context.Context, _ nativeverifier.Pins, _ nativeverifier.Identity, _ []byte) (nativeverifier.Verdict, error) {
					wait(ctx)
					return nativeverifier.Verdict{}, ctx.Err()
				}
			}
			start := time.Now()
			var out bytes.Buffer
			if code := runPortable(args, in, &out, deps); code != 2 || out.String() != "{\"code\":\"NATIVE_VERIFIER_TIMEOUT\"}\n" || time.Since(start) > time.Second {
				t.Fatal(code, out.String(), time.Since(start))
			}
		})
	}
}

func TestPortableOutputLimitAndFixedError(t *testing.T) {
	deps := portableTestDependencies(t)
	deps.verify = func(context.Context, nativeverifier.Pins, nativeverifier.Identity, []byte) (nativeverifier.Verdict, error) {
		return nativeverifier.Verdict{Memo: strings.Repeat("x", 256*1024)}, nil
	}
	var out bytes.Buffer
	if code := runPortable([]string{"--verify-epoch-v3-portable-proof", "--json-stdin"}, strings.NewReader(`{}`), &out, deps); code != 2 || out.String() != "{\"code\":\"NATIVE_VERIFIER_OUTPUT_INVALID\"}\n" {
		t.Fatal(code, out.String())
	}
	if got := portableError("/secret/rpc?token=abc"); string(got.data) != "{\"code\":\"NATIVE_VERIFIER_INVALID\"}\n" {
		t.Fatal(string(got.data))
	}
}
