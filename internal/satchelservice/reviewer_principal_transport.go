package satchelservice

// This is private service provenance, not a cryptographic Comet proof. Before
// using the client, the operator must independently enroll the actual native
// service/PID, dedicated account, listener and protected bearer. Loopback plus
// a bearer cannot establish that enrollment. The server validates its original
// signed SDK bytes and durable confirmations; the SQL partition verifier still
// refuses confirmed-but-unposted outflows. Both independent reserve reviewers
// must bind the resulting partition SHA before any principal allowance exists.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net"
	"net/http"
	"sort"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
)

const reviewerPrincipalCheckpointPath = "/satchel/v1/custody/principal-checkpoint"
const reviewerPrincipalCheckpointURL = "http://127.0.0.1:8094" + reviewerPrincipalCheckpointPath
const reviewerPrincipalRequestMaxBytes = 1024

type HTTPCustodyPrincipalJournalBackend interface {
	ReadReviewerPrincipalJournal(context.Context, string) (ReviewerPrincipalJournalSnapshot, error)
}

type reviewerPrincipalCheckpointRequest struct {
	Protocol int    `json:"protocol"`
	OwnerID  string `json:"owner_id"`
}
type reviewerPrincipalCheckpointWire struct {
	Protocol      int                           `json:"protocol"`
	Kind          string                        `json:"kind"`
	ChainID       string                        `json:"chain_id"`
	Denom         string                        `json:"denom"`
	Vault         string                        `json:"vault"`
	PolicyDigest  string                        `json:"policy_digest"`
	JournalDigest string                        `json:"journal_digest"`
	OwnerID       string                        `json:"owner_id"`
	ObservedAtMS  int64                         `json:"observed_at_ms"`
	Effects       []reviewerPrincipalEffectWire `json:"effects"`
}
type reviewerPrincipalEffectWire struct {
	OperationID         string `json:"operation_id"`
	Kind                string `json:"kind"`
	OwnerID             string `json:"owner_id"`
	AmountUWolo         string `json:"amount_uwolo"`
	Recipient           string `json:"recipient"`
	Memo                string `json:"memo"`
	OriginalFingerprint string `json:"original_fingerprint"`
	ReservationDigest   string `json:"reservation_digest"`
	FeeUWolo            string `json:"fee_uwolo"`
	Status              string `json:"status"`
	TxHash              string `json:"tx_hash"`
	Height              int64  `json:"height"`
}

func principalCheckpointWire(snapshot ReviewerPrincipalJournalSnapshot) reviewerPrincipalCheckpointWire {
	out := reviewerPrincipalCheckpointWire{Protocol: 1, Kind: "custody_principal_checkpoint", ChainID: "wolo-1", Denom: "uwolo", Vault: snapshot.vault, PolicyDigest: snapshot.policy, JournalDigest: snapshot.digest,
		OwnerID: snapshot.owner, ObservedAtMS: snapshot.observed.UnixMilli(), Effects: make([]reviewerPrincipalEffectWire, 0, len(snapshot.effects))}
	for id, e := range snapshot.effects {
		out.Effects = append(out.Effects, reviewerPrincipalEffectWire{OperationID: id, Kind: e.Kind, OwnerID: e.Owner, AmountUWolo: e.Amount, Recipient: e.Recipient, Memo: e.Memo,
			OriginalFingerprint: e.OriginalFingerprint, ReservationDigest: e.ReservationDigest, FeeUWolo: e.Fee, Status: e.Status, TxHash: e.TxHash, Height: e.Height})
	}
	sort.Slice(out.Effects, func(i, j int) bool { return out.Effects[i].OperationID < out.Effects[j].OperationID })
	return out
}

