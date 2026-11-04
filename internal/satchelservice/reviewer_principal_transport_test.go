package satchelservice

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"sort"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// The test changes only the private dialer. The production URL, Host, method,
// no-proxy/redirect/retry policy, token and pinned identity remain unchanged.
func principalTransportTestClient(t *testing.T, handler http.Handler, vault, policy string) (*ReviewerPrincipalJournalClient, *atomic.Int32) {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	client, err := NewReviewerPrincipalJournalClient(testHTTPToken, vault, policy)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	transport, ok := client.http.Transport.(*http.Transport)
	if !ok || transport.Proxy != nil || !transport.DisableCompression || !transport.DisableKeepAlives || transport.MaxConnsPerHost != 2 || client.http.Timeout != time.Second || client.http.CheckRedirect == nil {
		t.Fatal("ambient transport authority enabled")
	}
	listener, err := url.Parse(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	var dials atomic.Int32
	transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		dials.Add(1)
		if address != "127.0.0.1:8094" {
			return nil, errors.New("unexpected test destination")
		}
		return (&net.Dialer{Timeout: 500 * time.Millisecond}).DialContext(ctx, network, listener.Host)
	}
	return client, &dials
}
func principalTransportFailure(t *testing.T, snapshot ReviewerPrincipalJournalSnapshot, err error) {
	t.Helper()
	if !reflect.DeepEqual(snapshot, ReviewerPrincipalJournalSnapshot{}) || err != ErrReviewerHeld {
		t.Fatal("partial evidence or transport details escaped", snapshot, err)
	}
}

func TestReviewerPrincipalTransportActualSDKFullJournalAcrossPrivateHTTP(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	f.chain.release()
	result, err := f.engine.Submit(t.Context(), f.request)
	if err != nil || result.Status != "ACCEPTED" {
		t.Fatal(result, err)
	}
	if _, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), f.request.OwnerID); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("unresolved native operation was omitted")
	}
	confirmed, err := f.engine.Reconcile(t.Context(), f.request.OperationID)
	if err != nil || confirmed.Status != "CONFIRMED" {
		t.Fatal(confirmed, err)
	}
	before := readTestCustodyJournal(t, f.engine)
	cfg := testHTTPConfig(t)
	cfg.Accepting = false
	cfg.Health.VaultAddress = f.engine.policy.Vault
	actual := testHTTPHandler(t, f.engine, cfg)
	var calls atomic.Int32
	client, dials := principalTransportTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		body, err := io.ReadAll(r.Body)
		if err != nil || r.Method != http.MethodPost || r.Host != "127.0.0.1:8094" || r.URL.Path != reviewerPrincipalCheckpointPath || r.URL.RawQuery != "" ||
			r.Header.Get("Authorization") != "Bearer "+testHTTPToken || r.Header.Get("Content-Type") != "application/json" || r.Header.Get("Accept") != "application/json" || r.Header.Get("Accept-Encoding") != "" ||
			string(body) != `{"protocol":1,"owner_id":"`+f.request.OwnerID+`"}` {
			t.Error("fixed principal request changed", r.Method, r.URL, string(body))
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		r.Body = io.NopCloser(bytes.NewReader(body))
		actual.ServeHTTP(w, r)
	}), f.config.Vault, hashJSON(f.engine.policy))
	t.Setenv("HTTP_PROXY", "http://192.0.2.1:1234")
	t.Setenv("HTTPS_PROXY", "http://192.0.2.1:1234")
	t.Setenv("ALL_PROXY", "http://192.0.2.1:1234")
	t.Setenv("NO_PROXY", "")
	ctx := context.WithValue(t.Context(), "custody_url", "http://192.0.2.2:9999/alternate")
	got, err := client.ReadReviewerPrincipalJournal(ctx, f.request.OwnerID)
	if err != nil || !principalJournalCurrent(got, f.request.OwnerID, f.config.Vault, hashJSON(f.engine.policy), time.Now()) || len(got.effects) != 1 ||
		got.digest != before.JournalDigest || got.effects[f.request.OperationID].TxHash != confirmed.TxHash || got.effects[f.request.OperationID].Status != "CONFIRMED" || calls.Load() != 1 || dials.Load() != 1 {
		t.Fatal("actual separately read SDK journal lost its identity", got, err, calls.Load(), dials.Load())
	}
	if after := readTestCustodyJournal(t, f.engine); !reflect.DeepEqual(before, after) || f.SDKSigns.Load() != 1 || f.chain.broadcasts != 1 {
		t.Fatal("private snapshot read executed or mutated custody")
	}
}

