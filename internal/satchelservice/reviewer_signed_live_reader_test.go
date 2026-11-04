package satchelservice

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type reviewerSignedLiveHTTPFixture struct {
	reader   *ReviewerSignedLiveReader
	calls    atomic.Int32
	bad      atomic.Bool
	clock    atomic.Int64
	body     string
	media    string
	encoding string
	status   int
	chunked  bool
	after    func()
}

func newReviewerSignedLiveHTTPFixture(t *testing.T, witness ReviewerWatcherLiveWitness, now time.Time, trust string) *reviewerSignedLiveHTTPFixture {
	t.Helper()
	raw, err := json.Marshal(OriginalLiveWitnessReply{Status: "SIGNED", OperationID: witness.OperationID, Witness: &witness})
	if err != nil {
		t.Fatal(err)
	}
	f := &reviewerSignedLiveHTTPFixture{body: string(raw), media: "application/json", status: http.StatusOK}
	f.clock.Store(now.UnixNano())
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.calls.Add(1)
		body, err := io.ReadAll(io.LimitReader(r.Body, 1024))
		request, _ := json.Marshal(struct {
			OperationID string `json:"operation_id"`
		}{witness.OperationID})
		if err != nil || string(body) != string(request) || r.Method != http.MethodPost || r.URL.Path != reviewerSignedLivePath || r.URL.RawQuery != "" ||
			r.Header.Get("Content-Type") != "application/json" || r.Header.Get("Accept") != "application/json" {
			f.bad.Store(true)
			http.Error(w, "unexpected request", http.StatusBadRequest)
			return
		}
		if r.Header.Get("Authorization") != "Bearer "+strings.Repeat("t", 64) {
			http.Error(w, "private authentication required", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", f.media)
		if f.encoding != "" {
			w.Header().Set("Content-Encoding", f.encoding)
		}
		if f.status == http.StatusTemporaryRedirect {
			w.Header().Set("Location", "/caller-selected-witness")
		}
		w.WriteHeader(f.status)
		if f.chunked {
			w.(http.Flusher).Flush()
		}
		if f.after != nil {
			f.after()
		}
		_, _ = io.WriteString(w, f.body)
	}))
	t.Cleanup(server.Close)
	roots := x509.NewCertPool()
	if trust != "wrong_ca" {
		roots.AddCert(server.Certificate())
	}
	spki := sha256.Sum256(server.Certificate().RawSubjectPublicKeyInfo)
	pin, token := hex.EncodeToString(spki[:]), strings.Repeat("t", 64)
	if trust == "wrong_spki" {
		pin = strings.Repeat("a", 64)
	}
	if trust == "wrong_bearer" {
		token = strings.Repeat("x", 64)
	}
	api, err := NewReviewerOriginalLiveAPIClient(server.URL, token, pin, roots)
	if err != nil {
		t.Fatal(err)
	}
	f.reader, err = NewReviewerSignedLiveReader(api)
	if err != nil {
		t.Fatal(err)
	}
	f.reader.now = func() time.Time { return time.Unix(0, f.clock.Load()) }
	return f
}

func TestReviewerSignedLiveReaderUsesPinnedTLSAndExistingIndependentVerifier(t *testing.T) {
	candidate, source, checkpoint, public, _, now := reviewerLiveCheckpointFixture(t)
	f := newReviewerSignedLiveHTTPFixture(t, source.original, now, "")
	got, err := f.reader.FetchOriginalLiveWitness(t.Context(), candidate.OriginalOperationID)
	if err != nil || got != source.original {
		t.Fatalf("original signed witness changed over pinned TLS: %v", err)
	}
	if err := VerifyIndependentReviewerLiveWatcher(t.Context(), candidate, f.reader, checkpoint, public, now); err != nil {
		t.Fatalf("independent signature/checkpoint verification refused actual transport: %v", err)
	}
	if f.bad.Load() || f.calls.Load() != 2 || checkpoint.calls != 1 || got.ExpiresAtMS != source.original.ExpiresAtMS {
		t.Fatal("request contract, independent checkpoint read or original expiry changed")
	}
}

