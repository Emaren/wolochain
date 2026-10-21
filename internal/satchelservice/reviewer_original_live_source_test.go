package satchelservice

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type originalHDSourceFixture struct {
	candidate ReviewerWatcherCandidate
	mutate    bool
	calls     int
}

func (s *originalHDSourceFixture) OriginalHold(ctx context.Context, id string) (WagerReservation, error) {
	if ctx.Err() != nil || id != s.candidate.OriginalOperationID {
		return WagerReservation{}, ErrReviewerHeld
	}
	return WagerReservation{OperationID: id, OwnerID: s.candidate.OwnerUID}, nil
}
func (s *originalHDSourceFixture) InspectWatcherMarket(ctx context.Context, _ WagerReservation) (ReviewerWatcherCandidate, error) {
	s.calls++
	c := s.candidate
	if ctx.Err() != nil {
		return c, ErrReviewerHeld
	}
	if s.mutate && s.calls > 1 {
		c.SelectedSide = "right"
	}
	return c, nil
}

type originalAPIFixture struct {
	mu                       sync.Mutex
	record                   originalLiveAPIRecord
	raw                      []byte
	metadataOverride         string
	metadataCalls, byteCalls int
	beforeBytes              func()
	compression              bool
	chunked                  bool
}

func (f *originalAPIFixture) serve(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Authorization") != "Bearer "+strings.Repeat("t", 64) {
		http.Error(w, "private", 401)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if r.URL.Path == "/satchel-source/v1/live" && r.Method == http.MethodPost {
		var request struct {
			Owner   string `json:"owner_uid"`
			Session string `json:"linked_session"`
		}
		if json.NewDecoder(r.Body).Decode(&request) != nil || request.Owner != f.record.OwnerUID || request.Session != f.record.LinkedSession {
			http.Error(w, "unavailable", 503)
			return
		}
		f.metadataCalls++
		w.Header().Set("Content-Type", "application/json")
		if f.compression {
			w.Header().Set("Content-Encoding", "gzip")
		}
		if f.metadataOverride != "" {
			_, _ = io.WriteString(w, f.metadataOverride)
			return
		}
		_ = json.NewEncoder(w).Encode(f.record)
		return
	}
	if r.URL.Path == "/satchel-source/v1/checkpoints/"+f.record.CheckpointSHA256 && r.Method == http.MethodGet {
		f.byteCalls++
		if f.beforeBytes != nil {
			f.beforeBytes()
		}
		w.Header().Set("Content-Type", "application/octet-stream")
		if f.chunked {
			w.WriteHeader(http.StatusOK)
			w.(http.Flusher).Flush()
		}
		_, _ = w.Write(f.raw)
		return
	}
	http.Error(w, "missing", 404)
}
func newOriginalLiveAPITest(t *testing.T) (*ReviewerOriginalLiveSource, *originalAPIFixture, *originalHDSourceFixture, time.Time) {
	t.Helper()
	c, _, _, _, _, now := reviewerLiveCheckpointFixture(t)
	c.GameIdentityKey = "live-original.aoe2mpgame"
	c.LinkedSession = c.GameIdentityKey
	c.OwnerSteamID = "76561198000000001"
	c.SelectedSide = "left"
	raw := []byte("original pre-bet SDK-independent Watcher game-start bytes")
	digest := sha256.Sum256(raw)
	teams := []originalLiveAPITeam{
		{TeamKey: "steam:76561198000000001", PlayerKeys: []string{"steam:76561198000000001"}},
		{TeamKey: "steam:76561198000000002", PlayerKeys: []string{"steam:76561198000000002"}},
	}
	roster, _ := json.Marshal([]string{teams[0].PlayerKeys[0], teams[1].PlayerKeys[0]})
	rosterDigest := sha256.Sum256(roster)
	prop := []byte(`{"format":"1v1","teams":[{"teamKey":"steam:76561198000000001","players":["steam:76561198000000001"]},{"teamKey":"steam:76561198000000002","players":["steam:76561198000000002"]}]}`)
	propDigest := sha256.Sum256(prop)
	c.SourceRosterHash = hex.EncodeToString(rosterDigest[:])
	c.PropositionHash = hex.EncodeToString(propDigest[:])
	f := &originalAPIFixture{raw: raw, record: originalLiveAPIRecord{
		Schema: originalLiveSourceSchema, OriginalAttemptID: 17, OwnerUID: c.OwnerUID, OwnerSteamID: c.OwnerSteamID,
		GameIdentityKey: c.GameIdentityKey, LinkedSession: c.LinkedSession, IdentityAliases: []string{c.GameIdentityKey},
		WatcherID: "original-watcher", WatcherSessionID: "original-watcher-session", SourceParseIteration: c.SourceParseIteration,
		SourceRosterHash: c.SourceRosterHash, PropositionHash: c.PropositionHash, SelectedSide: c.SelectedSide, Teams: teams,
		CheckpointSHA256: hex.EncodeToString(digest[:]), CheckpointSizeBytes: int64(len(raw)),
		CapturedAt: now.Add(-25 * time.Second).UTC().Format(time.RFC3339Nano), ObservedAt: now.Add(-20 * time.Second).UTC().Format(time.RFC3339Nano),
	}}
	server := httptest.NewTLSServer(http.HandlerFunc(f.serve))
	t.Cleanup(server.Close)
	cert := server.Certificate()
	roots := x509.NewCertPool()
	roots.AddCert(cert)
	spki := sha256.Sum256(cert.RawSubjectPublicKeyInfo)
	api, e := NewReviewerOriginalLiveAPIClient(server.URL, strings.Repeat("t", 64), hex.EncodeToString(spki[:]), roots)
	if e != nil {
		t.Fatal(e)
	}
	hd := &originalHDSourceFixture{candidate: c}
	return &ReviewerOriginalLiveSource{origin: hd, api: api, now: func() time.Time { return now }}, f, hd, now
}
func sourceIssuer(t *testing.T, source *ReviewerOriginalLiveSource, now time.Time) *OriginalLiveWitnessIssuer {
	t.Helper()
	_, key, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	wager, _, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	withdrawal, _, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	issuer, e := OpenOriginalLiveWitnessIssuer(filepath.Join(t.TempDir(), "original.db"), source, source, key,
		Policy{WagerApprovalKey: wager, WithdrawalApprovalKey: withdrawal})
	if e != nil {
		t.Fatal(e)
	}
	issuer.now = func() time.Time { return now }
	t.Cleanup(func() { _ = issuer.Close() })
	return issuer
}