func validPrincipalCheckpointWire(w reviewerPrincipalCheckpointWire, owner, vault, policy string, completed time.Time) bool {
	if w.Protocol != 1 || w.Kind != "custody_principal_checkpoint" || w.ChainID != "wolo-1" || w.Denom != "uwolo" || !ownerUIDPattern.MatchString(owner) || w.OwnerID != owner ||
		!validAddress(vault) || w.Vault != vault || !validReserveDigest(policy) || w.PolicyDigest != policy || !validReserveDigest(w.JournalDigest) || w.ObservedAtMS <= 0 ||
		completed.IsZero() || w.ObservedAtMS > completed.UnixMilli() || completed.Sub(time.UnixMilli(w.ObservedAtMS)) > 2*time.Second || w.Effects == nil || len(w.Effects) > reviewerPrincipalMaxRows {
		return false
	}
	previous := ""
	for _, e := range w.Effects {
		if e.OperationID <= previous || !ownerUIDPattern.MatchString(e.OwnerID) || !validAddress(e.Recipient) || e.Recipient == vault || !validReserveDigest(e.OriginalFingerprint) || !validReserveDigest(e.ReservationDigest) {
			return false
		}
		previous = e.OperationID
		switch e.Kind {
		case "wager":
			n, err := reviewerAmount(e.AmountUWolo, ProductMaxWagerUWolo, true)
			if !wagerIDs.MatchString(e.OperationID) || !ticketMemo.MatchString(e.Memo) || err != nil || n%1000000 != 0 || !reviewerUnsignedDecimal(e.FeeUWolo, false, reviewerMaxOperationFeeUWolo) {
				return false
			}
		case "withdrawal":
			id := strings.TrimPrefix(e.OperationID, "satchel:withdrawal:")
			if id == e.OperationID || !uuid.MatchString(id) || e.Memo != "aoe2war/satchel/withdraw/v1/"+id || !reviewerUnsignedDecimal(e.AmountUWolo, false, 50000000000) || e.FeeUWolo != "" {
				return false
			}
		default:
			return false
		}
		switch e.Status {
		case "CONFIRMED", "FAILED":
			if !principalTxHash(e.TxHash) || e.Height <= 0 {
				return false
			}
		case "REFUSED":
			if e.TxHash != "" || e.Height != 0 {
				return false
			}
		default:
			return false // UNKNOWN/ACCEPTED/OBSERVED retain the global execution fence.
		}
	}
	return true
}

// The existing private handler must authenticate literal-loopback peers and
// the protected bearer BEFORE dispatching here. This optional read is available
// without granting the service any new signing or reserve capability.
func (h *privateHTTPHandler) custodyPrincipalCheckpoint(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}
	backend, ok := h.backend.(HTTPCustodyPrincipalJournalBackend)
	if !ok {
		httpFailure(w, http.StatusServiceUnavailable, "custody_principal_checkpoint_unavailable")
		return
	}
	media, params, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" || r.Header.Get("Content-Encoding") != "" {
		httpFailure(w, http.StatusUnsupportedMediaType, "invalid_bounded_request")
		return
	}
	for key, value := range params {
		if key != "charset" || !strings.EqualFold(value, "utf-8") {
			httpFailure(w, http.StatusUnsupportedMediaType, "invalid_bounded_request")
			return
		}
	}
	if r.ContentLength > reviewerPrincipalRequestMaxBytes {
		httpFailure(w, http.StatusRequestEntityTooLarge, "invalid_bounded_request")
		return
	}
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, reviewerPrincipalRequestMaxBytes))
	if err != nil {
		status := http.StatusBadRequest
		var limit *http.MaxBytesError
		if errors.As(err, &limit) {
			status = http.StatusRequestEntityTooLarge
		}
		httpFailure(w, status, "invalid_bounded_request")
		return
	}
	var input reviewerPrincipalCheckpointRequest
	fields, object := chainjson.Object(raw)
	if !utf8.Valid(raw) || !chainjson.ValidFolded(raw) || !object || len(fields) != 2 || strictHTTPJSON(raw, &input) != nil || input.Protocol != 1 || !ownerUIDPattern.MatchString(input.OwnerID) {
		httpFailure(w, http.StatusBadRequest, "invalid_principal_checkpoint_request")
		return
	}
	if ctx == nil || ctx.Err() != nil {
		httpFailure(w, http.StatusRequestTimeout, "request_canceled")
		return
	}
	snapshot, err := backend.ReadReviewerPrincipalJournal(ctx, input.OwnerID)
	out := principalCheckpointWire(snapshot)
	if err != nil || ctx.Err() != nil || !snapshot.valid || !validPrincipalCheckpointWire(out, input.OwnerID, h.identity.VaultAddress, snapshot.policy, time.Now()) {
		httpFailure(w, http.StatusConflict, "custody_principal_checkpoint_unverifiable")
		return
	}
	raw, err = json.Marshal(out)
	if err != nil || len(raw) > reviewerPrincipalMaxBytes || ctx.Err() != nil || !validPrincipalCheckpointWire(out, input.OwnerID, h.identity.VaultAddress, snapshot.policy, time.Now()) {
		httpFailure(w, http.StatusConflict, "custody_principal_checkpoint_unverifiable")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(raw)
}

