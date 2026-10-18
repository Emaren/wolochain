package satchelservice

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
)

const testHTTPToken = "synthetic_private_service_token_0000000000000000000000000000000000"
const testHTTPHash = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

type httpTestBackend struct {
	mu              sync.Mutex
	request         TransferRequest
	result          Result
	err             error
	submit          func(context.Context, TransferRequest) (Result, error)
	submissions     atomic.Int32
	reconciliations atomic.Int32
	lookups         atomic.Int32
}

func (b *httpTestBackend) Submit(ctx context.Context, input TransferRequest) (Result, error) {
	b.submissions.Add(1)
	b.mu.Lock()
	b.request = input
	b.mu.Unlock()
	if b.submit != nil {
		return b.submit(ctx, input)
	}
	if b.result.OperationID == "" {
		return Result{OperationID: input.OperationID, Status: "ACCEPTED", TxHash: testHTTPHash, DurableFenced: true}, b.err
	}
	return b.result, b.err
}
func (b *httpTestBackend) Reconcile(_ context.Context, id string) (Result, error) {
	b.reconciliations.Add(1)
	if b.result.OperationID == "" {
		return Result{OperationID: id, Status: "OBSERVED_NONCREDITING", TxHash: testHTTPHash, DurableFenced: true}, b.err
	}
	return b.result, b.err
}
func (b *httpTestBackend) Lookup(id string) (Result, error) {
	b.lookups.Add(1)
	if b.result.OperationID == "" {
		return Result{OperationID: id, Status: "ACCEPTED", TxHash: testHTTPHash, DurableFenced: true}, b.err
	}
	return b.result, b.err
}

func testHTTPAddress(t *testing.T, seed byte) string {
	t.Helper()
	address, err := bech32.EncodeFromBase256("wolo", bytes.Repeat([]byte{seed}, 20))
	if err != nil {
		t.Fatal(err)
	}
	return address
}
func testHTTPConfig(t *testing.T) HTTPConfig {
	return HTTPConfig{Token: testHTTPToken, Accepting: true, Authorize: func(context.Context) bool { return true }, Health: HTTPHealth{Accepting: true, VaultAddress: testHTTPAddress(t, 100),
		KeyFingerprint: strings.Repeat("1", 64), BuildSHA256: strings.Repeat("2", 64), ExclusiveAuthorityVerified: true}}
}
func testHTTPHandler(t *testing.T, backend HTTPBackend, cfg HTTPConfig) http.Handler {
	t.Helper()
	handler, err := NewHTTPHandler(backend, cfg)
	if err != nil {
		t.Fatal(err)
	}
	return handler
}
func testHTTPPayload(t *testing.T, snake bool) string {
	t.Helper()
	var value any
	if snake {
		value = map[string]any{"request_id": "satchel:ticket:1", "chain_id": "wolo-1", "signer_role": httpCustodyRole,
			"from_address": testHTTPAddress(t, 100), "to_address": testHTTPAddress(t, 101), "amount": map[string]any{"denom": "uwolo", "amount": "1000000"}, "memo": "AoE2HDBets bet ticket v1 · ticket 123"}
	} else {
		value = map[string]any{"protocol": 1, "requestId": "satchel:ticket:1", "chainId": "wolo-1",
			"senderAddress": testHTTPAddress(t, 100), "recipientAddress": testHTTPAddress(t, 101), "denom": "uwolo", "amountUwolo": "1000000", "memo": "AoE2HDBets bet ticket v1 · ticket 123"}
	}
	b, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}
