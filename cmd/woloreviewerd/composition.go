package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"database/sql"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
	"github.com/lib/pq"
)

// This guard reopens protected inputs; changes require a separately reviewed
// restart/config permit. Signed coverage and permits may rotate at their fixed
// configured paths, but neither can change an enrolled identity or source.
type inputGate struct {
	config                           config
	path, configDigest, binaryDigest string
	now                              func() time.Time
}

func (g *inputGate) allowed(ctx context.Context) bool {
	return g.allowedForEnvironment(ctx, os.Environ())
}

// Environment is explicit here only for deterministic source tests; every
// production gate entry above reads the actual process environment.
func (g *inputGate) allowedForEnvironment(ctx context.Context, environment []string) bool {
	if g == nil || ctx == nil || ctx.Err() != nil || pgEnvironmentPresent(environment) {
		return false
	}
	raw, e := satchelservice.ReadPrivateFile(g.path, 64<<10)
	if e != nil || digest(raw) != g.configDigest || privateJournalPath(g.config.JournalPath) != nil {
		return false
	}
	for _, p := range g.config.pins() {
		b, e := readPinned(p)
		wipe(b)
		if e != nil {
			return false
		}
	}
	raw, e = satchelservice.ReadPrivateFile(g.config.PermitPath, 16<<10)
	var permit startupPermit
	return e == nil && strictJSON(raw, &permit) == nil && verifyPermit(g.config, g.configDigest, g.binaryDigest, permit, g.now()) && ctx.Err() == nil
}
func pgEnvironmentPresent(env []string) bool {
	for _, item := range env {
		name, _, _ := strings.Cut(item, "=")
		if strings.HasPrefix(strings.ToUpper(name), "PG") {
			return true
		}
	}
	return false
}
func wipe(raw []byte) {
	for i := range raw {
		raw[i] = 0
	}
}

// No mkdir, chmod, symlink repair, home-directory discovery or alternate state
// path. The separately provisioned dedicated parent must already be private.
func privateJournalPath(path string) error {
	if !validPath(path) {
		return errHeld
	}
	parent := filepath.Dir(path)
	real, e := filepath.EvalSymlinks(parent)
	if e != nil || real != parent {
		return errHeld
	}
	st, e := os.Lstat(parent)
	if e != nil || !st.IsDir() || st.Mode().Perm()&0077 != 0 {
		return errHeld
	}
	sys, ok := st.Sys().(*syscall.Stat_t)
	if !ok || sys.Uid != uint32(os.Geteuid()) {
		return errHeld
	}
	st, e = os.Lstat(path)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil || !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 {
		return errHeld
	}
	sys, ok = st.Sys().(*syscall.Stat_t)
	if !ok || sys.Uid != uint32(os.Geteuid()) || sys.Nlink != 1 {
		return errHeld
	}
	return nil
}
func pinnedBytes(c config) (map[string][]byte, error) {
	out := map[string][]byte{}
	for _, p := range c.pins() {
		b, e := readPinned(p)
		if e != nil {
			for _, v := range out {
				wipe(v)
			}
			return nil, errHeld
		}
		out[p.Path] = b
	}
	return out, nil
}
func pinnedToken(pin filePin, inputs map[string][]byte) (string, error) {
	token := strings.TrimSpace(string(inputs[pin.Path]))
	if !tokenPattern.MatchString(token) {
		return "", errHeld
	}
	return token, nil
}
func certificatePool(raw []byte) (*x509.CertPool, error) {
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(raw) {
		return nil, errHeld
	}
	return pool, nil
}