// Only protected operator configuration supplies these three parameters. No
// request URL, key, root, completeness bit, environment proxy or retry policy
// is accepted. The expected policy digest includes both approval public roots.
type ReviewerPrincipalJournalClient struct {
	http                 *http.Client
	token, vault, policy string
	now                  func() time.Time
}

func NewReviewerPrincipalJournalClient(token, vault, policy string) (*ReviewerPrincipalJournalClient, error) {
	if !httpTokenPattern.MatchString(token) || !httpVaultAddress(vault) || !validReserveDigest(policy) {
		return nil, ErrReviewerHeld
	}
	transport := &http.Transport{Proxy: nil, DisableCompression: true, DisableKeepAlives: true, MaxConnsPerHost: 2,
		DialContext: (&net.Dialer{Timeout: 500 * time.Millisecond}).DialContext, ResponseHeaderTimeout: 750 * time.Millisecond}
	return &ReviewerPrincipalJournalClient{http: &http.Client{Transport: transport, Timeout: time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return ErrReviewerHeld }}, token: token, vault: vault, policy: policy, now: time.Now}, nil
}

func (c *ReviewerPrincipalJournalClient) ReadReviewerPrincipalJournal(ctx context.Context, owner string) (ReviewerPrincipalJournalSnapshot, error) {
	bad := func() (ReviewerPrincipalJournalSnapshot, error) {
		return ReviewerPrincipalJournalSnapshot{}, ErrReviewerHeld
	}
	if c == nil || c.http == nil || c.now == nil || ctx == nil || ctx.Err() != nil || !ownerUIDPattern.MatchString(owner) || !httpTokenPattern.MatchString(c.token) || !validAddress(c.vault) || !validReserveDigest(c.policy) {
		return bad()
	}
	started, initial := time.Now(), c.now()
	ctx, cancel := context.WithTimeout(ctx, time.Second)
	defer cancel()
	raw, err := json.Marshal(reviewerPrincipalCheckpointRequest{Protocol: 1, OwnerID: owner})
	if err != nil {
		return bad()
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, reviewerPrincipalCheckpointURL, bytes.NewReader(raw))
	if err != nil {
		return bad()
	}
	request.Header.Set("Authorization", "Bearer "+c.token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		if response != nil && response.Body != nil {
			_ = response.Body.Close()
		}
		return bad()
	}
	defer response.Body.Close()
	media, params, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || media != "application/json" || response.StatusCode != http.StatusOK || response.Header.Get("Content-Encoding") != "" || response.ContentLength > reviewerPrincipalMaxBytes {
		return bad()
	}
	for key, value := range params {
		if key != "charset" || !strings.EqualFold(value, "utf-8") {
			return bad()
		}
	}
	raw, err = io.ReadAll(io.LimitReader(response.Body, reviewerPrincipalMaxBytes+1))
	if err != nil || len(raw) > reviewerPrincipalMaxBytes || ctx.Err() != nil {
		return bad()
	}
	var wire reviewerPrincipalCheckpointWire
	if decodePrincipalCheckpointWire(raw, &wire) != nil {
		return bad()
	}
	completed := c.now()
	if floor := initial.Add(time.Since(started)); floor.After(completed) {
		completed = floor
	}
	if ctx.Err() != nil || !validPrincipalCheckpointWire(wire, owner, c.vault, c.policy, completed) {
		return bad()
	}
	// This flag means authenticated *service provenance*, not bank-proof or
	// cryptographic confirmation authority. The partition consumer still needs
	// its independently queried SQL slice and both reserve-review signatures.
	out := ReviewerPrincipalJournalSnapshot{valid: true, owner: owner, vault: c.vault, policy: c.policy, digest: wire.JournalDigest, observed: time.UnixMilli(wire.ObservedAtMS), effects: make(map[string]reviewerPrincipalEffect, len(wire.Effects))}
	for _, e := range wire.Effects {
		out.effects[e.OperationID] = reviewerPrincipalEffect{Kind: e.Kind, Owner: e.OwnerID, Amount: e.AmountUWolo, Recipient: e.Recipient, Memo: e.Memo,
			OriginalFingerprint: e.OriginalFingerprint, ReservationDigest: e.ReservationDigest, Fee: e.FeeUWolo, Status: e.Status, TxHash: e.TxHash, Height: e.Height}
	}
	finished := c.now()
	if floor := initial.Add(time.Since(started)); floor.After(finished) {
		finished = floor
	}
	if ctx.Err() != nil || !principalJournalCurrent(out, owner, c.vault, c.policy, finished) {
		return bad()
	}
	return out, nil
}
func (c *ReviewerPrincipalJournalClient) Close() {
	if c != nil && c.http != nil {
		c.http.CloseIdleConnections()
	}
}