func testHTTPRequest(method, path, body string) *http.Request {
	r := httptest.NewRequest(method, "http://127.0.0.1:8094"+path, strings.NewReader(body))
	r.RemoteAddr = "127.0.0.1:12345"
	r.Header.Set("Authorization", "Bearer "+testHTTPToken)
	r.Header.Set("Content-Type", "application/json")
	return r
}
func testHTTPRead(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func TestPrivateHTTPConstructorAndListenerLimits(t *testing.T) {
	backend := &httpTestBackend{}
	for _, test := range []struct {
		name   string
		mutate func(*HTTPConfig)
	}{
		{"missing token", func(c *HTTPConfig) { c.Token = "" }},
		{"short token", func(c *HTTPConfig) { c.Token = "short" }},
		{"token whitespace", func(c *HTTPConfig) { c.Token += "\n" }},
		{"excessive timeout", func(c *HTTPConfig) { c.RequestTimeout = 9 * time.Second }},
		{"negative timeout", func(c *HTTPConfig) { c.RequestTimeout = -time.Second }},
		{"excessive concurrency", func(c *HTTPConfig) { c.MaxConcurrent = 17 }},
		{"missing independent authority", func(c *HTTPConfig) { c.Health.ExclusiveAuthorityVerified = false }},
		{"missing permit verifier", func(c *HTTPConfig) { c.Authorize = nil }},
		{"invalid vault checksum", func(c *HTTPConfig) { c.Health.VaultAddress = "wolo1" }},
		{"protected vault role", func(c *HTTPConfig) { c.Health.VaultAddress = "wolo1r8kvt7me33rsv9ldaczj03xjrld4yumx0c0jkg" }},
		{"missing build identity", func(c *HTTPConfig) { c.Health.BuildSHA256 = "" }},
		{"missing key fingerprint", func(c *HTTPConfig) { c.Health.KeyFingerprint = "" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			cfg := testHTTPConfig(t)
			test.mutate(&cfg)
			if _, err := NewHTTPHandler(backend, cfg); err == nil {
				t.Fatal("invalid private service configuration accepted")
			}
		})
	}
	if _, err := NewHTTPHandler(nil, testHTTPConfig(t)); err == nil {
		t.Fatal("nil engine accepted")
	}
	handler := testHTTPHandler(t, backend, testHTTPConfig(t))
	for _, address := range []string{"0.0.0.0:8094", ":8094", "localhost:8094", "192.0.2.1:8094", "127.0.0.1:-1", "127.0.0.1:65536", "127.0.0.1:not-a-port"} {
		t.Run(address, func(t *testing.T) {
			if _, err := NewPrivateHTTPServer(address, handler); err == nil {
				t.Fatal("non-private listener accepted")
			}
		})
	}
	for _, address := range []string{"127.0.0.1:8094", "[::1]:8094"} {
		server, err := NewPrivateHTTPServer(address, handler)
		if err != nil || server.ReadHeaderTimeout != 2*time.Second || server.ReadTimeout != 3*time.Second || server.WriteTimeout != 9*time.Second || server.IdleTimeout != 15*time.Second || server.MaxHeaderBytes != 8192 {
			t.Fatalf("missing transport bounds: server=%+v err=%v", server, err)
		}
	}
}

func TestPrivateHTTPPermitExpiresWithoutPreventingReadOnlyRecovery(t *testing.T) {
	backend := &httpTestBackend{}
	cfg := testHTTPConfig(t)
	var active atomic.Bool
	active.Store(true)
	var checks atomic.Int32
	cfg.Authorize = func(context.Context) bool { checks.Add(1); return active.Load() }
	handler := testHTTPHandler(t, backend, cfg)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/health", ""))
	if testHTTPRead(t, w)["accepting"] != true {
		t.Fatal("verified activation was not available")
	}
	active.Store(false)
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/health", ""))
	if testHTTPRead(t, w)["accepting"] != false {
		t.Fatal("expired activation remained ready")
	}
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
	if w.Code != 503 || backend.submissions.Load() != 0 {
		t.Fatal("expired activation submitted a transfer")
	}
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/reconcile", `{"operation_id":"satchel:ticket:1"}`))
	if w.Code != 200 || backend.reconciliations.Load() != 1 || checks.Load() != 4 {
		t.Fatalf("expired permit prevented recovery or was not checked: status=%d checks=%d", w.Code, checks.Load())
	}
	cfg.Accepting = false
	handler = testHTTPHandler(t, backend, cfg)
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/health", ""))
	if testHTTPRead(t, w)["accepting"] != false {
		t.Fatal("zero activation policy was overridden by identity flags")
	}
}

func TestPrivateHTTPRevocationDuringRequestCannotReachSubmit(t *testing.T) {
	backend := &httpTestBackend{}
	cfg := testHTTPConfig(t)
	var checks atomic.Int32
	cfg.Authorize = func(context.Context) bool { return checks.Add(1) == 1 }
	handler := testHTTPHandler(t, backend, cfg)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
	if w.Code != 503 || backend.submissions.Load() != 0 || checks.Load() != 2 {
		t.Fatalf("expired activation crossed request-validation interval: status=%d calls=%d checks=%d", w.Code, backend.submissions.Load(), checks.Load())
	}
}

type unreadHTTPBody struct{ t *testing.T }

func (r unreadHTTPBody) Read([]byte) (int, error) {
	r.t.Error("unauthorized body was read")
	return 0, io.EOF
}
func (unreadHTTPBody) Close() error { return nil }

func TestPrivateHTTPRejectsUnauthorizedBeforeReadingOrCallingEngine(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*http.Request)
	}{
		{"missing token", func(r *http.Request) { r.Header.Del("Authorization") }},
		{"incorrect token", func(r *http.Request) { r.Header.Set("Authorization", "Bearer "+strings.Repeat("x", 64)) }},
		{"wrong auth scheme", func(r *http.Request) { r.Header.Set("Authorization", "Basic "+testHTTPToken) }},
		{"duplicate credentials", func(r *http.Request) { r.Header.Add("Authorization", "Bearer "+testHTTPToken) }},
		{"trailing credential whitespace", func(r *http.Request) { r.Header.Set("Authorization", "Bearer "+testHTTPToken+" ") }},
		{"remote peer", func(r *http.Request) { r.RemoteAddr = "192.0.2.1:321" }},
		{"hostname peer", func(r *http.Request) { r.RemoteAddr = "localhost:321" }},
		{"proxy headers confer no authority", func(r *http.Request) {
			r.RemoteAddr = "192.0.2.1:321"
			r.Header.Set("X-Forwarded-For", "127.0.0.1")
			r.Header.Set("Forwarded", "for=127.0.0.1")
		}},
		{"browser origin", func(r *http.Request) { r.Header.Set("Origin", "https://aoe2war.com") }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &httpTestBackend{}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			r := testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", "")
			r.Body = unreadHTTPBody{t}
			test.mutate(r)
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, r)
			if w.Code != http.StatusUnauthorized || backend.submissions.Load() != 0 {
				t.Fatalf("unauthorized request reached signing engine: status=%d calls=%d", w.Code, backend.submissions.Load())
			}
			if strings.Contains(w.Body.String(), testHTTPToken) {
				t.Fatal("credential exposed")
			}
		})
	}
}