func TestReviewerPrincipalTransportExistingPrivateAuthAndStrictRequestBoundary(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	cfg := testHTTPConfig(t)
	cfg.Accepting = false
	cfg.Health.VaultAddress = f.config.Vault
	handler := testHTTPHandler(t, f.engine, cfg)
	call := func(method, body, peer, token, path string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, "http://localhost"+path, strings.NewReader(body))
		r.RemoteAddr = peer
		r.Header.Set("Authorization", "Bearer "+token)
		r.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	valid := `{"protocol":1,"owner_id":"` + f.request.OwnerID + `"}`
	if w := call(http.MethodPost, valid, "127.0.0.1:1234", testHTTPToken, reviewerPrincipalCheckpointPath); w.Code != http.StatusOK {
		t.Fatal(w.Code, w.Body.String())
	}
	for _, body := range []string{`{"protocol":2,"owner_id":"owner-1"}`, `{"protocol":1}`, `{"protocol":1,"owner_id":null}`, `{"protocol":1,"owner_id":""}`, `{"protocol":1,"owner_id":"http://other.invalid/"}`, `{"protocol":1,"owner_id":"owner-1","owner_id":"owner-2"}`, `{"protocol":1,"owner_id":"owner-1","Owner_ID":"owner-2"}`, `{"protocol":1,"owner_id":"owner-1","all_obligations_covered":true}`, `{"protocol":1,"owner_id":"owner-1","policy_digest":"caller"}`, strings.Repeat(" ", reviewerPrincipalRequestMaxBytes) + valid} {
		if w := call(http.MethodPost, body, "127.0.0.1:1234", testHTTPToken, reviewerPrincipalCheckpointPath); w.Code < 400 {
			t.Fatal("caller substituted a snapshot authority", body, w.Body.String())
		}
	}
	for _, input := range []struct{ method, peer, token, path string }{
		{http.MethodGet, "127.0.0.1:1234", testHTTPToken, reviewerPrincipalCheckpointPath},
		{http.MethodPost, "192.0.2.1:1234", testHTTPToken, reviewerPrincipalCheckpointPath},
		{http.MethodPost, "127.0.0.1:1234", "wrong", reviewerPrincipalCheckpointPath},
		{http.MethodPost, "127.0.0.1:1234", testHTTPToken, reviewerPrincipalCheckpointPath + "?policy=caller"},
	} {
		if w := call(input.method, valid, input.peer, input.token, input.path); w.Code < 400 {
			t.Fatal("private route/auth boundary bypassed", input, w.Body.String())
		}
	}
	legacy := testHTTPHandler(t, &httpTestBackend{}, cfg)
	r := httptest.NewRequest(http.MethodPost, "http://localhost"+reviewerPrincipalCheckpointPath, strings.NewReader(valid))
	r.RemoteAddr = "127.0.0.1:1234"
	r.Header.Set("Authorization", "Bearer "+testHTTPToken)
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	legacy.ServeHTTP(w, r)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatal("legacy backend invented principal evidence", w.Code, w.Body.String())
	}
	if f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("invalid evidence request signed or broadcast")
	}
}

