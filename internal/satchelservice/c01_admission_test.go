package satchelservice

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

type c01Fixture struct {
	c                  C01StartupConfig
	revision, binary   string
	trust              C08V3Trust
	owner              *ecdsa.PrivateKey
	now                time.Time
	request            []any
	rawReceipt, public []byte
}

func c01TestSignature(t *testing.T, owner *ecdsa.PrivateKey, domain string, req any) string {
	t.Helper()
	raw, err := c08Canonical(req)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(append([]byte(domain), raw...))
	signature, err := ecdsa.SignASN1(rand.Reader, owner, digest[:])
	if err != nil {
		t.Fatal(err)
	}
	return base64.StdEncoding.EncodeToString(signature)
}

func c01WriteTestFile(t *testing.T, path string, raw []byte) {
	t.Helper()
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
}

func makeC01Fixture(t *testing.T) c01Fixture {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	_, trust, governanceRequest, sign := c08V3Fixture(t)
	receipt := sign(governanceRequest)
	owner, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	public := elliptic.Marshal(elliptic.P256(), owner.X, owner.Y)
	trust.OwnerKeySHA = c08HexSHA(public)
	governanceRequest["owner_public_x963_sha256"] = trust.OwnerKeySHA
	packet := map[string]any{
		"schema": c08V3PacketSchema, "request": governanceRequest,
		"signature_der_b64": c01TestSignature(t, owner, c08V3SignatureDomain, governanceRequest),
	}
	raw, err := c08Canonical(packet)
	if err != nil {
		t.Fatal(err)
	}
	receipt["signed_packet"], receipt["signed_packet_sha256"] = packet, c08HexSHA(raw)
	receipt["owner_public_x963_sha256"] = trust.OwnerKeySHA
	rawReceipt := c08V3Raw(t, receipt)
	trust.ReceiptSHA = c08HexSHA(rawReceipt)
	config := []byte(`{"mode":"zero-funded-fixture"}` + "\n")
	f := c01Fixture{
		c: C01StartupConfig{
			Role: C01CustodyRole, ConfigFile: filepath.Join(dir, "config.json"),
			ConfigSHA256: c08HexSHA(config), KeyFingerprintSHA256: strings.Repeat("e", 64),
			C08ReceiptFile: filepath.Join(dir, "receipt.json"), C08OwnerPublicFile: filepath.Join(dir, "owner.bin"),
			PermitFile: filepath.Join(dir, "permit.json"),
		},
		trust: trust, owner: owner, revision: strings.Repeat("a", 40), binary: strings.Repeat("b", 64),
		now:        time.Date(2026, 11, 9, 21, 23, 0, 0, time.UTC),
		rawReceipt: rawReceipt, public: public,
	}
	f.request = []any{f.c.Role, "wolo-1", f.revision, f.binary, f.c.ConfigSHA256,
		f.c.KeyFingerprintSHA256, trust.PolicySHA, trust.ReceiptSHA, strings.Repeat("f", 64),
		"2026-11-09T21:22:00Z", "2026-11-09T21:27:00Z", json.Number("0")}
	c01WriteTestFile(t, f.c.ConfigFile, config)
	c01WriteTestFile(t, f.c.C08ReceiptFile, rawReceipt)
	c01WriteTestFile(t, f.c.C08OwnerPublicFile, public)
	f.writePermit(t, f.owner, c01StartupDomain, f.request)
	return f
}

func (f c01Fixture) writePermit(t *testing.T, key *ecdsa.PrivateKey, domain string, req []any) {
	t.Helper()
	raw := c08V3Raw(t, map[string]any{
		"schema": c01StartupSchema, "request": req,
		"signature_der_b64": c01TestSignature(t, key, domain, req),
	})
	c01WriteTestFile(t, f.c.PermitFile, raw)
}