// lib/pq's inline TLS mode prevents a second filesystem read and its implicit
// ~/.postgresql certificate/key discovery. Every argument is explicit. A
// nonempty protected password also prevents .pgpass fallback. PG* environment
// variables are rejected before invoking pq (including unsupported variables).
func pgDSN(c pgConfig, inputs map[string][]byte) (string, error) {
	password := string(inputs[c.Password.Path])
	if len(password) == 0 || len(password) > 4096 || strings.ContainsRune(password, 0) {
		return "", errHeld
	}
	if _, e := certificatePool(inputs[c.CA.Path]); e != nil {
		return "", errHeld
	}
	if _, e := tls.X509KeyPair(inputs[c.ClientCertificate.Path], inputs[c.ClientKey.Path]); e != nil {
		return "", errHeld
	}
	values := [][2]string{
		{"host", c.Host}, {"port", strconv.Itoa(int(c.Port))}, {"dbname", c.Database}, {"user", c.Role}, {"password", password},
		{"sslmode", "verify-full"}, {"sslinline", "true"}, {"sslrootcert", string(inputs[c.CA.Path])},
		{"sslcert", string(inputs[c.ClientCertificate.Path])}, {"sslkey", string(inputs[c.ClientKey.Path])},
		{"connect_timeout", "2"}, {"application_name", "wolo-independent-reviewer"},
		{"options", "-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=500 -c idle_in_transaction_session_timeout=2000"},
	}
	parts := make([]string, 0, len(values))
	for _, v := range values {
		parts = append(parts, v[0]+"="+pqQuote(v[1]))
	}
	return strings.Join(parts, " "), nil
}
func pqQuote(s string) string {
	return "'" + strings.NewReplacer(`\`, `\\`, `'`, `\'`).Replace(s) + "'"
}
func openPG(ctx context.Context, c pgConfig, inputs map[string][]byte) (*sql.DB, error) {
	if pgEnvironmentPresent(os.Environ()) {
		return nil, errHeld
	}
	dsn, e := pgDSN(c, inputs)
	if e != nil {
		return nil, errHeld
	}
	connector, e := pq.NewConnector(dsn)
	if e != nil {
		return nil, errHeld
	}
	db := sql.OpenDB(connector)
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(0)
	db.SetConnMaxLifetime(time.Minute)
	check, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	if db.PingContext(check) != nil {
		_ = db.Close()
		return nil, errHeld
	}
	// Startup rejects even an apparently successful login under another role.
	// The production PG adapters additionally verify table/column privileges,
	// role memberships and owner-ledger consistency on each evidence read.
	var login, role, readonly string
	var privileged bool
	e = db.QueryRowContext(check, `SELECT session_user,current_user,current_setting('transaction_read_only'),
 COALESCE((SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolreplication
 FROM pg_catalog.pg_roles WHERE rolname=current_user),true)`).Scan(&login, &role, &readonly, &privileged)
	if e != nil || login != c.Role || role != c.Role || readonly != "on" || privileged {
		_ = db.Close()
		return nil, errHeld
	}
	return db, nil
}

type guardedSource struct {
	inner satchelservice.ReviewerEvidenceSource
	allow func(context.Context) bool
}

func (s *guardedSource) OriginalHold(ctx context.Context, id string) (satchelservice.WagerReservation, error) {
	if !s.allow(ctx) {
		return satchelservice.WagerReservation{}, errHeld
	}
	v, e := s.inner.OriginalHold(ctx, id)
	if !s.allow(ctx) {
		return satchelservice.WagerReservation{}, errHeld
	}
	return v, e
}
func (s *guardedSource) VerifyOwnerMandate(ctx context.Context, v satchelservice.WagerReservation) error {
	if !s.allow(ctx) {
		return errHeld
	}
	e := s.inner.VerifyOwnerMandate(ctx, v)
	if !s.allow(ctx) {
		return errHeld
	}
	return e
}
func (s *guardedSource) VerifyWatcherMarket(ctx context.Context, v satchelservice.WagerReservation) error {
	if !s.allow(ctx) {
		return errHeld
	}
	e := s.inner.VerifyWatcherMarket(ctx, v)
	if !s.allow(ctx) {
		return errHeld
	}
	return e
}
func (s *guardedSource) AuthenticatedFeeCensus(ctx context.Context, v satchelservice.WagerReservation) (satchelservice.ReviewerFeeCensus, error) {
	if !s.allow(ctx) {
		return satchelservice.ReviewerFeeCensus{}, errHeld
	}
	result, e := s.inner.AuthenticatedFeeCensus(ctx, v)
	if !s.allow(ctx) {
		return satchelservice.ReviewerFeeCensus{}, errHeld
	}
	return result, e
}

// Hold a response until protected inputs/permit are rechecked. This does not
// claim atomic filesystem revocation with the issuer's internal signing call;
// it prevents disclosure when revocation is observed at the response boundary.
type bufferedResponse struct {
	header   http.Header
	body     bytes.Buffer
	status   int
	overflow bool
}

func (b *bufferedResponse) Header() http.Header { return b.header }
func (b *bufferedResponse) WriteHeader(status int) {
	if b.status == 0 {
		b.status = status
	}
}
func (b *bufferedResponse) Write(raw []byte) (int, error) {
	if b.status == 0 {
		b.status = http.StatusOK
	}
	if b.overflow || b.body.Len()+len(raw) > 32<<10 {
		b.overflow = true
		return 0, errHeld
	}
	return b.body.Write(raw)
}
func guardHTTP(next http.Handler, allow func(context.Context) bool) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		held := func() {
			w.Header().Set("Cache-Control", "no-store")
			http.Error(w, "reviewer_startup_held", http.StatusServiceUnavailable)
		}
		if !allow(r.Context()) {
			held()
			return
		}
		buffer := &bufferedResponse{header: make(http.Header)}
		next.ServeHTTP(buffer, r)
		if buffer.overflow || !allow(r.Context()) {
			held()
			return
		}
		for key, values := range buffer.header {
			w.Header()[key] = append([]string{}, values...)
		}
		if buffer.status == 0 {
			buffer.status = http.StatusOK
		}
		w.WriteHeader(buffer.status)
		_, _ = w.Write(buffer.body.Bytes())
	})
}