func TestPrivateHTTPStrictBoundedTransferRequests(t *testing.T) {
	for _, test := range []struct {
		name   string
		body   string
		status int
		mutate func(*http.Request)
	}{
		{name: "empty body", body: "", status: 400},
		{name: "null body", body: "null", status: 400},
		{name: "array body", body: "[]", status: 400},
		{name: "trailing JSON", body: `{} {}`, status: 400},
		{name: "duplicate request key", body: `{"request_id":"one","request_id":"two"}`, status: 400},
		{name: "escaped duplicate key", body: `{"request_id":"one","request_\u0069d":"two"}`, status: 400},
		{name: "unknown field", body: `{"protocol":1,"surprise":"private_key"}`, status: 400},
		{name: "case alias", body: `{"protocol":1,"RequestId":"satchel:ticket:1"}`, status: 400},
		{name: "mixed wire forms", body: `{"protocol":1,"request_id":"satchel:ticket:1"}`, status: 400},
		{name: "nested duplicate", body: `{"amount":{"denom":"uwolo","denom":"uother"}}`, status: 400},
		{name: "null transfer amount", body: `{"request_id":"satchel:ticket:1","signer_role":"exclusive-war-satchel-v1","amount":null}`, status: 400},
		{name: "wrong protocol", body: `{"protocol":2}`, status: 400},
		{name: "wrong chain", status: 400, mutate: func(r *http.Request) {
			r.Body = io.NopCloser(strings.NewReader(strings.Replace(testHTTPPayload(t, false), "wolo-1", "wolo-2", 1)))
		}},
		{name: "wrong denomination", status: 400, mutate: func(r *http.Request) {
			r.Body = io.NopCloser(strings.NewReader(strings.Replace(testHTTPPayload(t, false), "uwolo", "ustake", 1)))
		}},
		{name: "wrong signer role", status: 400, mutate: func(r *http.Request) {
			r.Body = io.NopCloser(strings.NewReader(strings.Replace(testHTTPPayload(t, true), httpCustodyRole, "payout", 1)))
		}},
		{name: "invalid UTF8", body: string([]byte{'{', '"', 'a', '"', ':', '"', 0xff, '"', '}'}), status: 400},
		{name: "excessive nesting", body: `{"x":` + strings.Repeat("[", 40) + `0` + strings.Repeat("]", 40) + `}`, status: 400},
		{name: "body over limit", body: strings.Repeat("x", HTTPMaxBodyBytes+1), status: 413},
		{name: "chunked body over limit", body: strings.Repeat("x", HTTPMaxBodyBytes+1), status: 413, mutate: func(r *http.Request) { r.ContentLength = -1 }},
		{name: "wrong media type", status: 415, mutate: func(r *http.Request) { r.Header.Set("Content-Type", "text/plain") }},
		{name: "compressed body", status: 415, mutate: func(r *http.Request) { r.Header.Set("Content-Encoding", "gzip") }},
		{name: "wrong charset", status: 415, mutate: func(r *http.Request) { r.Header.Set("Content-Type", "application/json; charset=iso-8859-1") }},
		{name: "query is not authority", status: 400, mutate: func(r *http.Request) { r.URL.RawQuery = "token=secret" }},
		{name: "encoded route", status: 400, mutate: func(r *http.Request) { r.URL.RawPath = "/satchel/v1/%6fne-shot" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &httpTestBackend{}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			r := testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", test.body)
			if test.mutate != nil {
				test.mutate(r)
			}
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, r)
			if w.Code != test.status || backend.submissions.Load() != 0 {
				t.Fatalf("malformed request reached engine: status=%d wanted=%d calls=%d response=%s", w.Code, test.status, backend.submissions.Load(), w.Body.String())
			}
		})
	}
}

