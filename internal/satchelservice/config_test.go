package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

func configTestDir(t *testing.T) string {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return dir
}

func configTestWrite(t *testing.T, path string, data []byte) {
	t.Helper()
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
}

func TestPrivateFileRejectsUnsafeFilesystemObjects(t *testing.T) {
	for _, name := range []string{"group read", "group write", "world read", "world write", "empty", "oversize", "directory", "hardlink", "symlink", "ancestor symlink", "noncanonical ancestor", "fifo", "missing", "relative", "zero limit", "oversize limit", "foreign owner"} {
		t.Run(name, func(t *testing.T) {
			dir := configTestDir(t)
			path := filepath.Join(dir, "private")
			configTestWrite(t, path, []byte("synthetic-private-fixture"))
			limit := int64(128)
			switch name {
			case "group read", "group write", "world read", "world write":
				mode := map[string]os.FileMode{"group read": 0640, "group write": 0620, "world read": 0604, "world write": 0602}[name]
				if err := os.Chmod(path, mode); err != nil {
					t.Fatal(err)
				}
			case "empty":
				configTestWrite(t, path, nil)
			case "oversize":
				limit = 2
			case "directory":
				path = dir
			case "hardlink":
				if err := os.Link(path, filepath.Join(dir, "other-link")); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				alias := filepath.Join(dir, "alias")
				if err := os.Symlink(path, alias); err != nil {
					t.Fatal(err)
				}
				path = alias
			case "ancestor symlink":
				parent := filepath.Join(dir, "real")
				if err := os.Mkdir(parent, 0700); err != nil {
					t.Fatal(err)
				}
				configTestWrite(t, filepath.Join(parent, "private"), []byte("synthetic-private-fixture"))
				if err := os.Symlink(parent, filepath.Join(dir, "alias")); err != nil {
					t.Fatal(err)
				}
				path = filepath.Join(dir, "alias", "private")
			case "noncanonical ancestor":
				if err := os.Mkdir(filepath.Join(dir, "child"), 0700); err != nil {
					t.Fatal(err)
				}
				path = dir + "/child/../private"
			case "fifo":
				path = filepath.Join(dir, "fifo")
				if err := syscall.Mkfifo(path, 0600); err != nil {
					t.Fatal(err)
				}
			case "missing":
				path = filepath.Join(dir, "missing")
			case "relative":
				path = "private"
			case "zero limit":
				limit = 0
			case "oversize limit":
				limit = (1 << 20) + 1
			case "foreign owner":
				if os.Geteuid() != 0 {
					t.Skip("changing only a synthetic fixture's owner requires root")
				}
				if err := os.Chown(path, 1, -1); err != nil {
					t.Fatal(err)
				}
			}
			data, err := ReadPrivateFile(path, limit)
			if err == nil || data != nil || err.Error() != "private_file_refused" {
				t.Fatalf("unsafe file was accepted or leaked a diagnostic: data=%q err=%v", data, err)
			}
		})
	}
}

func TestPrivateFileAcceptsOnlyBoundedOwnerPrivateContents(t *testing.T) {
	path := filepath.Join(configTestDir(t), "private")
	want := []byte("synthetic-private-fixture")
	configTestWrite(t, path, want)
	for _, mode := range []os.FileMode{0600, 0400} {
		if err := os.Chmod(path, mode); err != nil {
			t.Fatal(err)
		}
		got, err := ReadPrivateFile(path, int64(len(want)))
		if err != nil || !bytes.Equal(got, want) {
			t.Fatalf("private exact-limit fixture refused: %v", err)
		}
	}
}