func TestOriginalLiveSourceBindsRealTLSTransportToOriginalHDOperation(t *testing.T) {
	s, f, hd, now := newOriginalLiveAPITest(t)
	issuer := sourceIssuer(t, s, now)
	reply := issuer.IssueOne(t.Context(), hd.candidate.OriginalOperationID)
	if reply.Status != "SIGNED" || reply.Witness == nil {
		t.Fatalf("real original API transport did not bind: %+v", reply)
	}
	f.mu.Lock()
	metadataCalls, byteCalls := f.metadataCalls, f.byteCalls
	f.mu.Unlock()
	if metadataCalls != 4 || byteCalls != 2 || hd.calls != 2 {
		t.Fatalf("source boundaries not independently reread: metadata=%d bytes=%d HD=%d", metadataCalls, byteCalls, hd.calls)
	}
	if reply.Witness.LiveCheckpointSHA256 != f.record.CheckpointSHA256 || reply.Witness.OwnerSteamID != f.record.OwnerSteamID || reply.Witness.ExpiresAtMS > now.Add(30*time.Second).UnixMilli() {
		t.Fatal("signed source was substituted or lifetime expanded")
	}
	// Existing issuer journals one fixed source-bound witness; transport cannot
	// refresh its expiry on duplicate operation requests.
	again := issuer.IssueOne(t.Context(), hd.candidate.OriginalOperationID)
	if again.Witness == nil || again.Witness.Signature != reply.Witness.Signature || again.Witness.ExpiresAtMS != reply.Witness.ExpiresAtMS {
		t.Fatal("duplicate renewed witness")
	}
}
func TestOriginalLiveSourceAcceptsGenuineGrowingRecordIdentityWithoutFilenameStageInference(t *testing.T) {
	s, f, hd, now := newOriginalLiveAPITest(t)
	name := "current-growing.aoe2record"
	hd.candidate.GameIdentityKey = name
	hd.candidate.LinkedSession = name
	f.record.GameIdentityKey = name
	f.record.LinkedSession = name
	f.record.IdentityAliases = []string{name}
	if answer := sourceIssuer(t, s, now).IssueOne(t.Context(), hd.candidate.OriginalOperationID); answer.Witness == nil {
		t.Fatal("original LIVE .aoe2record source was mistaken for a finished replay by extension")
	}
}
func TestOriginalLiveSourceRejectsForgedOriginalIdentityTeamsAndClocks(t *testing.T) {
	cases := []string{"uid", "steam", "game", "session", "side", "proposition", "roster", "iteration", "duplicate_alias", "missing_alias", "swapped_teams", "same_player_twice", "forged_team_hash", "postgame", "future", "stale", "financial_authority", "result_authority", "missing_checkpoint", "corrupt_checkpoint", "wrong_size", "extra_chunked", "changed_original", "changed_hd"}
	for _, which := range cases {
		t.Run(which, func(t *testing.T) {
			s, f, hd, now := newOriginalLiveAPITest(t)
			switch which {
			case "uid":
				f.record.OwnerUID = "forged-owner"
			case "steam":
				f.record.OwnerSteamID = "76561198000000002"
			case "game":
				f.record.GameIdentityKey = "other.aoe2mpgame"
			case "session":
				f.record.LinkedSession = "different.aoe2mpgame"
			case "side":
				f.record.SelectedSide = "right"
			case "proposition":
				f.record.PropositionHash = strings.Repeat("a", 64)
			case "roster":
				f.record.SourceRosterHash = strings.Repeat("b", 64)
			case "iteration":
				f.record.SourceParseIteration++
			case "duplicate_alias":
				f.record.IdentityAliases = append(f.record.IdentityAliases, f.record.LinkedSession)
			case "missing_alias":
				f.record.IdentityAliases = []string{"other.aoe2mpgame"}
			case "swapped_teams":
				f.record.Teams[0], f.record.Teams[1] = f.record.Teams[1], f.record.Teams[0]
			case "same_player_twice":
				f.record.Teams[1].PlayerKeys[0] = f.record.Teams[0].PlayerKeys[0]
			case "forged_team_hash":
				f.record.Teams[1].PlayerKeys[0] = "steam:76561198000000003"
			case "postgame":
				f.record.GameIdentityKey = "final.aoe2record"
			case "future":
				f.record.ObservedAt = now.Add(time.Second).Format(time.RFC3339Nano)
			case "stale":
				f.record.ObservedAt = now.Add(-60 * time.Second).Format(time.RFC3339Nano)
			case "financial_authority":
				f.record.FinancialAuthorized = true
			case "result_authority":
				f.record.ResultAuthority = true
			case "missing_checkpoint":
				f.raw = nil
			case "corrupt_checkpoint":
				f.raw[0] = 'X'
			case "wrong_size":
				f.record.CheckpointSizeBytes++
			case "extra_chunked":
				f.chunked = true
				f.raw = append(f.raw, 'X')
			case "changed_original":
				f.beforeBytes = func() { f.record.ObservedAt = now.Add(-19 * time.Second).UTC().Format(time.RFC3339Nano) }
			case "changed_hd":
				hd.mutate = true
			}
			reply := sourceIssuer(t, s, now).IssueOne(t.Context(), hd.candidate.OriginalOperationID)
			if reply.Status != "PENDING" || reply.Witness != nil {
				t.Fatalf("%s obtained authority", which)
			}
		})
	}
}
func TestOriginalLiveSourceConcurrentBodySlotsAreBoundedAndReleased(t *testing.T) {
	s, f, hd, _ := newOriginalLiveAPITest(t)
	var replies []*http.Response
	var releases []context.CancelFunc
	for i := 0; i < 4; i++ {
		r, done, e := s.api.request(t.Context(), "/satchel-source/v1/checkpoints/"+f.record.CheckpointSHA256, nil, "application/octet-stream")
		if e != nil {
			t.Fatal(e)
		}
		replies = append(replies, r)
		releases = append(releases, done)
	}
	if _, e := s.ReadOriginalLiveCapture(t.Context(), hd.candidate.OriginalOperationID); !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("fifth concurrent source I/O admitted")
	}
	for i, r := range replies {
		_ = r.Body.Close()
		releases[i]()
	}
	if len(s.api.slots) != 0 {
		t.Fatal("source body slots leaked")
	}
	if _, e := s.ReadOriginalLiveCapture(t.Context(), hd.candidate.OriginalOperationID); e != nil {
		t.Fatal("released source slots stayed held")
	}
}
func TestOriginalLiveSourceExactJSONAndSizeBounds(t *testing.T) {
	cases := []string{"empty", "duplicate", "case_alias", "extra", "unknown_team_field", "oversize", "compressed"}
	for _, which := range cases {
		t.Run(which, func(t *testing.T) {
			s, f, hd, now := newOriginalLiveAPITest(t)
			raw, _ := json.Marshal(f.record)
			switch which {
			case "empty":
				f.metadataOverride = "{}"
			case "duplicate":
				f.metadataOverride = strings.TrimSuffix(string(raw), "}") + `,"owner_uid":"forged"}`
			case "case_alias":
				f.metadataOverride = strings.Replace(string(raw), `"owner_uid"`, `"OWNER_UID"`, 1)
			case "extra":
				f.metadataOverride = strings.TrimSuffix(string(raw), "}") + `,"complete":true}`
			case "unknown_team_field":
				f.metadataOverride = strings.Replace(string(raw), `"team_key":`, `"self_claimed":true,"team_key":`, 1)
			case "oversize":
				f.metadataOverride = strings.Repeat(" ", int(originalLiveSourceJSONLimit)) + string(raw)
			case "compressed":
				f.compression = true
			}
			if reply := sourceIssuer(t, s, now).IssueOne(t.Context(), hd.candidate.OriginalOperationID); reply.Status != "PENDING" || reply.Witness != nil {
				t.Fatal("unbounded/ambiguous JSON signed")
			}
		})
	}
}
func TestOriginalLiveSourceCannotExpireDuringCheckpointIO(t *testing.T) {
	s, f, hd, now := newOriginalLiveAPITest(t)
	var clock atomic.Int64
	clock.Store(now.UnixNano())
	s.now = func() time.Time { return time.Unix(0, clock.Load()) }
	f.beforeBytes = func() { clock.Store(now.Add(41 * time.Second).UnixNano()) }
	if reply := sourceIssuer(t, s, now).IssueOne(t.Context(), hd.candidate.OriginalOperationID); reply.Status != "PENDING" || reply.Witness != nil {
		t.Fatal("expired original evidence signed after I/O")
	}
}
func TestOriginalLiveSourceDoesNotTrustBearerOrEndpointWithoutPinnedServer(t *testing.T) {
	s, _, hd, _ := newOriginalLiveAPITest(t)
	wrong, e := NewReviewerOriginalLiveAPIClient(s.api.endpoint, s.api.token, strings.Repeat("a", 64), s.api.http.Transport.(*http.Transport).TLSClientConfig.RootCAs)
	if e != nil {
		t.Fatal(e)
	}
	s.api = wrong
	if _, e := s.ReadOriginalLiveCapture(t.Context(), hd.candidate.OriginalOperationID); !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("untrusted TLS source accepted")
	}
	for _, endpoint := range []string{"http://127.0.0.1:4000", "https://user:pass@host", "https://host/path", "https://host?caller=source", "https://host/#fragment"} {
		if _, e := NewReviewerOriginalLiveAPIClient(endpoint, strings.Repeat("t", 64), strings.Repeat("a", 64), x509.NewCertPool()); !errors.Is(e, ErrReviewerHeld) {
			t.Fatalf("untrusted endpoint accepted: %s", endpoint)
		}
	}
}
func TestOriginalLiveSourceCanceledAndPartialReadsCannotAuthenticate(t *testing.T) {
	s, _, hd, _ := newOriginalLiveAPITest(t)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, e := s.ReadOriginalLiveCapture(ctx, hd.candidate.OriginalOperationID); !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("canceled source returned capture")
	}
	body, e := s.OpenAuthenticatedLiveCheckpoint(t.Context(), hd.candidate)
	if e != nil {
		t.Fatal(e)
	}
	if e = body.Close(); !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("unread checkpoint authenticated")
	}
	if len(s.api.slots) != 0 {
		t.Fatal("partial read leaked source slot")
	}
}