func TestPrivateHTTPBothPinnedHDClientsAndHealth(t *testing.T) {
	for _, snake := range []bool{false, true} {
		t.Run(map[bool]string{false: "camel transport", true: "snake dedicated client"}[snake], func(t *testing.T) {
			backend := &httpTestBackend{}
			cfg := testHTTPConfig(t)
			handler := testHTTPHandler(t, backend, cfg)
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/health", ""))
			health := testHTTPRead(t, w)
			if w.Code != 200 || health["ok"] != true || health["accepting"] != true || health["chainId"] != "wolo-1" || health["chain_id"] != "wolo-1" || health["custodyRole"] != httpCustodyRole || health["signer_role"] != httpCustodyRole || health["vaultAddress"] != cfg.Health.VaultAddress || health["vault_address"] != cfg.Health.VaultAddress || health["keyFingerprint"] != cfg.Health.KeyFingerprint || health["build_sha256"] != cfg.Health.BuildSHA256 || health["durable_one_shot"] != true || health["custody_mnemonic_shared_with_other_roles"] != false {
				t.Fatalf("health violates pinned client contracts: %v", health)
			}
			w = httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, snake)))
			receipt := testHTTPRead(t, w)
			if w.Code != 200 || receipt["kind"] != "broadcast_confirmed" || receipt["txHash"] != testHTTPHash || receipt["broadcast_status"] != "accepted_once" || receipt["durable_request_fenced"] != true || receipt["request_id"] != "satchel:ticket:1" || receipt["status"] != "ACCEPTED" {
				t.Fatalf("accepted broadcast receipt violates pinned client contracts: %v", receipt)
			}
			if backend.request.OperationID != "satchel:ticket:1" || backend.request.Kind != "wager" || backend.request.Sender != cfg.Health.VaultAddress || backend.request.AmountUWolo != "1000000" || backend.request.Approval != nil {
				t.Fatalf("wire changed economic payload: %+v", backend.request)
			}
			if w.Header().Get("Cache-Control") != "no-store" || w.Header().Get("X-Content-Type-Options") != "nosniff" {
				t.Fatal("sensitive response caching enabled")
			}
		})
	}
}

