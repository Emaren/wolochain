package satchelservice

// Original LIVE source transport and HD-operation binding. The API process
// must be separately governed, SELECT-only, and read the immutable original
// upload/archive. TLS authenticates that configured process; it does not
// certify its operator, database permissions, archive, or financial solvency.
// Neither HTTP caller parameters nor HD's own market JSON are source truth.
import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const originalLiveSourceSchema = "aoe2war-satchel-original-live-source/v1"
const originalLiveSourceJSONLimit int64 = 32 << 10

type originalLiveAPITeam struct {
	TeamKey    string   `json:"team_key"`
	PlayerKeys []string `json:"player_keys"`
}
type originalLiveAPIRecord struct {
	Schema               string                `json:"schema"`
	OriginalAttemptID    int64                 `json:"original_attempt_id"`
	OwnerUID             string                `json:"owner_uid"`
	OwnerSteamID         string                `json:"owner_steam_id"`
	GameIdentityKey      string                `json:"game_identity_key"`
	LinkedSession        string                `json:"linked_session"`
	IdentityAliases      []string              `json:"identity_aliases"`
	WatcherID            string                `json:"watcher_id"`
	WatcherSessionID     string                `json:"watcher_session_id"`
	SourceParseIteration int64                 `json:"source_parse_iteration"`
	SourceRosterHash     string                `json:"source_roster_hash"`
	PropositionHash      string                `json:"proposition_hash"`
	SelectedSide         string                `json:"selected_side"`
	Teams                []originalLiveAPITeam `json:"teams"`
	CheckpointSHA256     string                `json:"checkpoint_sha256"`
	CheckpointSizeBytes  int64                 `json:"checkpoint_size_bytes"`
	CapturedAt           string                `json:"captured_at"`
	ObservedAt           string                `json:"observed_at"`
	FinancialAuthorized  bool                  `json:"financial_authorized"`
	ResultAuthority      bool                  `json:"result_authority"`
}

// ReviewerOriginalLiveAPIClient has no signing or financial capability.
// endpoint, trust roots, SPKI digest and bearer are operator-pinned inputs,
// never fields obtained from a wager, metadata response or browser request.
type ReviewerOriginalLiveAPIClient struct {
	endpoint string
	token    string
	http     *http.Client
	slots    chan struct{}
}

func NewReviewerOriginalLiveAPIClient(endpoint, token, serverSPKISHA256 string, roots *x509.CertPool) (*ReviewerOriginalLiveAPIClient, error) {
	u, e := url.Parse(endpoint)
	if e != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.Path != "" || u.RawPath != "" || u.RawQuery != "" || u.Fragment != "" || u.Opaque != "" ||
		!httpTokenPattern.MatchString(token) || !reviewerHexDigest.MatchString(serverSPKISHA256) || serverSPKISHA256 == strings.Repeat("0", 64) || roots == nil {
		return nil, ErrReviewerHeld
	}
	transport := &http.Transport{
		Proxy: nil, DisableCompression: true, DisableKeepAlives: true, MaxConnsPerHost: 4,
		DialContext:         (&net.Dialer{Timeout: 500 * time.Millisecond}).DialContext,
		TLSHandshakeTimeout: 750 * time.Millisecond, ResponseHeaderTimeout: time.Second,
		TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS13, RootCAs: roots.Clone(),
			VerifyConnection: func(state tls.ConnectionState) error {
				if len(state.VerifiedChains) == 0 || len(state.PeerCertificates) == 0 {
					return ErrReviewerHeld
				}
				digest := sha256.Sum256(state.PeerCertificates[0].RawSubjectPublicKeyInfo)
				if hex.EncodeToString(digest[:]) != serverSPKISHA256 {
					return ErrReviewerHeld
				}
				return nil
			}},
	}
	client := &http.Client{Transport: transport, Timeout: 2 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return ErrReviewerHeld }}
	return &ReviewerOriginalLiveAPIClient{endpoint: endpoint, token: token, http: client, slots: make(chan struct{}, 4)}, nil
}