func TestC01StartupBindsExactC08AndZeroFunds(t *testing.T) {
	f := makeC01Fixture(t)
	if grant, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err != nil || grant == nil {
		t.Fatalf("valid fresh startup refused: %v", err)
	}
	// Even correctly owner-signed changes are refused.
	for _, tc := range []struct {
		name  string
		index int
		value any
	}{
		{"role", 0, C01ReviewerRole},
		{"chain", 1, "wolo-2"},
		{"source", 2, strings.Repeat("a", 39) + "b"},
		{"binary", 3, strings.Repeat("d", 64)},
		{"config", 4, strings.Repeat("d", 64)},
		{"key", 5, strings.Repeat("d", 64)},
		{"policy", 6, strings.Repeat("d", 64)},
		{"receipt", 7, strings.Repeat("d", 64)},
		{"nonce_uppercase", 8, strings.Repeat("A", 64)},
		{"nonce_zero", 8, strings.Repeat("0", 64)},
		{"nonce_traversal", 8, "../" + strings.Repeat("f", 61)},
		{"future", 9, "2026-11-09T21:24:00Z"},
		{"expiry", 10, "2026-11-09T21:23:00Z"},
		{"overlong", 10, "2026-11-09T21:27:01Z"},
		{"funded", 11, json.Number("1")},
		{"text_allowance", 11, "0"},
		{"noncanonical_allowance", 11, json.Number("0.0")},
	} {
		t.Run(tc.name, func(t *testing.T) {
			mutated := append([]any(nil), f.request...)
			mutated[tc.index] = tc.value
			f.writePermit(t, f.owner, c01StartupDomain, mutated)
			if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
				t.Fatal("invalid signed request accepted")
			}
		})
	}

	t.Run("C08 governance signature cannot authorize startup", func(t *testing.T) {
		f.writePermit(t, f.owner, c08V3SignatureDomain, f.request)
		if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
			t.Fatal("wrong domain accepted")
		}
	})

	t.Run("wrong owner cannot authorize", func(t *testing.T) {
		other, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			t.Fatal(err)
		}
		f.writePermit(t, other, c01StartupDomain, f.request)
		if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
			t.Fatal("wrong owner signature accepted")
		}
	})

	t.Run("duplicate fields", func(t *testing.T) {
		f.writePermit(t, f.owner, c01StartupDomain, f.request)
		raw, err := os.ReadFile(f.c.PermitFile)
		if err != nil {
			t.Fatal(err)
		}
		c01WriteTestFile(t, f.c.PermitFile, append([]byte(`{"schema":"alias",`), raw[1:]...))
		if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
			t.Fatal("duplicate permit schema accepted")
		}
	})

	t.Run("altered actual receipt and key", func(t *testing.T) {
		f.writePermit(t, f.owner, c01StartupDomain, f.request)
		c01WriteTestFile(t, f.c.C08ReceiptFile, append(append([]byte(nil), f.rawReceipt...), '\n'))
		if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
			t.Fatal("changed actual policy receipt accepted")
		}
		c01WriteTestFile(t, f.c.C08ReceiptFile, f.rawReceipt)
		public := append([]byte(nil), f.public...)
		public[len(public)-1] ^= 1
		c01WriteTestFile(t, f.c.C08OwnerPublicFile, public)
		if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
			t.Fatal("changed actual owner key accepted")
		}
	})
}