func TestPrivateHTTPUnknownAndNoncreditingNeverBecomeAccepted(t *testing.T) {
	for _, test := range []struct {
		name, status, hash string
		fenced             bool
	}{
		{"unknown despite known signed hash", "UNKNOWN", testHTTPHash, true},
		{"observed is not authority", "OBSERVED_NONCREDITING", testHTTPHash, true},
		{"failed execution", "FAILED", testHTTPHash, true},
		{"accepted without fence", "ACCEPTED", testHTTPHash, false},
		{"accepted without hash", "ACCEPTED", "", true},
		{"accepted with malformed hash", "ACCEPTED", "not-a-hash", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &httpTestBackend{result: Result{OperationID: "satchel:ticket:1", Status: test.status, TxHash: test.hash, DurableFenced: test.fenced}}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
			response := testHTTPRead(t, w)
			if response["kind"] != "unknown" || response["broadcast_status"] == "accepted_once" || response["txHash"] != nil {
				t.Fatalf("uncertain execution promoted to accepted broadcast: %v", response)
			}
		})
	}
}

func TestPrivateHTTPReconciliationAndLookupAreReadOnly(t *testing.T) {
	backend := &httpTestBackend{}
	handler := testHTTPHandler(t, backend, testHTTPConfig(t))
	for _, r := range []*http.Request{testHTTPRequest(http.MethodPost, "/satchel/v1/reconcile", `{"operation_id":"satchel:ticket:1"}`), testHTTPRequest(http.MethodGet, "/satchel/v1/operations/satchel:ticket:1", "")} {
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		result := testHTTPRead(t, w)
		if w.Code != 200 || result["kind"] != "unknown" || result["broadcast_status"] != nil {
			t.Fatalf("inspection created HD execution acknowledgement: %v", result)
		}
	}
	if backend.submissions.Load() != 0 || backend.reconciliations.Load() != 1 || backend.lookups.Load() != 1 {
		t.Fatal("read-only routes invoked transfer execution")
	}
}

