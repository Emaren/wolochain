package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchelservice"
	"github.com/lib/pq"
)

func TestPostgresEnvironmentCannotSelectCredentialsOrTransport(t *testing.T) {
	for _, env := range [][]string{{"PGHOST=other"}, {"PGSERVICE=secret-service"}, {"PGSSLKEY=implicit-key"}, {"PGPASSWORD=do-not-print"}, {"PGUNSUPPORTED=also-refuse"}, {"pgport=5433"}} {
		if !pgEnvironmentPresent(env) {
			t.Fatal("PostgreSQL environment override accepted")
		}
	}
	if pgEnvironmentPresent([]string{"HOME=/synthetic", "HTTP_PROXY=http://unused.invalid", "OTHER=value"}) {
		t.Fatal("unrelated environment refused")
	}
}
func testTLSMaterial(t *testing.T) ([]byte, []byte) {
	t.Helper()
	key := testKey(20)
	now := time.Unix(1_800_000_000, 0)
	cert := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test-only-db-client"}, NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	der, e := x509.CreateCertificate(rand.Reader, cert, cert, key.Public().(ed25519.PublicKey), key)
	if e != nil {
		t.Fatal(e)
	}
	private, e := x509.MarshalPKCS8PrivateKey(key)
	if e != nil {
		t.Fatal(e)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: private})
}
func TestPostgresUsesOnlyExplicitInlineTLSAndQuotedPassword(t *testing.T) {
	c := testConfig(t).Postgres
	cert, key := testTLSMaterial(t)
	inputs := map[string][]byte{c.CA.Path: cert, c.ClientCertificate.Path: cert, c.ClientKey.Path: key, c.Password.Path: []byte("test\\' password sslmode=disable")}
	dsn, e := pgDSN(c, inputs)
	if e != nil {
		t.Fatal("explicit test TLS configuration refused")
	}
	for _, setting := range []string{"sslmode='verify-full'", "sslinline='true'", "default_transaction_read_only=on", "statement_timeout=2000", "lock_timeout=500", "connect_timeout='2'"} {
		if !strings.Contains(dsn, setting) {
			t.Fatal("bounded readonly TLS option missing")
		}
	}
	if !strings.Contains(dsn, "password="+pqQuote(string(inputs[c.Password.Path]))) {
		t.Fatal("password escaped outside its single value")
	}
	// Parse without dialing or opening PostgreSQL. No credential/DSN is printed.
	if pgEnvironmentPresent(os.Environ()) {
		if db, e := openPG(context.Background(), c, inputs); e == nil || db != nil {
			t.Fatal("ambient PostgreSQL environment did not fail before connection")
		}
	} else if _, e := pq.NewConnector(dsn); e != nil {
		t.Fatal("explicit DSN could not be parsed")
	}
	inputs[c.Password.Path] = nil
	if _, e := pgDSN(c, inputs); e == nil {
		t.Fatal("implicit password discovery allowed")
	}
	inputs[c.Password.Path] = []byte("synthetic")
	inputs[c.CA.Path] = []byte("not a CA")
	if _, e := pgDSN(c, inputs); e == nil {
		t.Fatal("implicit system CA fallback allowed")
	}
	inputs[c.CA.Path] = cert
	inputs[c.ClientKey.Path] = []byte("not a client key")
	if _, e := pgDSN(c, inputs); e == nil {
		t.Fatal("implicit home client key fallback allowed")
	}
}

type sourceProbe struct {
	called int
	hold   func(context.Context, string) (satchelservice.WagerReservation, error)
	fee    func(context.Context, satchelservice.WagerReservation) (satchelservice.ReviewerFeeCensus, error)
}

