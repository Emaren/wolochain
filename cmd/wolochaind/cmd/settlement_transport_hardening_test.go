package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
)

func transportTestAddress(t *testing.T, hrp string, size int) string {
	t.Helper()
	address, err := bech32.EncodeFromBase256(hrp, bytes.Repeat([]byte{23}, size))
	if err != nil {
		t.Fatal(err)
	}
	return address
}

func TestSettlementAddressRequiresCompleteBech32(t *testing.T) {
	t.Parallel()
	valid := transportTestAddress(t, "wolo", 20)
	badChecksum := valid[:len(valid)-1] + "q"
	if badChecksum == valid {
		badChecksum = valid[:len(valid)-1] + "p"
	}
	cases := []struct {
		name    string
		address string
		valid   bool
	}{
		{"account", valid, true},
		{"trimmed account", " \t" + valid + "\n", true},
		{"empty", "", false},
		{"prefix only", "wolo1", false},
		{"invented account", "wolo1recipient000000000000000000000000000", false},
		{"bad checksum", badChecksum, false},
		{"truncated", valid[:len(valid)-1], false},
		{"wrong HRP", transportTestAddress(t, "cosmos", 20), false},
		{"validator HRP", transportTestAddress(t, "wolovaloper", 20), false},
		{"short payload", transportTestAddress(t, "wolo", 19), false},
		{"long payload", transportTestAddress(t, "wolo", 21), false},
		{"mixed case", "W" + valid[1:], false},
		{"noncanonical uppercase", strings.ToUpper(valid), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isWoloAddress(tc.address, "wolo"); got != tc.valid {
				t.Fatalf("isWoloAddress(%q) = %v, want %v", tc.address, got, tc.valid)
			}
		})
	}
}