func TestReviewerSignedLiveReaderRejectsUntrustedTransportAndResponse(t *testing.T) {
	for _, name := range []string{"wrong_spki", "wrong_ca", "wrong_bearer", "redirect", "wrong_media", "compressed", "oversize", "chunked_oversize", "truncated", "duplicate", "case_folded", "unknown_authority", "unknown_witness_field", "missing_field", "wrong_operation", "wrong_protocol", "pending", "future", "expired", "oversized_window", "expired_during_read", "canceled_during_read", "invalid_utf8"} {
		t.Run(name, func(t *testing.T) {
			candidate, source, _, _, _, now := reviewerLiveCheckpointFixture(t)
			f := newReviewerSignedLiveHTTPFixture(t, source.original, now, name)
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			switch name {
			case "redirect":
				f.status = http.StatusTemporaryRedirect
			case "wrong_media":
				f.media = "text/plain"
			case "compressed":
				f.encoding = "gzip"
			case "oversize", "chunked_oversize":
				f.body += strings.Repeat(" ", int(reviewerSignedLiveJSONLimit))
				f.chunked = name == "chunked_oversize"
			case "truncated":
				f.body = f.body[:len(f.body)-1]
			case "duplicate":
				f.body = `{"status":"SIGNED",` + f.body[1:]
			case "case_folded":
				f.body = strings.Replace(f.body, `"status"`, `"Status"`, 1)
			case "unknown_authority":
				f.body = `{"endpoint":"https://caller.invalid","public_key":"caller-key",` + f.body[1:]
			case "unknown_witness_field":
				f.body = strings.Replace(f.body, `"witness":{`, `"witness":{"financial_authorized":true,`, 1)
			case "missing_field":
				f.body = strings.Replace(f.body, `"version":2,`, "", 1)
			case "wrong_operation":
				f.body = strings.ReplaceAll(f.body, candidate.OriginalOperationID, "satchel:ticket:999999999999")
			case "wrong_protocol":
				f.body = strings.Replace(f.body, `"version":2`, `"version":1`, 1)
			case "pending":
				f.body = strings.Replace(f.body, `"SIGNED"`, `"PENDING"`, 1)
			case "future", "expired", "oversized_window":
				witness := source.original
				if name == "future" {
					witness.ObservedAtMS = now.Add(time.Second).UnixMilli()
				} else if name == "expired" {
					witness.ExpiresAtMS = now.UnixMilli()
				} else {
					witness.ExpiresAtMS = witness.ObservedAtMS + 60001
				}
				raw, err := json.Marshal(OriginalLiveWitnessReply{Status: "SIGNED", OperationID: candidate.OriginalOperationID, Witness: &witness})
				if err != nil {
					t.Fatal(err)
				}
				f.body = string(raw)
			case "expired_during_read":
				f.chunked = true
				f.after = func() { f.clock.Store(now.Add(time.Minute).UnixNano()) }
			case "canceled_during_read":
				f.chunked = true
				f.after = cancel
			case "invalid_utf8":
				f.body = strings.Replace(f.body, candidate.OwnerUID, string([]byte{0xff}), 1)
			}
			if _, err := f.reader.FetchOriginalLiveWitness(ctx, candidate.OriginalOperationID); !errors.Is(err, ErrReviewerHeld) {
				t.Fatalf("unsafe witness transport admitted: %v", err)
			}
			if f.bad.Load() || f.calls.Load() > 1 {
				t.Fatal("caller-selected route or retry reached source")
			}
		})
	}
}

func TestReviewerSignedLiveReaderCannotReplaceEnrolledKeyOwnerOrCheckpoint(t *testing.T) {
	for _, name := range []string{"wrong_key", "wrong_owner", "wrong_checkpoint", "forged_signature"} {
		t.Run(name, func(t *testing.T) {
			candidate, source, checkpoint, public, private, now := reviewerLiveCheckpointFixture(t)
			switch name {
			case "wrong_key":
				public = ed25519.PublicKey(make([]byte, ed25519.PublicKeySize))
			case "wrong_owner":
				source.original.OwnerUID = "another_owner"
				source.original.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(private, ReviewerWatcherLiveWitnessMessage(source.original)))
			case "wrong_checkpoint":
				checkpoint.data = []byte("different immutable original checkpoint")
			case "forged_signature":
				source.original.Signature = base64.StdEncoding.EncodeToString(make([]byte, ed25519.SignatureSize))
			}
			f := newReviewerSignedLiveHTTPFixture(t, source.original, now, "")
			if _, err := f.reader.FetchOriginalLiveWitness(t.Context(), candidate.OriginalOperationID); err != nil {
				t.Fatalf("transport unexpectedly replaced independent verification: %v", err)
			}
			if err := VerifyIndependentReviewerLiveWatcher(t.Context(), candidate, f.reader, checkpoint, public, now); !errors.Is(err, ErrReviewerHeld) {
				t.Fatalf("transport replaced enrolled owner/key/checkpoint authority: %v", err)
			}
		})
	}
}

func TestReviewerSignedLiveReaderRejectsCallerRoutesAndCanceledContexts(t *testing.T) {
	_, source, _, _, _, now := reviewerLiveCheckpointFixture(t)
	f := newReviewerSignedLiveHTTPFixture(t, source.original, now, "")
	for _, id := range []string{"", "satchel:ticket:0", "satchel:ticket:01", "satchel:ticket:1/../../authority", "https://caller.invalid", "satchel:ticket:1234567890123"} {
		if _, err := f.reader.FetchOriginalLiveWitness(t.Context(), id); !errors.Is(err, ErrReviewerHeld) {
			t.Fatalf("noncanonical operation accepted: %q", id)
		}
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	for _, c := range []context.Context{nil, ctx} {
		if _, err := f.reader.FetchOriginalLiveWitness(c, source.original.OperationID); !errors.Is(err, ErrReviewerHeld) {
			t.Fatal("invalid context reached source")
		}
	}
	if f.calls.Load() != 0 {
		t.Fatal("invalid request contacted external source")
	}
	if _, err := NewReviewerSignedLiveReader(nil); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("missing pinned transport accepted")
	}
}
