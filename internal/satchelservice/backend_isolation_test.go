package satchelservice

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/crypto"
	cryptocodec "github.com/cosmos/cosmos-sdk/crypto/codec"
	"github.com/cosmos/cosmos-sdk/crypto/keyring"
)

// Actual encrypted SDK keyring in an isolated temporary directory. This fixture
// contains only the existing deterministic test signer, never an operator key.
func isolatedBackendConfig(t *testing.T) (BackendConfig, *backendFixture) {
	t.Helper()
	f := newBackendFixture(t)
	directory, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(directory, 0700); err != nil {
		t.Fatal(err)
	}
	registry := codectypes.NewInterfaceRegistry()
	cryptocodec.RegisterInterfaces(registry)
	const password = "isolated-fixture-password-only"
	keys, err := keyring.New("cosmos", keyring.BackendFile, directory, strings.NewReader(password+"\n"+password+"\n"), codec.NewProtoCodec(registry))
	if err != nil {
		t.Fatal(err)
	}
	armor := crypto.EncryptArmorPrivKey(f.signer.key, "fixture-import-only", f.signer.key.Type())
	if err := keys.ImportPrivKey(f.b.cfg.KeyName, armor, "fixture-import-only"); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(filepath.Join(directory, "keyring-file"), 0700); err != nil {
		t.Fatal(err)
	}
	passwordFile := filepath.Join(directory, "unlock")
	if err := os.WriteFile(passwordFile, []byte(password+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg := f.b.cfg
	cfg.KeyringDir, cfg.PassphraseFile = directory, passwordFile
	return cfg, f
}

func TestBackendKeyringLeaseExcludesOtherProcess(t *testing.T) {
	if directory := os.Getenv("SATCHEL_TEST_KEYRING_LEASE_DIRECTORY"); directory != "" {
		lease, err := lockSatchelKeyring(directory)
		if os.Getenv("SATCHEL_TEST_KEYRING_EXPECT_LOCKED") == "1" {
			if err == nil {
				lease.Close()
				t.Fatal("separate process obtained an already-held keyring lease")
			}
			return
		}
		if err != nil {
			t.Fatalf("separate process could not acquire released keyring: %v", err)
		}
		lease.Close()
		return
	}
	cfg, _ := isolatedBackendConfig(t)
	b, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	for _, locked := range []string{"1", "0"} {
		if locked == "0" {
			b.Close()
		}
		ctx, cancel := context.WithTimeout(t.Context(), 5*time.Second)
		child := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestBackendKeyringLeaseExcludesOtherProcess$", "-test.count=1")
		child.Env = append(os.Environ(), "SATCHEL_TEST_KEYRING_LEASE_DIRECTORY="+cfg.KeyringDir, "SATCHEL_TEST_KEYRING_EXPECT_LOCKED="+locked)
		out, err := child.CombinedOutput()
		cancel()
		if err != nil {
			t.Fatalf("cross-process keyring exclusion failed: %v %s", err, out)
		}
	}
}

func TestBackendRejectsSecondSignerUsingSameEncryptedKeyring(t *testing.T) {
	cfg, _ := isolatedBackendConfig(t)
	first, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	second, err := NewKeyringBackend(cfg)
	if err == nil {
		second.Close()
		t.Fatal("two signer backends opened the same private keyring; separate journals bypass exclusive sequence authority")
	}
	first.Close()
	reopened, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatalf("closed exclusive signer could not be reopened: %v", err)
	}
	reopened.Close()
}

func TestBackendClosedSignerCannotSignOrBroadcastAfterLeaseRelease(t *testing.T) {
	cfg, f := isolatedBackendConfig(t)
	b, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatal(err)
	}
	signed, err := b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	b.Close()
	if _, err := b.Sign(t.Context(), f.request); err != ErrPreSignRefused {
		t.Fatal("closed keyring backend signed after releasing exclusive authority")
	}
	if _, err := b.Broadcast(t.Context(), signed); err != ErrBackend || f.broadcasts.Load() != 0 {
		t.Fatal("closed backend broadcast after releasing exclusive authority")
	}
}

func TestBackendKeyringDirectoryReplacementRefusesBeforeNativeSign(t *testing.T) {
	cfg, f := isolatedBackendConfig(t)
	b, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	path := filepath.Join(cfg.KeyringDir, "keyring-file")
	if err := os.Rename(path, path+"-preserved"); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(path, 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := b.Sign(t.Context(), f.request); err != ErrPreSignRefused {
		t.Fatalf("replaced keyring path reached SDK signing: %v", err)
	}
	if f.broadcasts.Load() != 0 {
		t.Fatal("keyring path replacement broadcast tokens")
	}
}