func TestPrivateHTTPTimeoutCancellationAndConcurrencyBound(t *testing.T) {
	t.Run("request deadline", func(t *testing.T) {
		backend := &httpTestBackend{submit: func(ctx context.Context, input TransferRequest) (Result, error) {
			<-ctx.Done()
			return Result{}, ctx.Err()
		}}
		cfg := testHTTPConfig(t)
		cfg.RequestTimeout = 10 * time.Millisecond
		handler := testHTTPHandler(t, backend, cfg)
		w := httptest.NewRecorder()
		start := time.Now()
		handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
		if time.Since(start) > time.Second || backend.submissions.Load() != 1 || testHTTPRead(t, w)["kind"] != "unknown" {
			t.Fatal("request timeout retried or acknowledged execution")
		}
	})
	t.Run("already canceled before submission", func(t *testing.T) {
		backend := &httpTestBackend{}
		handler := testHTTPHandler(t, backend, testHTTPConfig(t))
		r := testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false))
		ctx, cancel := context.WithCancel(r.Context())
		cancel()
		r = r.WithContext(ctx)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != 408 || backend.submissions.Load() != 0 {
			t.Fatal("canceled request signed")
		}
	})
	t.Run("bounded active requests", func(t *testing.T) {
		entered, release, finished := make(chan struct{}), make(chan struct{}), make(chan struct{})
		backend := &httpTestBackend{submit: func(_ context.Context, input TransferRequest) (Result, error) {
			close(entered)
			<-release
			return Result{OperationID: input.OperationID, Status: "UNKNOWN", DurableFenced: true}, nil
		}}
		cfg := testHTTPConfig(t)
		cfg.MaxConcurrent = 1
		handler := testHTTPHandler(t, backend, cfg)
		go func() {
			defer close(finished)
			handler.ServeHTTP(httptest.NewRecorder(), testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
		}()
		<-entered
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
		close(release)
		<-finished
		if w.Code != 503 || backend.submissions.Load() != 1 {
			t.Fatal("concurrency bound allowed a second execution")
		}
	})
}

func TestPrivateHTTPUnavailableAuthorityAndErrorsDoNotExposeSecrets(t *testing.T) {
	t.Run("unavailable authority", func(t *testing.T) {
		cfg := testHTTPConfig(t)
		cfg.Health = HTTPHealth{}
		backend := &httpTestBackend{}
		handler := testHTTPHandler(t, backend, cfg)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/health", ""))
		health := testHTTPRead(t, w)
		if health["ok"] != false || health["accepting"] != false || health["custody_mnemonic_shared_with_other_roles"] != nil {
			t.Fatal("unavailable custody authority was certified")
		}
		w = httptest.NewRecorder()
		handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
		if w.Code != 503 || backend.submissions.Load() != 0 {
			t.Fatal("unavailable authority reached signer")
		}
	})
	for _, test := range []struct {
		name   string
		result Result
		err    error
	}{
		{"backend error", Result{}, errors.New("/secret/keyring mnemonic " + testHTTPToken)},
		{"backend reason", Result{OperationID: "satchel:ticket:1", Status: "UNKNOWN", Reason: "/secret/keyring mnemonic " + testHTTPToken}, nil},
		{"backend status", Result{OperationID: "satchel:ticket:1", Status: "/secret/keyring mnemonic " + testHTTPToken}, nil},
		{"wrong operation identity", Result{OperationID: "satchel:ticket:2", Status: "ACCEPTED", TxHash: testHTTPHash, DurableFenced: true}, nil},
	} {
		t.Run(test.name, func(t *testing.T) {
			backend := &httpTestBackend{result: test.result, err: test.err}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/one-shot", testHTTPPayload(t, false)))
			if strings.Contains(w.Body.String(), "secret") || strings.Contains(w.Body.String(), "mnemonic") || strings.Contains(w.Body.String(), testHTTPToken) || testHTTPRead(t, w)["kind"] != "unknown" {
				t.Fatalf("private engine detail exposed: %s", w.Body.String())
			}
		})
	}
}

