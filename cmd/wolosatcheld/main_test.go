package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

type countedBackend struct{ signs, broadcasts, confirms int }

func (b *countedBackend) Sign(context.Context, satchelservice.TransferRequest) (satchelservice.SignedTransaction, error) {
	b.signs++
	return satchelservice.SignedTransaction{}, nil
}
func (b *countedBackend) ValidateSigned(satchelservice.TransferRequest, satchelservice.SignedTransaction) error {
	return nil
}
func (b *countedBackend) Broadcast(context.Context, satchelservice.SignedTransaction) (satchelservice.BroadcastResult, error) {
	b.broadcasts++
	return satchelservice.BroadcastResult{Status: "ACCEPTED"}, nil
}
func (b *countedBackend) Confirm(context.Context, satchelservice.TransferRequest, satchelservice.SignedTransaction) (satchelservice.Confirmation, error) {
	b.confirms++
	return satchelservice.Confirmation{Status: "UNKNOWN"}, nil
}

func TestCommandRefusesUnconfiguredExecutionWithoutLeakingInputs(t *testing.T) {
	for _, args := range [][]string{nil, {"-unknown-sensitive-value"}, {"-config", "/sensitive/production/path"}, {"-config", "/sensitive/path", "-check"}} {
		var out, errout bytes.Buffer
		if code := run(t.Context(), args, &out, &errout); code == 0 {
			t.Fatal("unconfigured service started")
		}
		if strings.Contains(errout.String(), "sensitive") || out.Len() != 0 {
			t.Fatal("configuration path or unknown input leaked")
		}
	}
}
func TestPermitCheckedBeforeEachSignAndBroadcastButRecoveryRemainsAvailable(t *testing.T) {
	inner := &countedBackend{}
	active := true
	guard := &permittedBackend{inner: inner, authorize: func(context.Context) bool { return active }, trust: func(context.Context) error { return nil }}
	if _, err := guard.Sign(t.Context(), satchelservice.TransferRequest{}); err != nil || inner.signs != 1 {
		t.Fatal("verified permit refused")
	}
	active = false
	if _, err := guard.Sign(t.Context(), satchelservice.TransferRequest{}); err == nil || inner.signs != 1 {
		t.Fatal("expired permit authorized signing")
	}
	if r, err := guard.Broadcast(t.Context(), satchelservice.SignedTransaction{}); err == nil || r.Status != "UNKNOWN" || inner.broadcasts != 0 {
		t.Fatal("expired permit authorized transmission")
	}
	if _, err := guard.Confirm(t.Context(), satchelservice.TransferRequest{}, satchelservice.SignedTransaction{}); err != nil || inner.confirms != 1 {
		t.Fatal("permit expiry blocked read-only recovery")
	}
	if guard.ValidateSigned(satchelservice.TransferRequest{}, satchelservice.SignedTransaction{}) != nil {
		t.Fatal("permit expiry blocked durable verification")
	}
}

func TestUnverifiedConsensusTrustCannotReachSigner(t *testing.T) {
	inner := &countedBackend{}
	guard := &permittedBackend{inner: inner, authorize: func(context.Context) bool { return true }, trust: func(context.Context) error { return errors.New("untrusted checkpoint") }}
	if _, err := guard.Sign(t.Context(), satchelservice.TransferRequest{}); err == nil || inner.signs != 0 {
		t.Fatal("unverified trust reached signer")
	}
}
func TestRunningExecutableDigestIsStableAndPublic(t *testing.T) {
	a, err := runningDigest()
	if err != nil || len(a) != 64 {
		t.Fatalf("digest unavailable: %v", err)
	}
	b, err := runningDigest()
	if err != nil || a != b {
		t.Fatal(errors.New("executable digest changed"))
	}
}

func TestStaticCheckVerifiesRealPermitWithoutNetworkOrKeyring(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	address := func(b byte) string {
		s, err := bech32.EncodeFromBase256("wolo", bytes.Repeat([]byte{b}, 20))
		if err != nil {
			t.Fatal(err)
		}
		return s
	}
	authority := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{3}, 32))
	approval := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{4}, 32))
	cfg := satchelservice.Config{Version: 1, Vault: address(1), PublicKeyHex: "02" + strings.Repeat("01", 32), BettingEscrow: address(2), ProtectedAddresses: []string{address(2)}, MaxAmountUWolo: 1000000, RPC: "https://primary.invalid", REST: "https://rest.invalid", WitnessRPC: "https://witness.invalid", TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("A", 64), PeriodSeconds: 3600, EvidenceReference: "synthetic-test-only"}, KeyringDir: filepath.Join(dir, "does-not-exist-keyring"), KeyName: "synthetic", PassphraseFile: filepath.Join(dir, "does-not-exist-unlock"), TokenFile: filepath.Join(dir, "does-not-exist-token"), StatePath: filepath.Join(dir, "does-not-exist-state"), FeesUWolo: "5000", GasLimit: 120000, TimeoutBlocks: 20, WithdrawalApprovalKeyHex: hex.EncodeToString(approval.Public().(ed25519.PublicKey)), ActivationAuthorityKeyHex: hex.EncodeToString(authority.Public().(ed25519.PublicKey)), PermitFile: filepath.Join(dir, "permit.json")}
	data, _ := json.Marshal(cfg)
	digest := sha256.Sum256(data)
	binary, err := runningDigest()
	if err != nil {
		t.Fatal(err)
	}
	permit := satchelservice.ExecutionPermit{Version: 1, Scope: "satchel-execution-v1", ConfigSHA256: hex.EncodeToString(digest[:]), BinarySHA256: binary, Vault: cfg.Vault, IsolationEvidenceSHA256: strings.Repeat("1", 64), AccountingEvidenceSHA256: strings.Repeat("2", 64), RecoveryEvidenceSHA256: strings.Repeat("3", 64), Reviewer: "synthetic test reviewer", Reference: "synthetic-only", IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Unix() + 300}
	permit.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(authority, satchelservice.PermitMessage(permit)))
	encoded, _ := json.Marshal(permit)
	config := filepath.Join(dir, "config.json")
	if os.WriteFile(config, data, 0600) != nil || os.WriteFile(cfg.PermitFile, encoded, 0600) != nil {
		t.Fatal("fixture write failed")
	}
	// A canceled context makes any accidental network trust check fail. Missing
	// keyring/token paths make accidental signer initialization fail as well.
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	var out, errout bytes.Buffer
	if code := run(ctx, []string{"-config", config, "-check"}, &out, &errout); code != 0 || !strings.Contains(out.String(), "TRUST_UNCHECKED") || errout.Len() != 0 {
		t.Fatalf("static check touched execution resources: %d %s %s", code, out.String(), errout.String())
	}
	if _, err := os.Lstat(cfg.KeyringDir); !os.IsNotExist(err) {
		t.Fatal("static check created keyring")
	}
}