func TestC01NonceDurabilityAndRevocation(t *testing.T) {
	f := makeC01Fixture(t)
	ctx := context.Background()
	grant, nonce, record, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now)
	if err != nil {
		t.Fatal(err)
	}
	if grant.currentAt(ctx, f.now) {
		t.Fatal("uncommitted nonce qualified an active grant")
	}
	path, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	dir, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	uid, gid := uint32(os.Geteuid()), uint32(os.Getegid())
	results := make(chan error, 2)
	for i := 0; i < cap(results); i++ {
		go func() { results <- consumeC01Nonce(dir, nonce, record, uid, gid) }()
	}
	first, second := <-results, <-results
	if !(first == nil && errors.Is(second, unix.EEXIST) || second == nil && errors.Is(first, unix.EEXIST)) {
		t.Fatalf("same nonce did not have exactly one durable claimant: %v / %v", first, second)
	}
	if err := dir.Close(); err != nil {
		t.Fatal(err)
	}
	dir, err = os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer dir.Close()
	if err := consumeC01Nonce(dir, nonce, record, uid, gid); !errors.Is(err, unix.EEXIST) {
		t.Fatalf("reopened journal accepted replay: %v", err)
	}
	blocked := strings.Repeat("c", 64)
	if err := os.Symlink("missing", filepath.Join(path, blocked)); err != nil {
		t.Fatal(err)
	}
	if err := consumeC01Nonce(dir, blocked, record, uid, gid); !errors.Is(err, unix.EEXIST) {
		t.Fatalf("nonce symlink was overwritten: %v", err)
	}

	marker := filepath.Join(path, nonce)
	bindMarker := func(grant *C01NonfundedAdmission) {
		grant.files = append(grant.files, c01FilePin{marker, c08HexSHA(record), 128})
	}
	bindMarker(grant)
	if grant.Role() != f.c.Role || !c01Hex(grant.RequestSHA256(), 32) ||
		grant.NonceSHA256() != c08HexSHA([]byte(nonce)) || !grant.currentAt(ctx, f.now) {
		t.Fatal("durable grant or public commitments incorrect")
	}
	if grant.currentAt(ctx, grant.ExpiresAt()) || grant.currentAt(ctx, f.now) {
		t.Fatal("expired grant could be restored by moving time backward")
	}
	// All cases below re-construct the same fixture grant independently;
	// production would also require a new nonce and hence could not do this.
	for _, path := range []string{marker, f.c.ConfigFile, f.c.C08ReceiptFile, f.c.PermitFile} {
		t.Run(filepath.Base(path), func(t *testing.T) {
			grant, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now)
			if err != nil {
				t.Fatal(err)
			}
			bindMarker(grant)
			if !grant.currentAt(ctx, f.now) {
				t.Fatal("fixture grant refused")
			}
			before, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.Remove(path); err != nil {
				t.Fatal(err)
			}
			if grant.currentAt(ctx, f.now) {
				t.Fatal("removed authorization input kept grant current")
			}
			c01WriteTestFile(t, path, before)
			if grant.currentAt(ctx, f.now) {
				t.Fatal("reinstating bytes revived revoked grant")
			}
		})
	}
}

func TestC01StartupRequiresCleanVCS(t *testing.T) {
	revision := strings.Repeat("f", 40)
	info := &debug.BuildInfo{Settings: []debug.BuildSetting{
		{Key: "vcs", Value: "git"},
		{Key: "vcs.revision", Value: revision},
		{Key: "vcs.modified", Value: "false"},
	}}
	if c01SourceRevision(info) != revision {
		t.Fatal("clean VCS metadata refused")
	}
	info.Settings = append(info.Settings, debug.BuildSetting{Key: "vcs.modified", Value: "false"})
	if c01SourceRevision(info) != "" {
		t.Fatal("duplicate VCS metadata accepted")
	}
	info.Settings = info.Settings[:3]
	info.Settings[2].Value = "true"
	if c01SourceRevision(info) != "" {
		t.Fatal("dirty VCS metadata accepted")
	}
}

func TestC01StartupPreparationDoesNotReadPermit(t *testing.T) {
	f := makeC01Fixture(t)
	f.c.Role, f.request[0] = C01ReviewerRole, C01ReviewerRole
	if err := os.Remove(f.c.PermitFile); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readC01StartupInputs(f.c, f.revision, f.binary, f.trust); err != nil {
		t.Fatalf("unsigned preparation required a permit: %v", err)
	}
	if _, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now); err == nil {
		t.Fatal("reviewer startup accepted a missing permit")
	}
	f.writePermit(t, f.owner, c01StartupDomain, f.request)
	grant, _, _, err := verifyC01Startup(f.c, f.revision, f.binary, f.trust, f.now)
	if err != nil || grant.Role() != C01ReviewerRole {
		t.Fatalf("exact reviewer authorization refused: %v", err)
	}
}