// Validate each bounded effect separately. The shared folded guard has a
// 100k-node ceiling; applying it to the whole 10k-operation envelope would
// reject a valid full inventory merely because it contains 12 fields per op.
// The top-level decoder checks exact unique names itself, with no map overwrite.
func decodePrincipalCheckpointWire(raw []byte, out *reviewerPrincipalCheckpointWire) error {
	if len(raw) == 0 || len(raw) > reviewerPrincipalMaxBytes || !utf8.Valid(raw) {
		return ErrReviewerHeld
	}
	allowed := map[string]bool{"protocol": true, "kind": true, "chain_id": true, "denom": true, "vault": true, "policy_digest": true, "journal_digest": true, "owner_id": true, "observed_at_ms": true, "effects": true}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return ErrReviewerHeld
	}
	seen := map[string]bool{}
	for decoder.More() {
		token, err = decoder.Token()
		if err != nil {
			return ErrReviewerHeld
		}
		key, ok := token.(string)
		if !ok || !allowed[key] || seen[key] {
			return ErrReviewerHeld
		}
		seen[key] = true
		var value json.RawMessage
		if decoder.Decode(&value) != nil {
			return ErrReviewerHeld
		}
		if key != "effects" {
			if !chainjson.ValidFolded(value) {
				return ErrReviewerHeld
			}
			continue
		}
		if bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
			return ErrReviewerHeld
		}
		var effects []json.RawMessage
		if json.Unmarshal(value, &effects) != nil || len(effects) > reviewerPrincipalMaxRows {
			return ErrReviewerHeld
		}
		for _, effect := range effects {
			fields, ok := chainjson.Object(effect)
			if !ok || len(fields) != 12 || !chainjson.ValidFolded(effect) {
				return ErrReviewerHeld
			}
			var e reviewerPrincipalEffectWire
			if strictHTTPJSON(effect, &e) != nil {
				return ErrReviewerHeld
			}
		}
	}
	if token, err = decoder.Token(); err != nil || token != json.Delim('}') || len(seen) != len(allowed) {
		return ErrReviewerHeld
	}
	if _, err = decoder.Token(); err != io.EOF {
		return ErrReviewerHeld
	}
	if strictHTTPJSON(raw, out) != nil {
		return ErrReviewerHeld
	}
	return nil
}

var _ HTTPCustodyPrincipalJournalBackend = (*Engine)(nil)
var _ ReviewerPrincipalJournalReader = (*ReviewerPrincipalJournalClient)(nil)