// These are deliberately synthetic service envelopes for parser/identity
// rejection tests. They are NOT independently authenticated chain evidence.
func principalTransportWireFixture(t *testing.T) reviewerPrincipalCheckpointWire {
	t.Helper()
	vault := testHTTPAddress(t, 110)
	id := "12345678-1234-4123-8123-123456789abc"
	return reviewerPrincipalCheckpointWire{Protocol: 1, Kind: "custody_principal_checkpoint", ChainID: "wolo-1", Denom: "uwolo", Vault: vault, PolicyDigest: strings.Repeat("b", 64), JournalDigest: strings.Repeat("a", 64), OwnerID: "owner-1", ObservedAtMS: time.Now().UnixMilli(),
		Effects: []reviewerPrincipalEffectWire{
			{OperationID: "satchel:ticket:7", Kind: "wager", OwnerID: "owner-1", AmountUWolo: "7000000", Recipient: testHTTPAddress(t, 111), Memo: "AoE2HDBets bet ticket v1 · ticket 7", OriginalFingerprint: strings.Repeat("c", 64), ReservationDigest: strings.Repeat("d", 64), FeeUWolo: "2500", Status: "CONFIRMED", TxHash: strings.Repeat("A", 64), Height: 42},
			{OperationID: "satchel:withdrawal:" + id, Kind: "withdrawal", OwnerID: "owner-2", AmountUWolo: "1000000", Recipient: testHTTPAddress(t, 112), Memo: "aoe2war/satchel/withdraw/v1/" + id, OriginalFingerprint: strings.Repeat("e", 64), ReservationDigest: strings.Repeat("f", 64), Status: "FAILED", TxHash: strings.Repeat("B", 64), Height: 43},
		}}
}