func configTestFixture(t *testing.T) (Config, ExecutionPermit, ed25519.PrivateKey, time.Time) {
	t.Helper()
	dir := configTestDir(t)
	authority := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{61}, 32))
	withdrawal := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{62}, 32))
	c := Config{Version: 1, Vault: testHTTPAddress(t, 120), PublicKeyHex: "02" + strings.Repeat("01", 32), BettingEscrow: testHTTPAddress(t, 121), ProtectedAddresses: []string{testHTTPAddress(t, 121)}, MaxAmountUWolo: 1000000,
		RPC: "https://primary.invalid", REST: "https://rest.invalid", WitnessRPC: "https://witness.invalid", TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("A", 64), PeriodSeconds: 3600, EvidenceReference: "synthetic-test-only"},
		KeyringDir: filepath.Join(dir, "unopened-keyring"), KeyName: "synthetic", PassphraseFile: filepath.Join(dir, "unopened-passphrase"), TokenFile: filepath.Join(dir, "unopened-token"), StatePath: filepath.Join(dir, "unopened-state"), PermitFile: filepath.Join(dir, "permit.json"), FeesUWolo: "5000", GasLimit: 120000, TimeoutBlocks: 20,
		ActivationAuthorityKeyHex: hex.EncodeToString(authority.Public().(ed25519.PublicKey)), WithdrawalApprovalKeyHex: hex.EncodeToString(withdrawal.Public().(ed25519.PublicKey)), WagerApprovalKeyHex: hex.EncodeToString(engineTestWagerApprovalKey().Public().(ed25519.PublicKey))}
	now := time.Unix(1800000000, 0)
	p := ExecutionPermit{Version: 1, Scope: "satchel-execution-v1", ConfigSHA256: strings.Repeat("1", 64), BinarySHA256: strings.Repeat("2", 64), Vault: c.Vault, IsolationEvidenceSHA256: strings.Repeat("3", 64), AccountingEvidenceSHA256: strings.Repeat("4", 64), RecoveryEvidenceSHA256: strings.Repeat("5", 64), Reviewer: "synthetic reviewer", Reference: "synthetic-test-only", IssuedAt: now.Unix() - 1, ExpiresAt: now.Unix() + 300}
	return c, p, authority, now
}

func configTestSign(p ExecutionPermit, key ed25519.PrivateKey) ExecutionPermit {
	p.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(key, PermitMessage(p)))
	return p
}

func configTestWritePermit(t *testing.T, c Config, p ExecutionPermit) {
	t.Helper()
	data, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	configTestWrite(t, c.PermitFile, data)
}

func TestExecutionPermitRequiresExactCryptographicFieldBinding(t *testing.T) {
	mutations := []struct {
		name string
		fn   func(*ExecutionPermit)
	}{
		{"version", func(p *ExecutionPermit) { p.Version++ }},
		{"scope", func(p *ExecutionPermit) { p.Scope += "-other" }},
		{"configuration", func(p *ExecutionPermit) { p.ConfigSHA256 = strings.Repeat("9", 64) }},
		{"binary", func(p *ExecutionPermit) { p.BinarySHA256 = strings.Repeat("9", 64) }},
		{"vault", func(p *ExecutionPermit) { p.Vault = testHTTPAddress(t, 122) }},
		{"isolation evidence", func(p *ExecutionPermit) { p.IsolationEvidenceSHA256 = strings.Repeat("9", 64) }},
		{"accounting evidence", func(p *ExecutionPermit) { p.AccountingEvidenceSHA256 = strings.Repeat("9", 64) }},
		{"recovery evidence", func(p *ExecutionPermit) { p.RecoveryEvidenceSHA256 = strings.Repeat("9", 64) }},
		{"reviewer", func(p *ExecutionPermit) { p.Reviewer += " changed" }},
		{"reference", func(p *ExecutionPermit) { p.Reference += " changed" }},
		{"issued", func(p *ExecutionPermit) { p.IssuedAt-- }},
		{"expiry", func(p *ExecutionPermit) { p.ExpiresAt++ }},
		{"signature", func(p *ExecutionPermit) { p.Signature = base64.StdEncoding.EncodeToString(make([]byte, 64)) }},
	}
	for _, test := range mutations {
		t.Run(test.name, func(t *testing.T) {
			c, p, key, now := configTestFixture(t)
			p = configTestSign(p, key)
			configTestWritePermit(t, c, p)
			if !verifyPermitAt(c, p.ConfigSHA256, p.BinarySHA256, now) {
				t.Fatal("genuine synthetic approval refused")
			}
			test.fn(&p)
			configTestWritePermit(t, c, p)
			if verifyPermitAt(c, strings.Repeat("1", 64), strings.Repeat("2", 64), now) {
				t.Fatal("tampered signed field authorized execution")
			}
		})
	}
}