func TestPrivateHTTPWithdrawalRequiresExplicitIndependentApprovalContract(t *testing.T) {
	approval := WithdrawalApproval{WithdrawalID: "12345678-1234-4123-8123-123456789abc", ChallengeID: "12345678-1234-4123-8123-123456789abd", OwnerID: "owner-1",
		Recipient: testHTTPAddress(t, 102), AmountUWolo: "1000000", Memo: "aoe2war/satchel/withdraw/v1/12345678-1234-4123-8123-123456789abc", HoldDigest: strings.Repeat("3", 64), IssuedAt: 100, ExpiresAt: 200, Signature: "synthetic"}
	payload := httpWithdrawal{Protocol: 1, OperationID: "satchel:withdrawal:" + approval.WithdrawalID, ChainID: "wolo-1", Sender: testHTTPAddress(t, 100), Recipient: approval.Recipient,
		Amount: httpCoin{Denom: "uwolo", Amount: approval.AmountUWolo}, Memo: approval.Memo, OwnerID: approval.OwnerID, Approval: &approval, OwnerMandate: engineTestWithdrawal(t).OwnerMandate}
	for _, test := range []struct {
		name   string
		mutate func(*httpWithdrawal)
		valid  bool
	}{
		{"full approval forwarded to verifier", func(*httpWithdrawal) {}, true},
		{"missing independently signed approval", func(v *httpWithdrawal) { v.Approval = nil }, false},
		{"missing independent owner mandate", func(v *httpWithdrawal) { v.OwnerMandate = nil }, false},
		{"missing owner", func(v *httpWithdrawal) { v.OwnerID = "" }, false},
		{"wrong protocol", func(v *httpWithdrawal) { v.Protocol = 2 }, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			input := payload
			test.mutate(&input)
			raw, err := json.Marshal(input)
			if err != nil {
				t.Fatal(err)
			}
			backend := &httpTestBackend{}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/v1/satchel/withdrawals", string(raw)))
			if test.valid {
				if w.Code != 200 || backend.submissions.Load() != 1 || backend.request.Kind != "withdrawal" || backend.request.OwnerID != "owner-1" || backend.request.Approval == nil || backend.request.Approval.ChallengeID != approval.ChallengeID {
					t.Fatalf("independent approval was dropped: request=%+v status=%d", backend.request, w.Code)
				}
			} else if w.Code != 400 || backend.submissions.Load() != 0 {
				t.Fatal("incomplete withdrawal contract reached signer")
			}
		})
	}
}

type httpTestReturnBackend struct {
	*httpTestBackend
	prepareCalls, reconcileCalls atomic.Int32
	vault                        string
	run                          *ReturnRun
	receipt                      *ReturnReceipt
	err                          error
}

func (b *httpTestReturnBackend) PrepareReturnRun(_ context.Context, a ReturnApproval) (ReturnRun, error) {
	b.prepareCalls.Add(1)
	if b.run != nil {
		return *b.run, b.err
	}
	id := "satchel:claim-return:" + a.ClaimID
	return ReturnRun{SettlementRunID: id, SourceApp: "aoe2hdbets", SourceEventID: a.OperationID, SignerRole: "escrow", Payouts: []ReturnPayout{{RequestID: id, ToAddress: b.vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + a.ClaimID}}}, b.err
}
func (b *httpTestReturnBackend) ReconcileClaimReturn(_ context.Context, a ReturnApproval, hash string) (ReturnReceipt, error) {
	b.reconcileCalls.Add(1)
	if b.receipt != nil {
		return *b.receipt, b.err
	}
	return ReturnReceipt{Version: 2, TicketID: a.TicketID, MarketID: a.MarketID, LegID: a.LegID, EntitlementID: a.EntitlementID, AllocationID: a.Allocation.AllocationID, OperationID: a.OperationID, ClaimID: a.ClaimID, OwnerID: a.OwnerID, ClaimKind: a.ClaimKind, AmountUWolo: a.AmountUWolo, TxHash: hash, ReceiptID: "wolo-1:" + hash + ":0", Height: 123, BlockHash: strings.Repeat("B", 64)}, b.err
}