func TestReviewerPrincipalTransportRejectsMalformedAndSubstitutedServiceResponses(t *testing.T) {
	for _, name := range []string{"valid_all_owners", "status", "media", "media_parameter", "charset", "encoding", "utf8", "unknown_authority", "duplicate", "folded", "missing_field", "missing_effect_field", "effect_unknown", "trailing", "truncated_json", "oversize", "declared_oversize", "truncated_http", "redirect", "owner", "vault", "policy", "zero_root", "future", "stale", "null_effects", "unsorted", "duplicate_operation", "bad_owner", "bad_amount", "wager_fraction", "fee_zero", "fee_overflow", "fingerprint_zero", "reservation_zero", "bad_memo", "wrong_kind", "unknown_status", "accepted", "failed_height", "confirmed_hash", "refused_hash", "withdrawal_fee", "withdrawal_memo"} {
		t.Run(name, func(t *testing.T) {
			wire := principalTransportWireFixture(t)
			vault, policy := wire.Vault, wire.PolicyDigest
			switch name {
			case "owner":
				wire.OwnerID = "other-owner"
			case "vault":
				wire.Vault = testHTTPAddress(t, 113)
			case "policy":
				wire.PolicyDigest = strings.Repeat("c", 64)
			case "zero_root":
				wire.JournalDigest = strings.Repeat("0", 64)
			case "future":
				wire.ObservedAtMS = time.Now().Add(time.Second).UnixMilli()
			case "stale":
				wire.ObservedAtMS = time.Now().Add(-3 * time.Second).UnixMilli()
			case "null_effects":
				wire.Effects = nil
			case "unsorted":
				wire.Effects[0], wire.Effects[1] = wire.Effects[1], wire.Effects[0]
			case "duplicate_operation":
				wire.Effects[1] = wire.Effects[0]
			case "bad_owner":
				wire.Effects[0].OwnerID = "owner with spaces"
			case "bad_amount":
				wire.Effects[0].AmountUWolo = "07000000"
			case "wager_fraction":
				wire.Effects[0].AmountUWolo = "7000001"
			case "fee_zero":
				wire.Effects[0].FeeUWolo = "0"
			case "fee_overflow":
				wire.Effects[0].FeeUWolo = "1000001"
			case "fingerprint_zero":
				wire.Effects[0].OriginalFingerprint = strings.Repeat("0", 64)
			case "reservation_zero":
				wire.Effects[0].ReservationDigest = strings.Repeat("0", 64)
			case "bad_memo":
				wire.Effects[0].Memo = "caller principal"
			case "wrong_kind":
				wire.Effects[0].Kind = "claim_return"
			case "unknown_status":
				wire.Effects[0].Status = "UNKNOWN"
			case "accepted":
				wire.Effects[0].Status = "ACCEPTED"
			case "failed_height":
				wire.Effects[1].Height = 0
			case "confirmed_hash":
				wire.Effects[0].TxHash = strings.Repeat("a", 64)
			case "refused_hash":
				wire.Effects[0].Status = "REFUSED"
			case "withdrawal_fee":
				wire.Effects[1].FeeUWolo = "2500"
			case "withdrawal_memo":
				wire.Effects[1].Memo = "aoe2war/satchel/withdraw/v1/other"
			}
			var calls atomic.Int32
			client, dials := principalTransportTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				w.Header().Set("Content-Type", "application/json")
				body, err := json.Marshal(wire)
				if err != nil {
					t.Error(err)
					return
				}
				switch name {
				case "status":
					w.WriteHeader(http.StatusUnauthorized)
				case "media":
					w.Header().Set("Content-Type", "text/plain")
				case "media_parameter":
					w.Header().Set("Content-Type", "application/json; authority=caller")
				case "charset":
					w.Header().Set("Content-Type", "application/json; charset=iso-8859-1")
				case "encoding":
					w.Header().Set("Content-Encoding", "gzip")
				case "utf8":
					body = append(body, 0xff)
				case "unknown_authority":
					body = append([]byte(`{"all_obligations_covered":true,`), body[1:]...)
				case "duplicate":
					body = append([]byte(`{"protocol":1,`), body[1:]...)
				case "folded":
					body = append([]byte(`{"Owner_ID":"caller",`), body[1:]...)
				case "missing_field":
					body = bytes.Replace(body, []byte(`"denom":"uwolo",`), nil, 1)
				case "missing_effect_field":
					body = bytes.Replace(body, []byte(`"fee_uwolo":"",`), nil, 1)
				case "effect_unknown":
					body = bytes.Replace(body, []byte(`"kind":"wager",`), []byte(`"kind":"wager","spend_authorized":true,`), 1)
				case "trailing":
					body = append(body, []byte(` {}`)...)
				case "truncated_json":
					body = body[:len(body)-1]
				case "oversize":
					body = append(bytes.Repeat([]byte(" "), reviewerPrincipalMaxBytes), body...)
				case "declared_oversize":
					w.Header().Set("Content-Length", fmt.Sprint(reviewerPrincipalMaxBytes+1))
				case "truncated_http":
					w.Header().Set("Content-Length", fmt.Sprint(len(body)+20))
				case "redirect":
					w.Header().Set("Location", "http://127.0.0.1:8094/alternate")
					w.WriteHeader(http.StatusTemporaryRedirect)
				}
				_, _ = w.Write(body)
			}), vault, policy)
			got, err := client.ReadReviewerPrincipalJournal(t.Context(), "owner-1")
			if name == "valid_all_owners" {
				if err != nil || !got.valid || len(got.effects) != 2 || got.effects[wire.Effects[1].OperationID].Owner != "owner-2" {
					t.Fatal("global inventory was filtered by request owner", got, err)
				}
			} else {
				principalTransportFailure(t, got, err)
			}
			if calls.Load() != 1 || dials.Load() != 1 {
				t.Fatal("read retried or redirected", calls.Load(), dials.Load())
			}
		})
	}
}

type principalTransportRoundTrip func(*http.Request) (*http.Response, error)

