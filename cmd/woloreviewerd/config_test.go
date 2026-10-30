package main

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
)

// Synthetic, deterministic authority material is confined to tests. The
// command has no key creation/import/enrollment operation.
func testKey(n byte) ed25519.PrivateKey { return ed25519.NewKeyFromSeed(bytes.Repeat([]byte{n}, 32)) }
func testPublic(n byte) string          { return hex.EncodeToString(testKey(n).Public().(ed25519.PublicKey)) }
func testAddress(t *testing.T, n byte) string {
	t.Helper()
	words, e := bech32.ConvertBits(bytes.Repeat([]byte{n}, 20), 8, 5, true)
	if e != nil {
		t.Fatal(e)
	}
	s, e := bech32.Encode("wolo", words)
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func testConfig(t *testing.T) config {
	t.Helper()
	pin := func(name string) filePin { return filePin{Path: "/reviewed/" + name, SHA256: digest([]byte(name))} }
	c := config{
		Version: 1, SourceRevision: strings.Repeat("a", 40), BinarySHA256: strings.Repeat("b", 64), Vault: testAddress(t, 100), BettingEscrow: testAddress(t, 101),
		MaxAmountUWolo: 1_000_000, FeeUWolo: "250", MinimumGasReserveUWolo: "10000", MinimumUnencumberedUWolo: "1", RequiredProducerIDs: []string{},
		Roles:    roleConfig{testPublic(1), testPublic(2), testPublic(3), testPublic(4), testPublic(5)},
		Custody:  custodyPins{strings.Repeat("c", 64), strings.Repeat("d", 64), strings.Repeat("e", 64), strings.Repeat("f", 64)},
		Postgres: pgConfig{Host: "reviewer-db.invalid", Port: 5432, Database: "aoe2war", Role: "satchel_reviewer_independent", Password: pin("pg-password"), CA: pin("pg-ca"), ClientCertificate: pin("pg-cert"), ClientKey: pin("pg-key")},
		Watcher:  watcherConfig{Origin: "https://watcher.invalid", CA: pin("watcher-ca"), Token: pin("watcher-token"), ServerSPKISHA256: strings.Repeat("1", 64), WitnessPublicKeyHex: testPublic(6)},
		RPC:      "http://127.0.0.1:26657", REST: "http://127.0.0.1:1317", WitnessRPC: "https://witness.invalid",
		ReviewerPrivateKey: pin("reviewer-key"), HTTPToken: pin("reviewer-token"), CustodyToken: pin("custody-token"), JournalPath: "/reviewed/state/reviewer.db", ReserveCoveragePath: "/reviewed/coverage.json", PermitPath: "/reviewed/permit.json",
	}
	c.ProtectedAddresses = []string{c.BettingEscrow}
	c.TrustAnchor.Height = 42
	c.TrustAnchor.Hash = strings.Repeat("2", 64)
	c.TrustAnchor.PeriodSeconds = 3600
	c.TrustAnchor.EvidenceReference = "independently reviewed test anchor"
	p, e := c.policy()
	if e != nil {
		t.Fatal(e)
	}
	raw, e := json.Marshal(p)
	if e != nil {
		t.Fatal(e)
	}
	c.IssuerPolicySHA256 = digest(raw)
	return c
}
func TestStrictConfigRejectsIdentitySubstitution(t *testing.T) {
	c := testConfig(t)
	if c.validate() != nil {
		t.Fatal("synthetic full configuration refused")
	}
	raw, e := json.Marshal(c)
	if e != nil {
		t.Fatal(e)
	}
	var decoded config
	if strictJSON(raw, &decoded) != nil {
		t.Fatal("canonical schema refused")
	}
	for name, bad := range map[string][]byte{
		"duplicate":          bytes.Replace(raw, []byte(`"version":1`), []byte(`"version":1,"version":1`), 1),
		"case alias":         bytes.Replace(raw, []byte(`"version"`), []byte(`"VERSION"`), 1),
		"nested missing":     bytes.Replace(raw, []byte(`"port":5432,`), nil, 1),
		"null producer list": bytes.Replace(raw, []byte(`"required_producer_ids":[]`), []byte(`"required_producer_ids":null`), 1),
		"unknown":            append([]byte(`{"unreviewed_authority":true,`), raw[1:]...),
		"trailing":           append(append([]byte{}, raw...), []byte(` {}`)...),
	} {
		t.Run(name, func(t *testing.T) {
			var out config
			if strictJSON(bad, &out) == nil {
				t.Fatal("ambiguous or incomplete schema accepted")
			}
		})
	}
}
func TestConfigRequiresSeparatedPinnedReviewedInputs(t *testing.T) {
	mutations := map[string]func(*config){
		"role collision":           func(c *config) { c.Roles.CustodyPublicKeyHex = c.Roles.AccountingPublicKeyHex },
		"watcher signer collision": func(c *config) { c.Watcher.WitnessPublicKeyHex = c.Roles.WagerPublicKeyHex },
		"zero key":                 func(c *config) { c.Roles.AccountingPublicKeyHex = strings.Repeat("0", 64) },
		"placeholder root":         func(c *config) { c.Watcher.CA.SHA256 = strings.Repeat("0", 64) },
		"file alias":               func(c *config) { c.Postgres.Password.Path = c.ReviewerPrivateKey.Path },
		"state alias":              func(c *config) { c.JournalPath = c.PermitPath },
		"arbitrary watcher path":   func(c *config) { c.Watcher.Origin += "/review" },
		"insecure watcher":         func(c *config) { c.Watcher.Origin = "http://127.0.0.1:8096" },
		"remote cleartext bank":    func(c *config) { c.RPC = "http://rpc.invalid" },
		"same witness":             func(c *config) { c.WitnessRPC = c.RPC },
		"root role":                func(c *config) { c.Postgres.Role = "postgres" },
		"DSN override":             func(c *config) { c.Postgres.Host = "localhost sslmode=disable" },
		"vault destination":        func(c *config) { c.ProtectedAddresses = append(c.ProtectedAddresses, c.Vault) },
		"wrong policy bytes":       func(c *config) { c.IssuerPolicySHA256 = strings.Repeat("3", 64) },
		"unbounded canary":         func(c *config) { c.MaxAmountUWolo = 1_000_001 },
		"unreviewed anchor":        func(c *config) { c.TrustAnchor.EvidenceReference = "" },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			c := testConfig(t)
			mutate(&c)
			if c.validate() == nil {
				t.Fatal("unreviewed or colliding source accepted")
			}
		})
	}
}
func testPermit(c config, now time.Time) startupPermit {
	p := startupPermit{Version: 1, Scope: permitScope, ConfigSHA256: strings.Repeat("4", 64), BinarySHA256: c.BinarySHA256, SourceRevision: c.SourceRevision, IssuerPolicySHA256: c.IssuerPolicySHA256, Vault: c.Vault, WagerPublicKeyHex: c.Roles.WagerPublicKeyHex, IssuedAt: now.Unix() - 1, ExpiresAt: now.Unix() + 60}
	p.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(testKey(3), permitMessage(p)))
	return p
}
func signTestPermit(p startupPermit) string {
	return base64.StdEncoding.EncodeToString(ed25519.Sign(testKey(3), permitMessage(p)))
}
func TestStartupPermitIsExactScopedShortLivedAndIndependent(t *testing.T) {
	c := testConfig(t)
	now := time.Unix(1_800_000_000, 0)
	p := testPermit(c, now)
	if !verifyPermit(c, p.ConfigSHA256, c.BinarySHA256, p, now) {
		t.Fatal("exact independent test permit refused")
	}
	for name, mutate := range map[string]func(*startupPermit){
		"custody permit": func(p *startupPermit) { p.Scope = "satchel-execution-v1" },
		"config":         func(p *startupPermit) { p.ConfigSHA256 = strings.Repeat("5", 64) },
		"binary":         func(p *startupPermit) { p.BinarySHA256 = strings.Repeat("5", 64) },
		"source":         func(p *startupPermit) { p.SourceRevision = strings.Repeat("5", 40) },
		"policy":         func(p *startupPermit) { p.IssuerPolicySHA256 = strings.Repeat("5", 64) },
		"vault":          func(p *startupPermit) { p.Vault = c.BettingEscrow },
		"signer":         func(p *startupPermit) { p.WagerPublicKeyHex = c.Roles.WithdrawalPublicKeyHex },
		"expired":        func(p *startupPermit) { p.ExpiresAt = now.Unix() },
		"future":         func(p *startupPermit) { p.IssuedAt = now.Unix() + 1 },
		"long lived":     func(p *startupPermit) { p.ExpiresAt = p.IssuedAt + 121 },
	} {
		t.Run(name, func(t *testing.T) {
			bad := p
			mutate(&bad)
			bad.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(testKey(3), permitMessage(bad)))
			if verifyPermit(c, p.ConfigSHA256, c.BinarySHA256, bad, now) {
				t.Fatal("incorrect permit admitted")
			}
		})
	}
	p.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(testKey(4), permitMessage(p)))
	if verifyPermit(c, p.ConfigSHA256, c.BinarySHA256, p, now) {
		t.Fatal("wager signer self-authorized startup")
	}
}
func TestBuildPinRejectsDirtyMissingAndConflictingVCS(t *testing.T) {
	revision := strings.Repeat("a", 40)
	clean := &debug.BuildInfo{Settings: []debug.BuildSetting{{Key: "vcs", Value: "git"}, {Key: "vcs.revision", Value: revision}, {Key: "vcs.modified", Value: "false"}}}
	if !sourcePinned(clean, revision) {
		t.Fatal("clean pinned source refused")
	}
	if sourcePinned(nil, revision) || sourcePinned(clean, strings.Repeat("b", 40)) {
		t.Fatal("missing/wrong source admitted")
	}
	dirty := *clean
	dirty.Settings = append([]debug.BuildSetting{}, clean.Settings...)
	dirty.Settings[2].Value = "true"
	if sourcePinned(&dirty, revision) {
		t.Fatal("dirty source admitted")
	}
	clean.Settings = append(clean.Settings, debug.BuildSetting{Key: "vcs.modified", Value: "false"})
	if sourcePinned(clean, revision) {
		t.Fatal("conflicting VCS metadata admitted")
	}
}
func TestPinnedFileCannotChangeOrBecomePublic(t *testing.T) {
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "selected-input")
	raw := []byte("synthetic protected input")
	if os.WriteFile(path, raw, 0600) != nil {
		t.Fatal("write fixture")
	}
	p := filePin{path, digest(raw)}
	if _, e := readPinned(p); e != nil {
		t.Fatal("original protected fixture refused")
	}
	if os.WriteFile(path, []byte("replacement"), 0600) != nil {
		t.Fatal("replace fixture")
	}
	if _, e := readPinned(p); e == nil {
		t.Fatal("replacement admitted under old pin")
	}
	if os.WriteFile(path, raw, 0600) != nil || os.Chmod(path, 0644) != nil {
		t.Fatal("change fixture permissions")
	}
	if _, e := readPinned(p); e == nil {
		t.Fatal("public protected input admitted")
	}
}
