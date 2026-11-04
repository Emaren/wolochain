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
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type reviewerReserveTestTransport func(*http.Request) (*http.Response, error)

func (f reviewerReserveTestTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func reviewerReserveTestCustodyCheckpoint(t *testing.T) ReviewerCustodyFeeCheckpoint {
	t.Helper()
	return ReviewerCustodyFeeCheckpoint{Protocol: 1, Kind: "custody_fee_checkpoint", ChainID: "wolo-1", Denom: "uwolo",
		Vault: testHTTPAddress(t, 110), JournalDigest: strings.Repeat("a", 64), PolicyDigest: strings.Repeat("b", 64), ObservedAtMS: 1800000000000,
		UnresolvedFees: []ReviewerPendingFee{}, AccountedOperations: map[string]string{"satchel:ticket:7": "NOT_RECORDED"},
		AccountedFingerprints: map[string]string{"satchel:ticket:7": ""}, WagerApprovalKeyFingerprint: strings.Repeat("c", 64)}
}

// Only the private transport dials the test listener. The production URL,
// request Host, method, redirect policy and constructor remain unchanged.
func reviewerReserveTestClient(t *testing.T, handler http.Handler) (*ReviewerCustodyFeeClient, *atomic.Int32) {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	client, err := NewReviewerCustodyFeeClient(testHTTPToken)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(client.Close)
	transport, ok := client.http.Transport.(*http.Transport)
	if !ok || transport.Proxy != nil || !transport.DisableCompression || !transport.DisableKeepAlives || client.http.Timeout != time.Second || client.http.CheckRedirect == nil {
		t.Fatal("production constructor did not disable ambient transport authority")
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

func reviewerReserveRequireSourceFailure(t *testing.T, got ReviewerCustodyFeeCheckpoint, err error) {
	t.Helper()
	if !reflect.DeepEqual(got, ReviewerCustodyFeeCheckpoint{}) || err != ReviewerCensusSourceInvalid || err.Error() != "reviewer_census_source_identity_invalid" {
		t.Fatal("reader exposed partial checkpoint or non-fixed error", got, err)
	}
}

func TestReviewerCustodyFeeClientFixedPrivateWire(t *testing.T) {
	want := reviewerReserveTestCustodyCheckpoint(t)
	var calls atomic.Int32
	client, dials := reviewerReserveTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		body, err := io.ReadAll(r.Body)
		if err != nil || r.Method != http.MethodPost || r.Host != "127.0.0.1:8094" || r.URL.Path != "/satchel/v1/custody/fee-checkpoint" || r.URL.RawQuery != "" ||
			r.Header.Get("Authorization") != "Bearer "+testHTTPToken || r.Header.Get("Content-Type") != "application/json" || r.Header.Get("Accept") != "application/json" || r.Header.Get("Accept-Encoding") != "" ||
			string(body) != `{"protocol":1,"operation_ids":["satchel:ticket:7"]}` {
			t.Errorf("fixed custody request changed: %s %s %q", r.Method, r.URL, body)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=UTF-8")
		_ = json.NewEncoder(w).Encode(want)
	}))
	t.Setenv("HTTP_PROXY", "http://192.0.2.1:1234")
	t.Setenv("HTTPS_PROXY", "http://192.0.2.1:1234")
	t.Setenv("ALL_PROXY", "http://192.0.2.1:1234")
	t.Setenv("NO_PROXY", "")
	ctx := context.WithValue(t.Context(), "custody_url", "http://192.0.2.2:9999/alternate")
	ctx = context.WithValue(ctx, "bank_verified", true)
	got, err := client.ReadReviewerCustodyFees(ctx, []string{"satchel:ticket:7"})
	if err != nil || !reflect.DeepEqual(got, want) || calls.Load() != 1 || dials.Load() != 1 {
		t.Fatal("fixed private checkpoint read failed or retried", got, err, calls.Load(), dials.Load())
	}
}

func TestReviewerCustodyFeeClientRejectsUntrustedResponsesWithoutRetry(t *testing.T) {
	valid, err := json.Marshal(reviewerReserveTestCustodyCheckpoint(t))
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"status", "media", "media_parameter", "charset", "encoding", "utf8", "unknown", "duplicate", "folded", "truncated_json", "oversize", "declared_oversize", "missing_status_key", "missing_fingerprint_key", "null_fees", "truncated_http", "redirect"} {
		t.Run(name, func(t *testing.T) {
			var calls atomic.Int32
			client, _ := reviewerReserveTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				w.Header().Set("Content-Type", "application/json")
				body := append([]byte{}, valid...)
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
				case "unknown":
					body = append([]byte(`{"bank_authenticated":true,`), body[1:]...)
				case "duplicate":
					body = append([]byte(`{"protocol":1,`), body[1:]...)
				case "folded":
					body = append([]byte(`{"Protocol":1,`), body[1:]...)
				case "truncated_json":
					body = body[:len(body)-1]
				case "oversize":
					body = append(bytes.Repeat([]byte(" "), custodyFeeCheckpointMaxOutput), body...)
				case "declared_oversize":
					w.Header().Set("Content-Length", fmt.Sprint(custodyFeeCheckpointMaxOutput+1))
				case "missing_status_key":
					body = bytes.Replace(body, []byte(`"satchel:ticket:7":"NOT_RECORDED"`), []byte(`"satchel:ticket:8":"NOT_RECORDED"`), 1)
				case "missing_fingerprint_key":
					body = bytes.Replace(body, []byte(`"satchel:ticket:7":""`), []byte(`"satchel:ticket:8":""`), 1)
				case "null_fees":
					body = bytes.Replace(body, []byte(`"unresolved_fees":[]`), []byte(`"unresolved_fees":null`), 1)
				case "truncated_http":
					conn, _, err := w.(http.Hijacker).Hijack()
					if err != nil {
						t.Error(err)
						return
					}
					_, _ = io.WriteString(conn, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n{")
					_ = conn.Close()
					return
				case "redirect":
					w.Header().Set("Location", "http://127.0.0.1:8094/alternate")
					w.WriteHeader(http.StatusTemporaryRedirect)
					return
				}
				_, _ = w.Write(body)
			}))
			got, err := client.ReadReviewerCustodyFees(t.Context(), []string{"satchel:ticket:7"})
			reviewerReserveRequireSourceFailure(t, got, err)
			if calls.Load() != 1 {
				t.Fatal("untrusted read retried or followed redirect", calls.Load())
			}
		})
	}
}