func TestPrivateHTTPReturnPreparationIsNotExecutionOrCredit(t *testing.T) {
	a := testReturnApproval(t, "satchel:ticket:1", "1")
	data, _ := json.Marshal(a)
	backend := &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, vault: testHTTPAddress(t, 100)}
	handler := testHTTPHandler(t, backend, testHTTPConfig(t))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/prepare", string(data)))
	response := testHTTPRead(t, w)
	if w.Code != 200 || response["kind"] != "escrow_run_prepared" || response["execution_authorized"] != false || response["credit_authorized"] != false || backend.prepareCalls.Load() != 1 || backend.submissions.Load() != 0 {
		t.Fatalf("run preparation executed or credited custody: response=%v calls=%d", response, backend.submissions.Load())
	}
	run := response["run"].(map[string]any)
	payouts := run["payouts"].([]any)
	if run["signer_role"] != "escrow" || len(payouts) != 1 || payouts[0].(map[string]any)["amount_uwolo"] != "1000000" {
		t.Fatalf("full refund lost exact escrow wire identity: %v", run)
	}
}

func TestPrivateHTTPExpiredPermitAllowsOnlyReturnReconciliation(t *testing.T) {
	a := testReturnApproval(t, "satchel:ticket:1", "1")
	backend := &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, vault: testHTTPAddress(t, 100)}
	cfg := testHTTPConfig(t)
	cfg.Authorize = func(context.Context) bool { return false }
	handler := testHTTPHandler(t, backend, cfg)
	data, _ := json.Marshal(a)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/prepare", string(data)))
	if w.Code != 503 || backend.prepareCalls.Load() != 0 {
		t.Fatal("expired activation prepared a fresh escrow obligation")
	}
	data, _ = json.Marshal(map[string]any{"approval": a, "tx_hash": strings.ToLower(testHTTPHash)})
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/reconcile", string(data)))
	response := testHTTPRead(t, w)
	if w.Code != 200 || response["tx_hash"] != testHTTPHash || response["credit_authorized"] != false || backend.reconcileCalls.Load() != 1 || backend.submissions.Load() != 0 {
		t.Fatalf("read-only return recovery unavailable or credited: %v", response)
	}
}

func TestPrivateHTTPMalformedOrForgedReturnEvidenceIsUnavailable(t *testing.T) {
	a := testReturnApproval(t, "satchel:ticket:1", "1")
	for _, test := range []struct {
		name, path, body string
		backend          *httpTestReturnBackend
		status           int
	}{
		{name: "missing adapter", path: "/satchel/v1/returns/prepare", body: `{}`, status: 503},
		{name: "missing approval", path: "/satchel/v1/returns/reconcile", body: `{"tx_hash":"` + testHTTPHash + `"}`, backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}}, status: 400},
		{name: "mixed approval aliases", path: "/satchel/v1/returns/prepare", body: `{"OperationID":"satchel:ticket:1"}`, backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}}, status: 400},
		{name: "backend errors redacted", path: "/satchel/v1/returns/prepare", backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, err: errors.New("secret escrow token")}, status: 409},
		{name: "wrong escrow run role", path: "/satchel/v1/returns/prepare", backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, run: &ReturnRun{SignerRole: "payout"}}, status: 503},
		{name: "invented ledger credit", path: "/satchel/v1/returns/reconcile", backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, receipt: &ReturnReceipt{CreditAuthorized: true}}, status: 503},
		{name: "wrong owner receipt", path: "/satchel/v1/returns/reconcile", backend: &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, receipt: &ReturnReceipt{OwnerID: "another-owner"}}, status: 503},
	} {
		t.Run(test.name, func(t *testing.T) {
			body := test.body
			if body == "" {
				var raw []byte
				if strings.HasSuffix(test.path, "reconcile") {
					raw, _ = json.Marshal(map[string]any{"approval": a, "tx_hash": testHTTPHash})
				} else {
					raw, _ = json.Marshal(a)
				}
				body = string(raw)
			}
			var backend HTTPBackend = &httpTestBackend{}
			if test.backend != nil {
				backend = test.backend
			}
			handler := testHTTPHandler(t, backend, testHTTPConfig(t))
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, testHTTPRequest(http.MethodPost, test.path, body))
			if w.Code != test.status || strings.Contains(w.Body.String(), "secret") {
				t.Fatalf("forged return evidence accepted: status=%d body=%s", w.Code, w.Body.String())
			}
		})
	}
}