func (s *sourceProbe) OriginalHold(ctx context.Context, id string) (satchelservice.WagerReservation, error) {
	s.called++
	return s.hold(ctx, id)
}
func (s *sourceProbe) VerifyOwnerMandate(context.Context, satchelservice.WagerReservation) error {
	s.called++
	return nil
}
func (s *sourceProbe) VerifyWatcherMarket(context.Context, satchelservice.WagerReservation) error {
	s.called++
	return nil
}
func (s *sourceProbe) AuthenticatedFeeCensus(ctx context.Context, w satchelservice.WagerReservation) (satchelservice.ReviewerFeeCensus, error) {
	s.called++
	return s.fee(ctx, w)
}
func TestSourceGuardDeniesBeforeIOAndAfterRevocation(t *testing.T) {
	allowed := false
	probe := &sourceProbe{hold: func(context.Context, string) (satchelservice.WagerReservation, error) {
		allowed = false
		return satchelservice.WagerReservation{OperationID: "original"}, nil
	}}
	s := &guardedSource{inner: probe, allow: func(context.Context) bool { return allowed }}
	ctx := context.Background()
	if _, e := s.OriginalHold(ctx, "original"); e == nil || probe.called != 0 {
		t.Fatal("held source performed I/O")
	}
	allowed = true
	if result, e := s.OriginalHold(ctx, "original"); e == nil || result.OperationID != "" || probe.called != 1 {
		t.Fatal("in-flight revocation leaked an original hold")
	}
	if s.VerifyOwnerMandate(ctx, satchelservice.WagerReservation{}) == nil || s.VerifyWatcherMarket(ctx, satchelservice.WagerReservation{}) == nil || probe.called != 1 {
		t.Fatal("held downstream source performed I/O")
	}
}
func TestSourceGuardPreservesPrivateIssuerCheckpointContext(t *testing.T) {
	type contextKey struct{}
	ctx := context.WithValue(context.Background(), contextKey{}, "private process checkpoint")
	probe := &sourceProbe{fee: func(received context.Context, _ satchelservice.WagerReservation) (satchelservice.ReviewerFeeCensus, error) {
		if received != ctx || received.Value(contextKey{}) != "private process checkpoint" {
			t.Fatal("issuer context was replaced")
		}
		return satchelservice.ReviewerFeeCensus{}, nil
	}}
	s := &guardedSource{inner: probe, allow: func(context.Context) bool { return true }}
	if _, e := s.AuthenticatedFeeCensus(ctx, satchelservice.WagerReservation{}); e != nil || probe.called != 1 {
		t.Fatal("protected context did not reach census")
	}
}
func TestHTTPGuardWithholdsApprovalWhenPermitIsRevokedDuringReview(t *testing.T) {
	allowed := true
	called := 0
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called++
		w.Header().Set("X-Approval", "sensitive")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"approval":"must-not-leak"}`))
		allowed = false
	})
	h := guardHTTP(next, func(context.Context) bool { return allowed })
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8095/reviewer/v1/wagers", nil))
	if called != 1 || w.Code != http.StatusServiceUnavailable || strings.Contains(w.Body.String(), "must-not-leak") || w.Header().Get("X-Approval") != "" || w.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("revoked approval escaped response fence")
	}
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8095/reviewer/v1/wagers", nil))
	if called != 1 || w.Code != http.StatusServiceUnavailable {
		t.Fatal("held HTTP performed review")
	}
}
func TestHTTPGuardBoundsBufferedOutput(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(strings.Repeat("x", (32<<10)+1))) })
	w := httptest.NewRecorder()
	guardHTTP(next, func(context.Context) bool { return true }).ServeHTTP(w, httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8095", nil))
	if w.Code != http.StatusServiceUnavailable || len(w.Body.Bytes()) > 100 {
		t.Fatal("unbounded approval output escaped")
	}
}
func TestJournalRequiresPreexistingPrivateOwnedParentAndNoAliases(t *testing.T) {
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "reviewer.db")
	if privateJournalPath(path) != nil {
		t.Fatal("new private journal path refused")
	}
	if privateJournalPath(filepath.Join(dir, "missing", "reviewer.db")) == nil {
		t.Fatal("implicit state provisioning allowed")
	}
	if os.WriteFile(path, []byte("synthetic journal"), 0600) != nil {
		t.Fatal("journal fixture")
	}
	link := filepath.Join(dir, "alias.db")
	if os.Link(path, link) != nil {
		t.Fatal("hardlink fixture")
	}
	if privateJournalPath(path) == nil {
		t.Fatal("shared journal file accepted")
	}
	if os.Remove(link) != nil || os.Symlink(path, link) != nil {
		t.Fatal("symlink fixture")
	}
	if privateJournalPath(link) == nil {
		t.Fatal("symlink journal accepted")
	}
	if os.Chmod(dir, 0755) != nil {
		t.Fatal("parent fixture")
	}
	if privateJournalPath(path) == nil {
		t.Fatal("public journal parent accepted")
	}
}
func TestInputGateRechecksSignedPermitAndPinnedFiles(t *testing.T) {
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	c := testConfig(t)
	refs := []*filePin{&c.Postgres.Password, &c.Postgres.CA, &c.Postgres.ClientCertificate, &c.Postgres.ClientKey, &c.Watcher.CA, &c.Watcher.Token, &c.ReviewerPrivateKey, &c.HTTPToken, &c.CustodyToken}
	for _, ref := range refs {
		ref.Path = filepath.Join(dir, filepath.Base(ref.Path))
		raw := []byte("synthetic protected gate input " + ref.Path)
		ref.SHA256 = digest(raw)
		if os.WriteFile(ref.Path, raw, 0600) != nil {
			t.Fatal("input fixture")
		}
	}
	c.JournalPath = filepath.Join(dir, "reviewer.db")
	c.PermitPath = filepath.Join(dir, "permit.json")
	c.ReserveCoveragePath = filepath.Join(dir, "coverage.json")
	path := filepath.Join(dir, "config.json")
	raw, e := json.Marshal(c)
	if e != nil || os.WriteFile(path, raw, 0600) != nil {
		t.Fatal("config fixture")
	}
	now := time.Unix(1_800_000_000, 0)
	p := testPermit(c, now)
	p.ConfigSHA256 = digest(raw)
	// Re-sign only synthetic test material after selecting the exact config.
	p.Signature = signTestPermit(p)
	writePermit := func() {
		t.Helper()
		raw, e := json.Marshal(p)
		if e != nil || os.WriteFile(c.PermitPath, raw, 0600) != nil {
			t.Fatal("permit fixture")
		}
	}
	writePermit()
	g := &inputGate{config: c, path: path, configDigest: digest(raw), binaryDigest: c.BinarySHA256, now: func() time.Time { return now }}
	if !g.allowedForEnvironment(context.Background(), nil) {
		t.Fatal("exact protected gate fixture refused")
	}
	if g.allowedForEnvironment(context.Background(), []string{"PGSERVICE=unreviewed"}) {
		t.Fatal("environment override admitted with otherwise valid protected inputs")
	}
	now = now.Add(61 * time.Second)
	if g.allowedForEnvironment(context.Background(), nil) {
		t.Fatal("expired startup permit remained accepting")
	}
	now = now.Add(-61 * time.Second)
	if os.WriteFile(c.HTTPToken.Path, []byte("unreviewed replacement"), 0600) != nil {
		t.Fatal("input mutation")
	}
	if g.allowedForEnvironment(context.Background(), nil) {
		t.Fatal("changed selected input remained accepting")
	}
}