func (f principalTransportRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestReviewerPrincipalTransportInputCancelAndCompletionClockFloor(t *testing.T) {
	wire := principalTransportWireFixture(t)
	client, err := NewReviewerPrincipalJournalClient(testHTTPToken, wire.Vault, wire.PolicyDigest)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	var calls atomic.Int32
	client.http.Transport = principalTransportRoundTrip(func(r *http.Request) (*http.Response, error) {
		calls.Add(1)
		<-r.Context().Done()
		return nil, errors.New("protected transport detail: " + testHTTPToken)
	})
	for _, owner := range []string{"", "owner with spaces", strings.Repeat("a", 101), "http://other.invalid/"} {
		got, err := client.ReadReviewerPrincipalJournal(t.Context(), owner)
		principalTransportFailure(t, got, err)
	}
	got, err := client.ReadReviewerPrincipalJournal(nil, "owner-1")
	principalTransportFailure(t, got, err)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	got, err = client.ReadReviewerPrincipalJournal(ctx, "owner-1")
	principalTransportFailure(t, got, err)
	if calls.Load() != 0 {
		t.Fatal("invalid input performed IO")
	}
	ctx, cancel = context.WithTimeout(t.Context(), 20*time.Millisecond)
	defer cancel()
	got, err = client.ReadReviewerPrincipalJournal(ctx, "owner-1")
	principalTransportFailure(t, got, err)
	if calls.Load() != 1 || !errors.Is(ctx.Err(), context.DeadlineExceeded) {
		t.Fatal("caller deadline lost or read retried")
	}
	for _, bad := range []struct{ token, vault, policy string }{{"invalid secret", wire.Vault, wire.PolicyDigest}, {testHTTPToken, "http://other.invalid", wire.PolicyDigest}, {testHTTPToken, wire.Vault, strings.Repeat("0", 64)}} {
		if c, err := NewReviewerPrincipalJournalClient(bad.token, bad.vault, bad.policy); c != nil || err != ErrReviewerHeld {
			t.Fatal("invalid operator source accepted")
		}
	}
	initial := time.Now()
	wire.ObservedAtMS = initial.Add(-1995 * time.Millisecond).UnixMilli()
	clockClient, _ := principalTransportTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(30 * time.Millisecond)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(wire)
	}), wire.Vault, wire.PolicyDigest)
	clockClient.now = func() time.Time { return initial } // rollback/frozen wall clock cannot renew freshness during IO.
	got, err = clockClient.ReadReviewerPrincipalJournal(t.Context(), wire.OwnerID)
	principalTransportFailure(t, got, err)
}

func TestReviewerPrincipalTransportBoundedTenThousandOperationDecoder(t *testing.T) {
	wire := principalTransportWireFixture(t)
	effect := wire.Effects[0]
	wire.Effects = make([]reviewerPrincipalEffectWire, reviewerPrincipalMaxRows)
	for i := range wire.Effects {
		entry := effect
		entry.OperationID = fmt.Sprintf("satchel:ticket:%d", i+1)
		wire.Effects[i] = entry
	}
	sort.Slice(wire.Effects, func(i, j int) bool { return wire.Effects[i].OperationID < wire.Effects[j].OperationID })
	raw, err := json.Marshal(wire)
	if err != nil || len(raw) > reviewerPrincipalMaxBytes {
		t.Fatal("fixture exceeded bounded wire", len(raw), err)
	}
	var decoded reviewerPrincipalCheckpointWire
	if err := decodePrincipalCheckpointWire(raw, &decoded); err != nil || len(decoded.Effects) != reviewerPrincipalMaxRows {
		t.Fatal("complete bounded inventory hit unrelated global JSON node limit", err)
	}
	wire.Effects = append(wire.Effects, effect)
	raw, err = json.Marshal(wire)
	if err != nil {
		t.Fatal(err)
	}
	if err := decodePrincipalCheckpointWire(raw, &decoded); err != ErrReviewerHeld {
		t.Fatal("unbounded operation inventory accepted")
	}
}