func TestExecutionPermitRejectsSignedButInvalidAuthorityScope(t *testing.T) {
	for _, test := range []struct {
		name string
		fn   func(*ExecutionPermit, time.Time)
	}{
		{"empty isolation evidence", func(p *ExecutionPermit, _ time.Time) { p.IsolationEvidenceSHA256 = "" }},
		{"zero isolation evidence", func(p *ExecutionPermit, _ time.Time) { p.IsolationEvidenceSHA256 = strings.Repeat("0", 64) }},
		{"empty accounting evidence", func(p *ExecutionPermit, _ time.Time) { p.AccountingEvidenceSHA256 = "" }},
		{"zero accounting evidence", func(p *ExecutionPermit, _ time.Time) { p.AccountingEvidenceSHA256 = strings.Repeat("0", 64) }},
		{"empty recovery evidence", func(p *ExecutionPermit, _ time.Time) { p.RecoveryEvidenceSHA256 = "" }},
		{"zero recovery evidence", func(p *ExecutionPermit, _ time.Time) { p.RecoveryEvidenceSHA256 = strings.Repeat("0", 64) }},
		{"invalid proof digest", func(p *ExecutionPermit, _ time.Time) { p.RecoveryEvidenceSHA256 = strings.Repeat("g", 64) }},
		{"empty reviewer", func(p *ExecutionPermit, _ time.Time) { p.Reviewer = " \n " }},
		{"excess reviewer", func(p *ExecutionPermit, _ time.Time) { p.Reviewer = strings.Repeat("a", 129) }},
		{"empty reference", func(p *ExecutionPermit, _ time.Time) { p.Reference = "\t" }},
		{"excess reference", func(p *ExecutionPermit, _ time.Time) { p.Reference = strings.Repeat("a", 513) }},
		{"future issuance", func(p *ExecutionPermit, now time.Time) { p.IssuedAt = now.Unix() + 1 }},
		{"expired", func(p *ExecutionPermit, now time.Time) { p.ExpiresAt = now.Unix() }},
		{"reversed interval", func(p *ExecutionPermit, _ time.Time) { p.ExpiresAt = p.IssuedAt }},
		{"more than one day", func(p *ExecutionPermit, _ time.Time) { p.ExpiresAt = p.IssuedAt + 86401 }},
		{"overflowed interval", func(p *ExecutionPermit, _ time.Time) { p.IssuedAt, p.ExpiresAt = math.MinInt64, math.MaxInt64 }},
	} {
		t.Run(test.name, func(t *testing.T) {
			c, p, key, now := configTestFixture(t)
			test.fn(&p, now)
			p = configTestSign(p, key)
			configTestWritePermit(t, c, p)
			if verifyPermitAt(c, p.ConfigSHA256, p.BinarySHA256, now) {
				t.Fatal("invalid but correctly signed permit authorized execution")
			}
		})
	}
}