func TestSettlementGetJSONRejectsUntrustedEnvelopes(t *testing.T) {
	t.Parallel()
	const maximumBytes = 1 << 20
	cases := []struct {
		name string
		body string
	}{
		{"duplicate members", `{"value":"first","value":"substituted"}`},
		{"case-folded member alias", `{"value":"first","VALUE":"substituted"}`},
		{"Unicode simple-folded member alias", `{"source_app":"first","ſource_app":"substituted"}`},
		{"escaped duplicate member", `{"value":"first","\u0076alue":"substituted"}`},
		{"trailing object", `{"value":"first"}{"value":"substituted"}`},
		{"trailing garbage", `{"value":"first"}untrusted`},
		{"oversized valid JSON", `{"value":"first","padding":"` + strings.Repeat("x", maximumBytes) + `"}`},
		{"null object", `null`},
		{"array object", `[]`},
		{"excessive nesting", `{"unused":` + strings.Repeat("[", 40) + `0` + strings.Repeat("]", 40) + `}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(tc.body))
			}))
			defer server.Close()
			var result struct {
				Value     string `json:"value"`
				SourceApp string `json:"source_app"`
			}
			if _, err := getJSON(context.Background(), server.URL, &result); err == nil {
				t.Fatalf("untrusted upstream JSON accepted: %s; decoded value %q", tc.name, result.Value)
			}
		})
	}
}

func TestSettlementGetJSONRefusesRedirectBeforeFollowing(t *testing.T) {
	t.Parallel()
	var destinationCalls atomic.Int32
	destination := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		destinationCalls.Add(1)
		_, _ = w.Write([]byte(`{"value":"redirected"}`))
	}))
	defer destination.Close()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, destination.URL, http.StatusTemporaryRedirect)
	}))
	defer upstream.Close()
	var result map[string]any
	if _, err := getJSON(context.Background(), upstream.URL, &result); err == nil {
		t.Error("redirected financial evidence accepted")
	}
	if got := destinationCalls.Load(); got != 0 {
		t.Fatalf("followed redirect to another source %d times", got)
	}
}

func TestSettlementGetJSONRejectsUnexpectedStatusAndEncoding(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name     string
		status   int
		encoding string
	}{
		{"created instead of retrieved", http.StatusCreated, ""},
		{"missing instead of zero balance", http.StatusNotFound, ""},
		{"unexpected compressed representation", http.StatusOK, "br"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if tc.encoding != "" {
					w.Header().Set("Content-Encoding", tc.encoding)
				}
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(`{"value":"ordinary"}`))
			}))
			defer server.Close()
			var result map[string]any
			if _, err := getJSON(context.Background(), server.URL, &result); err == nil {
				t.Fatalf("unexpected upstream response accepted: HTTP %d encoding=%q", tc.status, tc.encoding)
			}
		})
	}
}

func TestSettlementGetJSONPreservesCancellationAndOrdinaryResponses(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/cancel":
			<-r.Context().Done()
		case "/missing":
			http.NotFound(w, r)
		default:
			_, _ = w.Write([]byte(`{"value":"ordinary","future_upstream_field":true}`))
		}
	}))
	defer server.Close()
	var result struct {
		Value string `json:"value"`
	}
	if status, err := getJSON(context.Background(), server.URL, &result); status != http.StatusOK || err != nil || result.Value != "ordinary" {
		t.Fatalf("ordinary response rejected: status=%d result=%+v err=%v", status, result, err)
	}
	if status, err := getJSON(context.Background(), server.URL+"/missing", &result); status != http.StatusNotFound || err == nil {
		t.Fatalf("missing upstream object accepted: status=%d err=%v", status, err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if _, err := getJSON(ctx, server.URL+"/cancel", &result); err == nil {
		t.Fatal("cancelled upstream request accepted")
	}
}

func TestSettlementGetJSONDoesNotExposeUntrustedErrorBody(t *testing.T) {
	t.Parallel()
	const secret = "untrusted-upstream-sensitive-value"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(secret))
	}))
	defer server.Close()
	var result map[string]any
	_, err := getJSON(context.Background(), server.URL, &result)
	if err == nil {
		t.Fatal("unavailable upstream accepted")
	}
	if strings.Contains(err.Error(), secret) {
		t.Fatalf("upstream error body was copied into error: %v", err)
	}
}

func TestSettlementHTTPRejectsAmbiguousAndOversizedRequestBodies(t *testing.T) {
	t.Parallel()
	cfg := settlementConfig{AuthToken: "local-test-token", StateDir: t.TempDir(), AddressPrefix: "wolo", ChainID: "wolo-1"}
	handler := cfg.newSettlementHTTPHandler()
	routes := []string{
		"/settlement/v1/payouts",
		"/settlement/v1/runs/validate",
		"/settlement/v1/runs",
		"/settlement/v1/challenges/validate",
		"/settlement/v1/challenges",
	}
	bodies := []struct {
		name string
		body string
	}{
		{"duplicate member", `{"memo":"one","memo":"two"}`},
		{"escaped duplicate member", `{"memo":"one","\u006demo":"two"}`},
		{"case-folded member alias", `{"memo":"one","MEMO":"two"}`},
		{"nested case-folded member alias", `{"payouts":[{"amount_uwolo":"1","AMOUNT_UWOLO":"2"}]}`},
		{"Unicode simple-folded member alias", `{"source_app":"one","ſource_app":"two"}`},
		{"nested Unicode simple-folded member alias", `{"payouts":[{"request_id":"one","requeſt_id":"two"}]}`},
		{"trailing object", `{} {}`},
		{"trailing garbage", `{} extra`},
		{"oversized JSON", `{"memo":"` + strings.Repeat("x", 1<<20) + `"}`},
		{"null object", `null`},
		{"array object", `[]`},
		{"excessive nesting", `{"unused":` + strings.Repeat("[", 40) + `0` + strings.Repeat("]", 40) + `}`},
	}
	for _, route := range routes {
		t.Run(route, func(t *testing.T) {
			for _, body := range bodies {
				t.Run(body.name, func(t *testing.T) {
					request := httptest.NewRequest(http.MethodPost, route, strings.NewReader(body.body))
					request.Header.Set("Authorization", "Bearer "+cfg.AuthToken)
					recorder := httptest.NewRecorder()
					handler.ServeHTTP(recorder, request)
					var response struct {
						Detail string `json:"detail"`
					}
					if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
						t.Fatal(err)
					}
					if recorder.Code != http.StatusBadRequest || response.Detail != "request body must be valid JSON" {
						t.Fatalf("body reached request semantics instead of strict parser: HTTP %d detail=%q", recorder.Code, response.Detail)
					}
				})
			}
		})
	}
	// A single ordinary object must continue to reach normal semantic validation.
	request := httptest.NewRequest(http.MethodPost, routes[0], strings.NewReader(`{}`))
	request.Header.Set("Authorization", "Bearer "+cfg.AuthToken)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if strings.Contains(recorder.Body.String(), "request body must be valid JSON") {
		t.Fatal("ordinary JSON object was incorrectly rejected by request parser")
	}
}

func TestSettlementHTTPStopsReadingOversizedBody(t *testing.T) {
	t.Parallel()
	body := `{"memo":"` + strings.Repeat("x", 2<<20) + `"}`
	reader := &io.LimitedReader{R: strings.NewReader(body), N: int64(len(body))}
	request := httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", reader)
	response := httptest.NewRecorder()
	(settlementConfig{}).newSettlementHTTPHandler().ServeHTTP(response, request)
	if consumed := int64(len(body)) - reader.N; consumed > (1<<20)+1 {
		t.Fatalf("oversized request consumed %d bytes before rejection", consumed)
	}
	if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), "request body must be valid JSON") {
		t.Fatalf("oversized request not rejected by parser: HTTP %d %s", response.Code, response.Body.String())
	}
}

func TestSettlementHTTPRefusesUnexpectedRequestEncoding(t *testing.T) {
	t.Parallel()
	request := httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", strings.NewReader(`{}`))
	request.Header.Set("Content-Encoding", "br")
	response := httptest.NewRecorder()
	(settlementConfig{}).newSettlementHTTPHandler().ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest || !strings.Contains(response.Body.String(), "request body must be valid JSON") {
		t.Fatalf("unsupported representation reached execution semantics: HTTP %d %s", response.Code, response.Body.String())
	}
}

func TestSettlementHTTPServerBoundsResourcesWithoutShorteningRunBudget(t *testing.T) {
	t.Parallel()
	cfg := settlementConfig{ListenAddr: "127.0.0.1:8092", RequestTimeout: 30 * time.Second, ConfirmTimeout: 15 * time.Second, LookupTimeout: 5 * time.Second}
	server := cfg.newSettlementHTTPServer()
	if server.Addr != cfg.ListenAddr || server.Handler == nil {
		t.Fatalf("server lost settlement binding: %+v", server)
	}
	if server.ReadHeaderTimeout <= 0 || server.ReadHeaderTimeout > 5*time.Second || server.ReadTimeout <= 0 || server.ReadTimeout > 10*time.Second {
		t.Fatalf("header/body reads have no tight deadline: %+v", server)
	}
	if server.IdleTimeout <= 0 || server.IdleTimeout > 30*time.Second || server.MaxHeaderBytes <= 0 || server.MaxHeaderBytes > 16384 {
		t.Fatalf("idle connections or headers are not bounded: %+v", server)
	}
	minimumBudget := time.Duration(settlementMaxRunPayouts) * (cfg.RequestTimeout + cfg.ConfirmTimeout + cfg.LookupTimeout)
	if server.WriteTimeout < minimumBudget || server.WriteTimeout > minimumBudget+time.Minute {
		t.Fatalf("write deadline %s is incompatible with bounded run budget %s", server.WriteTimeout, minimumBudget)
	}
}

func TestSettlementHTTPRefusesExcessWorkAndReleasesCancelledRequests(t *testing.T) {
	t.Parallel()
	entered := make(chan struct{}, 16)
	release := make(chan struct{})
	defer close(release)
	var executions atomic.Int32
	handler := boundedSettlementHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		executions.Add(1)
		entered <- struct{}{}
		select {
		case <-r.Context().Done():
		case <-release:
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var workers sync.WaitGroup
	for i := 0; i < 16; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, "/local", nil).WithContext(ctx))
		}()
	}
	for i := 0; i < 16; i++ {
		select {
		case <-entered:
		case <-time.After(5 * time.Second):
			t.Fatal("bounded requests failed to enter handler")
		}
	}
	refused := httptest.NewRecorder()
	handler.ServeHTTP(refused, httptest.NewRequest(http.MethodPost, "/financial", nil))
	if refused.Code != http.StatusServiceUnavailable || executions.Load() != 16 {
		t.Fatalf("excess request entered execution or queued: HTTP %d executions=%d", refused.Code, executions.Load())
	}
	cancel()
	workers.Wait()
	if executions.Load() != 16 {
		t.Fatalf("cancellation retried accepted work: executions=%d", executions.Load())
	}
	// An already-cancelled read exercises release of capacity without another
	// financial operation or a retry of any of the original requests.
	available := httptest.NewRecorder()
	handler.ServeHTTP(available, httptest.NewRequest(http.MethodGet, "/local", nil).WithContext(ctx))
	if available.Code != http.StatusNoContent || executions.Load() != 17 {
		t.Fatalf("cancelled reads did not release capacity: HTTP %d executions=%d", available.Code, executions.Load())
	}
}

func TestSettlementCLIJSONUsesSameBoundedUnambiguousContract(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name  string
		body  string
		valid bool
	}{
		{"ordinary object", `{"value":"ordinary","future_field":true}`, true},
		{"duplicate member", `{"value":"one","value":"two"}`, false},
		{"case-folded member alias", `{"value":"one","VALUE":"two"}`, false},
		{"trailing object", `{} {}`, false},
		{"null object", `null`, false},
		{"array object", `[]`, false},
		{"oversized object", `{"value":"` + strings.Repeat("x", 1<<20) + `"}`, false},
		{"excessive nesting", `{"unused":` + strings.Repeat("[", 40) + `0` + strings.Repeat("]", 40) + `}`, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "request.json")
			if err := os.WriteFile(path, []byte(tc.body), 0600); err != nil {
				t.Fatal(err)
			}
			var request struct {
				Value string `json:"value"`
			}
			err := readJSONInput(path, &request)
			if (err == nil) != tc.valid {
				t.Fatalf("readJSONInput validity=%v, want %v: %v", err == nil, tc.valid, err)
			}
			if tc.valid && request.Value != "ordinary" {
				t.Fatalf("valid CLI request changed: %+v", request)
			}
		})
	}
}

func TestSettlementRequestRejectsCaseFoldedMemberAliases(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name    string
		body    string
		decoded func(settlementRunRequest) string
	}{
		{"top-level ASCII", `{"memo":"authorized","MEMO":"substituted"}`, func(r settlementRunRequest) string { return r.Memo }},
		{"top-level Unicode", `{"source_app":"authorized","ſource_app":"substituted"}`, func(r settlementRunRequest) string { return r.SourceApp }},
		{"nested ASCII", `{"payouts":[{"amount_uwolo":"authorized","AMOUNT_UWOLO":"substituted"}]}`, func(r settlementRunRequest) string { return r.Payouts[0].AmountUWolo }},
		{"nested Unicode", `{"payouts":[{"request_id":"authorized","requeſt_id":"substituted"}]}`, func(r settlementRunRequest) string { return r.Payouts[0].RequestID }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			// Prove that these distinct JSON spellings address the same actual
			// request field under the standard decoder used by settlement.
			var permissive settlementRunRequest
			if err := json.Unmarshal([]byte(tc.body), &permissive); err != nil {
				t.Fatal(err)
			}
			if got := tc.decoded(permissive); got != "substituted" {
				t.Fatalf("fixture did not reproduce a decoder alias: got %q", got)
			}
			var strict settlementRunRequest
			if err := decodeSettlementObject(strings.NewReader(tc.body), &strict); err == nil {
				t.Fatalf("case-folded financial field substitution accepted: %s", tc.body)
			}
		})
	}
}

func TestSettlementRequestPreservesSingleAliasesAndDistinctObjectFields(t *testing.T) {
	t.Parallel()
	var request settlementRunRequest
	body := `{"MEMO":"ordinary","ſource_app":"compatible","future_field":true,"payouts":[{"AMOUNT_UWOLO":"1"},{"amount_uwolo":"2"}]}`
	if err := decodeSettlementObject(strings.NewReader(body), &request); err != nil {
		t.Fatalf("single compatible spelling or fields in distinct objects rejected: %v", err)
	}
	if request.Memo != "ordinary" || request.SourceApp != "compatible" || len(request.Payouts) != 2 || request.Payouts[0].AmountUWolo != "1" || request.Payouts[1].AmountUWolo != "2" {
		t.Fatalf("compatible single spellings changed meaning: %+v", request)
	}
}