func TestReviewerReserveFileRechecksMutatedPathsOnEveryRead(t *testing.T) {
	for _, name := range []string{"missing", "symlink", "oversize"} {
		t.Run(name, func(t *testing.T) {
			path := reviewerReserveTestFilePath(t)
			if err := os.WriteFile(path, []byte("opaque coverage"), 0600); err != nil {
				t.Fatal(err)
			}
			reader, err := NewReviewerReserveFile(path)
			if err != nil {
				t.Fatal(err)
			}
			switch name {
			case "missing", "symlink":
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
				if name == "symlink" {
					target := path + ".target"
					if err := os.WriteFile(target, []byte("replacement"), 0600); err != nil {
						t.Fatal(err)
					}
					if err := os.Symlink(target, path); err != nil {
						t.Fatal(err)
					}
				}
			case "oversize":
				if err := os.WriteFile(path, make([]byte, reviewerReserveCensusMaxBytes+1), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if raw, err := reader.ReadReviewerReserveCoverage(t.Context()); raw != nil || err != ReviewerCensusCoverageInvalid {
				t.Fatal("reader trusted stale constructor checks", name, len(raw), err)
			}
		})
	}
}

func TestReviewerCustodyFeeClientRejectsInvalidInputBeforeIOAndPropagatesCancel(t *testing.T) {
	client, err := NewReviewerCustodyFeeClient(testHTTPToken)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	var calls atomic.Int32
	client.http.Transport = reviewerReserveTestTransport(func(r *http.Request) (*http.Response, error) {
		calls.Add(1)
		<-r.Context().Done()
		return nil, errors.New("transport detail must remain private: " + testHTTPToken)
	})
	for _, ids := range [][]string{{"satchel:ticket:07"}, {"satchel:ticket:7", "satchel:ticket:7"}, {"http://192.0.2.1/"}, make([]string, custodyFeeCheckpointMaxIDs+1)} {
		got, err := client.ReadReviewerCustodyFees(t.Context(), ids)
		reviewerReserveRequireSourceFailure(t, got, err)
	}
	got, err := client.ReadReviewerCustodyFees(nil, []string{"satchel:ticket:7"})
	reviewerReserveRequireSourceFailure(t, got, err)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	got, err = client.ReadReviewerCustodyFees(ctx, []string{"satchel:ticket:7"})
	reviewerReserveRequireSourceFailure(t, got, err)
	if calls.Load() != 0 {
		t.Fatal("invalid input performed network IO")
	}
	ctx, cancel = context.WithTimeout(t.Context(), 20*time.Millisecond)
	defer cancel()
	got, err = client.ReadReviewerCustodyFees(ctx, []string{"satchel:ticket:7"})
	reviewerReserveRequireSourceFailure(t, got, err)
	if calls.Load() != 1 || !errors.Is(ctx.Err(), context.DeadlineExceeded) {
		t.Fatal("read lost caller deadline or retried", calls.Load(), ctx.Err())
	}
	if c, err := NewReviewerCustodyFeeClient("invalid secret"); c != nil || err != ReviewerCensusUnconfigured {
		t.Fatal("invalid token accepted or exposed", c, err)
	}
}

func reviewerReserveTestFilePath(t *testing.T) string {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return filepath.Join(dir, "coverage.json")
}

func TestReviewerReserveFileRereadsProtectedBytesWithoutCachingOrAuthority(t *testing.T) {
	path := reviewerReserveTestFilePath(t)
	first, second := []byte(`{"version":1}`), []byte(`{"version":2}`)
	if err := os.WriteFile(path, first, 0600); err != nil {
		t.Fatal(err)
	}
	reader, err := NewReviewerReserveFile(path)
	if err != nil {
		t.Fatal("protected opaque coverage file refused", err)
	}
	got, err := reader.ReadReviewerReserveCoverage(t.Context())
	if err != nil || !bytes.Equal(got, first) {
		t.Fatal(got, err)
	}
	got[0] = 'x'
	if err := os.WriteFile(path, second, 0600); err != nil {
		t.Fatal(err)
	}
	got, err = reader.ReadReviewerReserveCoverage(t.Context())
	if err != nil || !bytes.Equal(got, second) {
		t.Fatal("file reader cached old coverage or shared returned bytes", got, err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if got, err := reader.ReadReviewerReserveCoverage(ctx); got != nil || err != ReviewerCensusCoverageInvalid {
		t.Fatal("canceled coverage read returned evidence", got, err)
	}
	if err := os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	if got, err := reader.ReadReviewerReserveCoverage(t.Context()); got != nil || err != ReviewerCensusCoverageInvalid || strings.Contains(err.Error(), path) {
		t.Fatal("reader trusted its constructor instead of rechecking file protection", got, err)
	}
}

func TestReviewerReserveFileRefusesUnprotectedPathsAndBounds(t *testing.T) {
	for _, name := range []string{"relative", "unclean", "missing", "mode", "symlink", "ancestor_symlink", "hardlink", "empty", "oversize"} {
		t.Run(name, func(t *testing.T) {
			path := reviewerReserveTestFilePath(t)
			if err := os.WriteFile(path, []byte("opaque signed bundle bytes"), 0600); err != nil {
				t.Fatal(err)
			}
			expected := ReviewerCensusCoverageInvalid
			switch name {
			case "relative":
				path, expected = "coverage.json", ReviewerCensusUnconfigured
			case "unclean":
				path, expected = filepath.Dir(path)+"/./coverage.json", ReviewerCensusUnconfigured
			case "missing":
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
			case "mode":
				if err := os.Chmod(path, 0644); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				link := path + ".link"
				if err := os.Symlink(path, link); err != nil {
					t.Fatal(err)
				}
				path = link
			case "ancestor_symlink":
				link := filepath.Join(filepath.Dir(path), "link")
				if err := os.Symlink(filepath.Dir(path), link); err != nil {
					t.Fatal(err)
				}
				path = filepath.Join(link, filepath.Base(path))
			case "hardlink":
				if err := os.Link(path, path+".link"); err != nil {
					t.Fatal(err)
				}
			case "empty", "oversize":
				size := 0
				if name == "oversize" {
					size = reviewerReserveCensusMaxBytes + 1
				}
				if err := os.WriteFile(path, make([]byte, size), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if reader, err := NewReviewerReserveFile(path); reader != nil || err != expected || strings.Contains(err.Error(), path) {
				t.Fatal("unprotected path accepted or leaked", reader, err)
			}
		})
	}
	path := reviewerReserveTestFilePath(t)
	if err := os.WriteFile(path, bytes.Repeat([]byte("x"), reviewerReserveCensusMaxBytes), 0600); err != nil {
		t.Fatal(err)
	}
	if raw, err := ReadPrivateFile(path, reviewerReserveCensusMaxBytes); raw != nil || err == nil {
		t.Fatal("reserve reader widened the public private-file ceiling", len(raw), err)
	}
	reader, err := NewReviewerReserveFile(path)
	if err != nil {
		t.Fatal("exact bounded opaque file refused", err)
	}
	if got, err := reader.ReadReviewerReserveCoverage(t.Context()); err != nil || len(got) != reviewerReserveCensusMaxBytes {
		t.Fatal("exact file bound not readable", len(got), err)
	}
}