func TestExecutionPermitRefusesWrongKeysEncodingsAndChangedPrivateFiles(t *testing.T) {
	for _, name := range []string{"wrong signing key", "different authority key", "withdrawal key", "malformed authority key", "raw base64", "base64 newline", "short signature", "invalid signature encoding", "world readable", "hardlink", "symlink", "duplicate fields", "unknown fields", "trailing object", "invalid utf8", "oversize permit", "missing file", "different config bytes", "different binary bytes", "malformed config digest", "malformed binary digest"} {
		t.Run(name, func(t *testing.T) {
			c, p, key, now := configTestFixture(t)
			p = configTestSign(p, key)
			configDigest, binaryDigest := p.ConfigSHA256, p.BinarySHA256
			switch name {
			case "wrong signing key":
				p = configTestSign(p, ed25519.NewKeyFromSeed(bytes.Repeat([]byte{63}, 32)))
			case "different authority key":
				other := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{63}, 32))
				c.ActivationAuthorityKeyHex = hex.EncodeToString(other.Public().(ed25519.PublicKey))
			case "withdrawal key":
				p = configTestSign(p, ed25519.NewKeyFromSeed(bytes.Repeat([]byte{62}, 32)))
			case "malformed authority key":
				c.ActivationAuthorityKeyHex = "00"
			case "raw base64":
				p.Signature = strings.TrimRight(p.Signature, "=")
			case "base64 newline":
				p.Signature = p.Signature[:8] + "\n" + p.Signature[8:]
			case "short signature":
				p.Signature = base64.StdEncoding.EncodeToString(make([]byte, 63))
			case "invalid signature encoding":
				p.Signature = "!not-base64!"
			case "different config bytes":
				configDigest = strings.Repeat("9", 64)
			case "different binary bytes":
				binaryDigest = strings.Repeat("9", 64)
			case "malformed config digest":
				configDigest = "invalid"
			case "malformed binary digest":
				binaryDigest = "invalid"
			}
			configTestWritePermit(t, c, p)
			switch name {
			case "world readable":
				if err := os.Chmod(c.PermitFile, 0644); err != nil {
					t.Fatal(err)
				}
			case "hardlink":
				if err := os.Link(c.PermitFile, c.PermitFile+"-link"); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				if err := os.Symlink(c.PermitFile, c.PermitFile+"-alias"); err != nil {
					t.Fatal(err)
				}
				c.PermitFile += "-alias"
			case "duplicate fields", "unknown fields", "trailing object":
				b, _ := json.Marshal(p)
				if name == "duplicate fields" {
					b = append(b[:len(b)-1], []byte(`,"version":1}`)...)
				}
				if name == "unknown fields" {
					b = append(b[:len(b)-1], []byte(`,"certified":true}`)...)
				}
				if name == "trailing object" {
					b = append(b, []byte(`{}`)...)
				}
				configTestWrite(t, c.PermitFile, b)
			case "invalid utf8":
				configTestWrite(t, c.PermitFile, []byte{'{', '"', 0xff, '"', ':', '1', '}'})
			case "oversize permit":
				configTestWrite(t, c.PermitFile, bytes.Repeat([]byte{' '}, 16385))
			case "missing file":
				if err := os.Remove(c.PermitFile); err != nil {
					t.Fatal(err)
				}
			}
			if verifyPermitAt(c, configDigest, binaryDigest, now) {
				t.Fatal("untrusted permit or unsafe file authorized execution")
			}
		})
	}
}

func TestLoadConfigBindsExactBytesWithoutOpeningExecutionResources(t *testing.T) {
	c, _, _, _ := configTestFixture(t)
	path := filepath.Join(filepath.Dir(c.PermitFile), "config.json")
	data, err := json.Marshal(c)
	if err != nil {
		t.Fatal(err)
	}
	configTestWrite(t, path, data)
	got, digest, err := LoadConfig(path)
	sum := sha256.Sum256(data)
	if err != nil || digest != hex.EncodeToString(sum[:]) || got.Vault != c.Vault {
		t.Fatalf("valid configuration refused: %v", err)
	}
	configTestWrite(t, path, append(data, '\n'))
	_, changed, err := LoadConfig(path)
	if err != nil || changed == digest {
		t.Fatal("different exact configuration bytes reused permit digest")
	}
	for _, unopened := range []string{c.KeyringDir, c.PassphraseFile, c.TokenFile, c.StatePath, c.PermitFile} {
		if _, err := os.Lstat(unopened); !os.IsNotExist(err) {
			t.Fatal("configuration validation opened an execution resource")
		}
	}
	c.WithdrawalApprovalKeyHex = c.ActivationAuthorityKeyHex
	data, _ = json.Marshal(c)
	configTestWrite(t, path, data)
	if _, _, err := LoadConfig(path); err == nil {
		t.Fatal("shared activation/withdrawal approval authority accepted")
	}
}