func (s *ReviewerOriginalLiveAPIClient) request(ctx context.Context, path string, body []byte, media string) (*http.Response, context.CancelFunc, error) {
	if s == nil || s.http == nil || ctx == nil || ctx.Err() != nil {
		return nil, nil, ErrReviewerHeld
	}
	select {
	case s.slots <- struct{}{}:
	default:
		return nil, nil, ErrReviewerHeld
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	var once sync.Once
	done := func() { once.Do(func() { cancel(); <-s.slots }) }
	method := http.MethodGet
	var input io.Reader
	if body != nil {
		method = http.MethodPost
		input = strings.NewReader(string(body))
	}
	req, e := http.NewRequestWithContext(ctx, method, s.endpoint+path, input)
	if e != nil {
		done()
		return nil, nil, ErrReviewerHeld
	}
	req.Header.Set("Authorization", "Bearer "+s.token)
	req.Header.Set("Accept", media)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	r, e := s.http.Do(req)
	if e != nil {
		done()
		return nil, nil, ErrReviewerHeld
	}
	actual, _, e := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if r.StatusCode != http.StatusOK || e != nil || actual != media || r.Header.Get("Content-Encoding") != "" || r.ContentLength < -1 {
		_ = r.Body.Close()
		done()
		return nil, nil, ErrReviewerHeld
	}
	return r, done, nil
}

func (s *ReviewerOriginalLiveAPIClient) original(ctx context.Context, owner, session string) (originalLiveAPIRecord, error) {
	var record originalLiveAPIRecord
	if !ownerUIDPattern.MatchString(owner) || session == "" || len(session) > 255 {
		return record, ErrReviewerHeld
	}
	request, _ := json.Marshal(struct {
		Owner   string `json:"owner_uid"`
		Session string `json:"linked_session"`
	}{owner, session})
	r, done, e := s.request(ctx, "/satchel-source/v1/live", request, "application/json")
	if e != nil {
		return record, ErrReviewerHeld
	}
	defer done()
	defer r.Body.Close()
	if r.ContentLength > originalLiveSourceJSONLimit {
		return record, ErrReviewerHeld
	}
	raw, e := io.ReadAll(io.LimitReader(r.Body, originalLiveSourceJSONLimit+1))
	if e != nil || len(raw) == 0 || int64(len(raw)) > originalLiveSourceJSONLimit || ctx.Err() != nil {
		return record, ErrReviewerHeld
	}
	value, e := reviewerStrictJSON(raw)
	object, ok := value.(map[string]any)
	if e != nil || !ok || !reviewerRecord(object, []string{"schema", "original_attempt_id", "owner_uid", "owner_steam_id", "game_identity_key", "linked_session", "identity_aliases", "watcher_id", "watcher_session_id", "source_parse_iteration", "source_roster_hash", "proposition_hash", "selected_side", "teams", "checkpoint_sha256", "checkpoint_size_bytes", "captured_at", "observed_at", "financial_authorized", "result_authority"}) {
		return record, ErrReviewerHeld
	}
	teams, ok := object["teams"].([]any)
	if !ok || len(teams) != 2 {
		return record, ErrReviewerHeld
	}
	for _, team := range teams {
		row, ok := team.(map[string]any)
		if !ok || !reviewerRecord(row, []string{"team_key", "player_keys"}) {
			return record, ErrReviewerHeld
		}
	}
	if json.Unmarshal(raw, &record) != nil {
		return originalLiveAPIRecord{}, ErrReviewerHeld
	}
	return record, nil
}

// The public constructor accepts the concrete role-checking HD reader. The
// private interface only permits deterministic fault injection in tests.
type originalLiveHDReader interface {
	OriginalHold(context.Context, string) (WagerReservation, error)
	InspectWatcherMarket(context.Context, WagerReservation) (ReviewerWatcherCandidate, error)
}
type ReviewerOriginalLiveSource struct {
	origin originalLiveHDReader
	api    *ReviewerOriginalLiveAPIClient
	now    func() time.Time
}

func NewReviewerOriginalLiveSource(pg *ReviewerReadOnlyPGSource, api *ReviewerOriginalLiveAPIClient) (*ReviewerOriginalLiveSource, error) {
	if pg == nil || pg.db == nil || api == nil || api.http == nil {
		return nil, ErrReviewerHeld
	}
	return &ReviewerOriginalLiveSource{origin: pg, api: api, now: time.Now}, nil
}

func originalLiveValidIdentity(s string) bool {
	return s != "" && len(s) <= 255 && strings.TrimSpace(s) == s && !strings.ContainsAny(s, "\x00\r\n")
}
func originalLiveTeamLess(a, b string) bool {
	x, xe := strconv.ParseInt(a, 10, 64)
	y, ye := strconv.ParseInt(b, 10, 64)
	if xe == nil && ye == nil {
		return x < y
	}
	return a < b
}
func (r originalLiveAPIRecord) bind(c ReviewerWatcherCandidate, now time.Time) (OriginalLiveCapture, error) {
	held := func() (OriginalLiveCapture, error) { return OriginalLiveCapture{}, ErrReviewerHeld }
	if now.IsZero() || r.Schema != originalLiveSourceSchema || r.OriginalAttemptID < 1 || r.FinancialAuthorized || r.ResultAuthority ||
		r.OwnerUID != c.OwnerUID || r.OwnerSteamID != c.OwnerSteamID || !originalLiveSteamID.MatchString(r.OwnerSteamID) ||
		r.GameIdentityKey != c.GameIdentityKey || r.LinkedSession != c.LinkedSession ||
		!originalLiveValidIdentity(r.GameIdentityKey) || !originalLiveValidIdentity(r.LinkedSession) ||
		!originalLiveValidIdentity(r.WatcherID) || !originalLiveValidIdentity(r.WatcherSessionID) ||
		r.SourceParseIteration < 1 || r.SourceParseIteration != c.SourceParseIteration ||
		r.SourceRosterHash != c.SourceRosterHash || r.PropositionHash != c.PropositionHash ||
		!reviewerHexDigest.MatchString(r.SourceRosterHash) || !reviewerHexDigest.MatchString(r.PropositionHash) ||
		!reviewerHexDigest.MatchString(r.CheckpointSHA256) || r.CheckpointSizeBytes < 1 || r.CheckpointSizeBytes > reviewerMaxLiveCheckpointBytes ||
		r.SelectedSide != c.SelectedSide || (r.SelectedSide != "left" && r.SelectedSide != "right") ||
		len(r.IdentityAliases) < 1 || len(r.IdentityAliases) > 8 || len(r.Teams) != 2 {
		return held()
	}
	aliases := map[string]bool{}
	for _, alias := range r.IdentityAliases {
		if !originalLiveValidIdentity(alias) || aliases[alias] {
			return held()
		}
		aliases[alias] = true
	}
	if !aliases[r.GameIdentityKey] || !aliases[r.LinkedSession] {
		return held()
	}
	// Original files/platform IDs only. Merged or inferred HD aliases are not
	// independently proven by this V1 source and remain unavailable.
	// Watcher's actual growing LIVE transport can be .aoe2record. Its suffix
	// is never proof of stage: the pinned source contract must independently
	// validate ORIGINAL nonfinal live_monitor capture and bounded game elapsed.
	// Re-parsing the AoE2 protocol here would create a competing authority.
	name := strings.ToLower(r.GameIdentityKey)
	if !strings.HasPrefix(r.GameIdentityKey, "platform:") && !strings.HasSuffix(name, ".aoe2mpgame") && !strings.HasSuffix(name, ".aoe2record") {
		return held()
	}
	all := []string{}
	seen := map[string]bool{}
	ownSide := ""
	type propositionTeam struct {
		TeamKey string   `json:"teamKey"`
		Players []string `json:"players"`
	}
	proposition := struct {
		Format string            `json:"format"`
		Teams  []propositionTeam `json:"teams"`
	}{
		Format: strconv.Itoa(len(r.Teams[0].PlayerKeys)) + "v" + strconv.Itoa(len(r.Teams[1].PlayerKeys)), Teams: []propositionTeam{},
	}
	total := len(r.Teams[0].PlayerKeys) + len(r.Teams[1].PlayerKeys)
	for i, team := range r.Teams {
		if len(team.PlayerKeys) < 1 || len(team.PlayerKeys) > 4 || !originalLiveValidIdentity(team.TeamKey) || (i == 1 && !originalLiveTeamLess(r.Teams[0].TeamKey, team.TeamKey)) {
			return held()
		}
		if total == 2 {
			if team.TeamKey != team.PlayerKeys[0] {
				return held()
			}
		} else if strings.HasPrefix(team.TeamKey, "solo:") {
			if len(team.PlayerKeys) != 1 || team.TeamKey != "solo:"+team.PlayerKeys[0] || len(r.Teams[1-i].PlayerKeys) < 2 {
				return held()
			}
		} else {
			n, e := strconv.ParseInt(team.TeamKey, 10, 32)
			if e != nil || n < 0 || n > 9 || strconv.FormatInt(n, 10) != team.TeamKey {
				return held()
			}
		}
		previous := ""
		for _, key := range team.PlayerKeys {
			if !strings.HasPrefix(key, "steam:") || !originalLiveSteamID.MatchString(strings.TrimPrefix(key, "steam:")) || seen[key] || (previous != "" && previous >= key) {
				return held()
			}
			seen[key] = true
			previous = key
			all = append(all, key)
			if key == "steam:"+r.OwnerSteamID {
				if i == 0 {
					ownSide = "left"
				} else {
					ownSide = "right"
				}
			}
		}
		proposition.Teams = append(proposition.Teams, propositionTeam{team.TeamKey, team.PlayerKeys})
	}
	if ownSide != r.SelectedSide {
		return held()
	}
	// These are the existing HD teamResolution JSON domains. The original API
	// parser supplies real teams; Go independently checks their exact hashes.
	sort.Strings(all)
	encoded, _ := json.Marshal(all)
	roster := sha256.Sum256(encoded)
	encoded, _ = json.Marshal(proposition)
	prop := sha256.Sum256(encoded)
	if hex.EncodeToString(roster[:]) != r.SourceRosterHash || hex.EncodeToString(prop[:]) != r.PropositionHash {
		return held()
	}
	captured, e := time.Parse(time.RFC3339Nano, r.CapturedAt)
	if e != nil {
		return held()
	}
	observed, e := time.Parse(time.RFC3339Nano, r.ObservedAt)
	if e != nil {
		return held()
	}
	if captured.After(observed) || observed.After(now) || now.Sub(observed) >= 60*time.Second {
		return held()
	}
	result := OriginalLiveCapture{Candidate: c, CapturedAt: captured, ObservedAt: observed, CheckpointSHA256: r.CheckpointSHA256}
	if _, e = captureToWitness(result, now); e != nil {
		return held()
	}
	return result, nil
}

func (s *ReviewerOriginalLiveSource) ReadOriginalLiveCapture(ctx context.Context, id string) (OriginalLiveCapture, error) {
	if s == nil || s.origin == nil || s.api == nil || s.now == nil || ctx == nil || ctx.Err() != nil || !wagerIDs.MatchString(id) {
		return OriginalLiveCapture{}, ErrReviewerHeld
	}
	hold, e := s.origin.OriginalHold(ctx, id)
	if e != nil || hold.OperationID != id {
		return OriginalLiveCapture{}, ErrReviewerHeld
	}
	c, e := s.origin.InspectWatcherMarket(ctx, hold)
	if e != nil || c.OriginalOperationID != id {
		return OriginalLiveCapture{}, ErrReviewerHeld
	}
	r, e := s.api.original(ctx, c.OwnerUID, c.LinkedSession)
	if e != nil || ctx.Err() != nil {
		return OriginalLiveCapture{}, ErrReviewerHeld
	}
	return r.bind(c, s.now())
}

type originalLiveCheckpointBody struct {
	body           io.ReadCloser
	done           context.CancelFunc
	ctx            context.Context
	now            func() time.Time
	observed       time.Time
	expectedSize   int64
	expectedDigest string
	read           int64
	hash           interface {
		Write([]byte) (int, error)
		Sum([]byte) []byte
	}
	once     sync.Once
	closeErr error
}

func (r *originalLiveCheckpointBody) Read(p []byte) (int, error) {
	if r.ctx.Err() != nil || r.read > r.expectedSize {
		return 0, ErrReviewerHeld
	}
	if int64(len(p)) > r.expectedSize-r.read+1 {
		p = p[:r.expectedSize-r.read+1]
	}
	n, e := r.body.Read(p)
	r.read += int64(n)
	_, _ = r.hash.Write(p[:n])
	if r.read > r.expectedSize || r.ctx.Err() != nil || r.now().Sub(r.observed) >= 60*time.Second {
		return n, ErrReviewerHeld
	}
	return n, e
}
func (r *originalLiveCheckpointBody) Close() error {
	r.once.Do(func() {
		e := r.body.Close()
		now := r.now()
		if e != nil || r.ctx.Err() != nil || r.read != r.expectedSize || hex.EncodeToString(r.hash.Sum(nil)) != r.expectedDigest || now.Before(r.observed) || now.Sub(r.observed) >= 60*time.Second {
			r.closeErr = ErrReviewerHeld
		}
		r.done()
	})
	return r.closeErr
}
func (s *ReviewerOriginalLiveSource) OpenAuthenticatedLiveCheckpoint(ctx context.Context, c ReviewerWatcherCandidate) (io.ReadCloser, error) {
	if s == nil || s.api == nil || s.now == nil || ctx == nil || ctx.Err() != nil {
		return nil, ErrReviewerHeld
	}
	r, e := s.api.original(ctx, c.OwnerUID, c.LinkedSession)
	if e != nil {
		return nil, ErrReviewerHeld
	}
	bound, e := r.bind(c, s.now())
	if e != nil {
		return nil, ErrReviewerHeld
	}
	response, done, e := s.api.request(ctx, "/satchel-source/v1/checkpoints/"+r.CheckpointSHA256, nil, "application/octet-stream")
	if e != nil {
		return nil, ErrReviewerHeld
	}
	if response.ContentLength >= 0 && response.ContentLength != r.CheckpointSizeBytes {
		_ = response.Body.Close()
		done()
		return nil, ErrReviewerHeld
	}
	return &originalLiveCheckpointBody{body: response.Body, done: done, ctx: response.Request.Context(), now: s.now, observed: bound.ObservedAt,
		expectedSize: r.CheckpointSizeBytes, expectedDigest: r.CheckpointSHA256, hash: sha256.New()}, nil
}

var _ OriginalLiveCaptureSource = (*ReviewerOriginalLiveSource)(nil)
var _ ReviewerIndependentLiveCheckpointReader = (*ReviewerOriginalLiveSource)(nil)