type composedReviewer struct {
	server *http.Server
	close  func()
}

func compose(ctx context.Context, c config, gate *inputGate) (*composedReviewer, error) {
	if os.Geteuid() == 0 || !gate.allowed(ctx) {
		return nil, errHeld
	}
	inputs, e := pinnedBytes(c)
	if e != nil {
		return nil, errHeld
	}
	defer func() {
		for _, raw := range inputs {
			wipe(raw)
		}
	}()
	// Distinct transport principals cannot silently collapse to a bearer that
	// authenticates both an app caller and the independent evidence readers.
	httpToken, e := pinnedToken(c.HTTPToken, inputs)
	if e != nil {
		return nil, errHeld
	}
	watcherToken, e := pinnedToken(c.Watcher.Token, inputs)
	if e != nil {
		return nil, errHeld
	}
	custodyToken, e := pinnedToken(c.CustodyToken, inputs)
	if e != nil || httpToken == watcherToken || httpToken == custodyToken || watcherToken == custodyToken {
		return nil, errHeld
	}
	bank, e := satchel.NewTrustedReader(satchel.SourceConfig{RPC: c.RPC, REST: c.REST, WitnessRPC: c.WitnessRPC}, c.TrustAnchor)
	if e != nil {
		return nil, errHeld
	}
	var db *sql.DB
	var custody *satchelservice.ReviewerCustodyFeeClient
	var issuer *satchelservice.ReviewerIssuer
	cleanup := func() {
		if issuer != nil {
			_ = issuer.Close()
		}
		if custody != nil {
			custody.Close()
		}
		if db != nil {
			_ = db.Close()
		}
		bank.Close()
	}
	success := false
	defer func() {
		if !success {
			cleanup()
		}
	}()
	if bank.CheckTrust(ctx) != nil {
		return nil, errHeld
	}
	db, e = openPG(ctx, c.Postgres, inputs)
	if e != nil {
		return nil, errHeld
	}
	pg, e := satchelservice.NewReviewerReadOnlyPGSource(db, c.Postgres.Role, c.FeeUWolo, c.Vault, c.BettingEscrow)
	if e != nil {
		return nil, errHeld
	}
	roots, e := certificatePool(inputs[c.Watcher.CA.Path])
	if e != nil {
		return nil, errHeld
	}
	api, e := satchelservice.NewReviewerOriginalLiveAPIClient(c.Watcher.Origin, watcherToken, c.Watcher.ServerSPKISHA256, roots)
	if e != nil {
		return nil, errHeld
	}
	original, e := satchelservice.NewReviewerOriginalLiveSource(pg, api)
	if e != nil {
		return nil, errHeld
	}
	witness, e := satchelservice.NewReviewerSignedLiveReader(api)
	if e != nil {
		return nil, errHeld
	}
	watcherKey, _ := publicKey(c.Watcher.WitnessPublicKeyHex)
	watcher, e := satchelservice.NewReviewerIndependentWatcherSource(pg, witness, original, watcherKey)
	if e != nil {
		return nil, errHeld
	}
	finance, e := satchelservice.NewReviewerFinanceSource(watcher, pg, bank)
	if e != nil {
		return nil, errHeld
	}
	custody, e = satchelservice.NewReviewerCustodyFeeClient(custodyToken)
	if e != nil {
		return nil, errHeld
	}
	coverage, e := satchelservice.NewReviewerReserveFile(c.ReserveCoveragePath)
	if e != nil {
		return nil, errHeld
	}
	accountingKey, _ := publicKey(c.Roles.AccountingPublicKeyHex)
	custodyKey, _ := publicKey(c.Roles.CustodyPublicKeyHex)
	executionKey, _ := publicKey(c.Roles.ExecutionPublicKeyHex)
	wagerKey, _ := publicKey(c.Roles.WagerPublicKeyHex)
	withdrawalKey, _ := publicKey(c.Roles.WithdrawalPublicKeyHex)
	census, e := satchelservice.NewReviewerReserveCensusSource(finance, custody, coverage, satchelservice.ReviewerReserveCensusConfig{
		Authority:           satchelservice.ReserveReviewAuthority{AccountingReviewerKey: accountingKey, CustodyReviewerKey: custodyKey, ExecutionAuthorityKey: executionKey, WagerApprovalKey: wagerKey, WithdrawalApprovalKey: withdrawalKey, ExpectedVault: c.Vault, ExpectedBuildSHA256: c.Custody.BuildSHA256, ExpectedConfigSHA256: c.Custody.ConfigSHA256, ExpectedPermitSHA256: c.Custody.PermitSHA256},
		FeeSources:          satchelservice.ReviewerFeeMergeAuthority{Vault: c.Vault, CustodyPolicyDigest: c.Custody.PolicySHA256, IssuerPolicyDigest: c.IssuerPolicySHA256, WagerApprovalKey: wagerKey},
		RequiredProducerIDs: c.RequiredProducerIDs, FeeUWolo: c.FeeUWolo, MinimumGasReserveUWolo: c.MinimumGasReserveUWolo, MinimumUnencumberedUWolo: c.MinimumUnencumberedUWolo,
	})
	if e != nil {
		return nil, errHeld
	}
	key := inputs[c.ReviewerPrivateKey.Path]
	if len(key) != ed25519.PrivateKeySize {
		return nil, errHeld
	}
	canonicalKey := ed25519.NewKeyFromSeed(key[:ed25519.SeedSize])
	canonical := bytes.Equal(canonicalKey, key)
	wipe(canonicalKey)
	if !canonical || !bytes.Equal(key[ed25519.SeedSize:], wagerKey) {
		return nil, errHeld
	}
	policy, e := c.policy()
	if e != nil {
		return nil, errHeld
	}
	if !gate.allowed(ctx) {
		return nil, errHeld
	}
	issuer, e = satchelservice.OpenReviewerIssuer(c.JournalPath, &guardedSource{inner: census, allow: gate.allowed}, ed25519.PrivateKey(key), policy)
	if e != nil {
		return nil, errHeld
	}
	if issuer.RequireIssuanceAuthorization(gate.allowed) != nil {
		return nil, errHeld
	}
	handler, e := satchelservice.NewReviewerHTTPHandler(issuer, httpToken)
	if e != nil {
		return nil, errHeld
	}
	server, e := satchelservice.NewReviewerHTTPServer(guardHTTP(handler, gate.allowed))
	if e != nil || !gate.allowed(ctx) {
		return nil, errHeld
	}
	success = true
	return &composedReviewer{server: server, close: cleanup}, nil
}

var _ satchelservice.ReviewerEvidenceSource = (*guardedSource)(nil)
