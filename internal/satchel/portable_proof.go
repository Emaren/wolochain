package satchel

// Portable proofs are transcripts, not signer assertions. Verification replays
// the existing strict chain reader and CometBFT light client without network I/O.
// The recipient must provision its own reviewed trust anchor. A proof cannot
// supply, replace, refresh or certify that trust root.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
)

const (
	PortableProofVersion  = 1
	MaxPortableProofBytes = (14 << 20) + (128 << 10)
	maxProofResponses     = 80
	maxProofBodyBytes     = 14 << 20 // C3 collection 6 MiB + light-client 8 MiB
)

// PortableProof deliberately contains no trust anchor, source URL, ownership
// approval, ledger credit or custody-readiness assertion. Response source names
// identify transcript roles; they do not prove independent endpoint operators.
type PortableProof struct {
	Version   int             `json:"version"`
	ChainID   string          `json:"chain_id"`
	Kind      string          `json:"kind"`
	TxHash    string          `json:"tx_hash"`
	Responses []ProofResponse `json:"responses"`
}

type ProofResponse struct {
	Source string          `json:"source"`
	Path   string          `json:"path"`
	Query  string          `json:"query"`
	Body   json.RawMessage `json:"body"`
}

// DecodePortableProof is the bounded strict wire decoder. Callers must also
// bound their HTTP envelope before allocating it. Authority comes only from a
// subsequent verification against an independently configured trust anchor.
func DecodePortableProof(data []byte) (PortableProof, error) {
	if len(data) == 0 || len(data) > MaxPortableProofBytes || !chainjson.ValidFolded(data) {
		return PortableProof{}, fail(InvalidResponse, "proof", "encoding")
	}
	var p PortableProof
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&p) != nil {
		return PortableProof{}, fail(InvalidResponse, "proof", "encoding")
	}
	if _, err := copyProof(p, p.Kind, p.TxHash); err != nil {
		return PortableProof{}, err
	}
	return p, nil
}

type proofRecorder struct {
	mu        sync.Mutex
	responses []ProofResponse
	bytes     int
}

func (p *proofRecorder) add(source, path, query string, body []byte) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if len(p.responses) >= maxProofResponses || len(body) > maxResponseBytes || len(body) > maxProofBodyBytes-p.bytes {
		return fail(ResponseTooLarge, "proof", "capture")
	}
	p.bytes += len(body)
	p.responses = append(p.responses, ProofResponse{source, path, query, append(json.RawMessage(nil), body...)})
	return nil
}

func (p *proofRecorder) snapshot() []ProofResponse {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]ProofResponse(nil), p.responses...)
}

func (r *TrustedReader) ReadDepositProof(ctx context.Context, intent Intent, hash string) (AuthenticatedEvidence, PortableProof, error) {
	evidence, proof, err := r.readProof(ctx, "deposit", hash, func(ctx context.Context, reader *TrustedReader) (AuthenticatedEvidence, error) {
		return reader.ReadDeposit(ctx, intent, hash)
	})
	if err == nil && !validIntent(intent, r.reader.now()) {
		return AuthenticatedEvidence{}, PortableProof{}, fail(InvalidIntent, "intent", "proof_complete")
	}
	return evidence, proof, err
}

func (r *TrustedReader) ReadTransferProof(ctx context.Context, intent TransferIntent, hash string) (AuthenticatedEvidence, PortableProof, error) {
	return r.readProof(ctx, "transfer", hash, func(ctx context.Context, reader *TrustedReader) (AuthenticatedEvidence, error) {
		return reader.ReadTransfer(ctx, intent, hash)
	})
}

func (r *TrustedReader) readProof(ctx context.Context, kind, hash string, collect func(context.Context, *TrustedReader) (AuthenticatedEvidence, error)) (AuthenticatedEvidence, PortableProof, error) {
	if r == nil || r.reader == nil {
		return AuthenticatedEvidence{}, PortableProof{}, fail(InvalidConfiguration, "proof", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	// A private copy shares the fixed, read-only client and the authentication
	// gate, never mutating the live reader, transport or source configuration.
	recorder := &proofRecorder{}
	reader := *r.reader
	reader.proof = recorder
	isolated := &TrustedReader{reader: &reader, anchor: r.anchor, gate: r.gate}
	evidence, err := collect(ctx, isolated)
	if err != nil {
		return AuthenticatedEvidence{}, PortableProof{}, err
	}
	proof, err := copyProof(PortableProof{PortableProofVersion, ChainID, kind, strings.ToUpper(hash), recorder.snapshot()}, kind, hash)
	if err != nil {
		return AuthenticatedEvidence{}, PortableProof{}, err
	}
	if err := portableCompletion(ctx, evidence, r.reader.now()); err != nil {
		return AuthenticatedEvidence{}, PortableProof{}, err
	}
	return evidence, proof, nil
}

// ProofVerifier owns an operator-provisioned root and its wall clock. Never
// construct it using values supplied by a deposit, HTTP request or proof. The
// proof's own matching headers are not a substitute for this trust root.
type ProofVerifier struct {
	anchor TrustAnchor
	now    func() time.Time
	slots  chan struct{}
}

func NewProofVerifier(operatorAnchor TrustAnchor) (*ProofVerifier, error) {
	if !validTrustAnchor(operatorAnchor) {
		return nil, fail(InvalidConfiguration, "proof", "anchor")
	}
	return &ProofVerifier{operatorAnchor, time.Now, make(chan struct{}, 4)}, nil
}

func (v *ProofVerifier) VerifyDepositProof(ctx context.Context, intent Intent, hash string, proof PortableProof) (AuthenticatedEvidence, error) {
	evidence, err := v.verify(ctx, proof, "deposit", hash, func(ctx context.Context, reader *TrustedReader) (AuthenticatedEvidence, error) {
		return reader.ReadDeposit(ctx, intent, hash)
	})
	if err == nil && !validIntent(intent, v.now()) {
		return AuthenticatedEvidence{}, fail(InvalidIntent, "intent", "proof_complete")
	}
	return evidence, err
}

func (v *ProofVerifier) VerifyTransferProof(ctx context.Context, intent TransferIntent, hash string, proof PortableProof) (AuthenticatedEvidence, error) {
	return v.verify(ctx, proof, "transfer", hash, func(ctx context.Context, reader *TrustedReader) (AuthenticatedEvidence, error) {
		return reader.ReadTransfer(ctx, intent, hash)
	})
}

func (v *ProofVerifier) verify(ctx context.Context, proof PortableProof, kind, hash string, run func(context.Context, *TrustedReader) (AuthenticatedEvidence, error)) (AuthenticatedEvidence, error) {
	if v == nil || v.now == nil || v.slots == nil || !validTrustAnchor(v.anchor) {
		return AuthenticatedEvidence{}, fail(InvalidConfiguration, "proof", "verifier")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	select {
	case v.slots <- struct{}{}:
		defer func() { <-v.slots }()
	case <-ctx.Done():
		return AuthenticatedEvidence{}, fail(contextCode(ctx), "proof", "capacity")
	}
	copy, err := copyProof(proof, kind, hash)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	replay := newProofReplay(copy.Responses)
	reader, err := NewTrustedReader(SourceConfig{RPC: "https://primary.satchel-proof.invalid", REST: "https://rest.satchel-proof.invalid", WitnessRPC: "https://witness.satchel-proof.invalid"}, v.anchor)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	reader.Close() // discard the network transport before any read can occur
	reader.reader.client = &http.Client{Transport: replay, Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("proof_redirect_refused") }}
	reader.reader.now = v.now
	evidence, err := run(ctx, reader)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	if !replay.complete() {
		return AuthenticatedEvidence{}, fail(InvalidResponse, "proof", "unused_responses")
	}
	if err := portableCompletion(ctx, evidence, v.now()); err != nil {
		return AuthenticatedEvidence{}, err
	}
	return evidence, nil
}

func portableCompletion(ctx context.Context, evidence AuthenticatedEvidence, now time.Time) error {
	if ctx.Err() != nil {
		return fail(contextCode(ctx), "proof", "complete")
	}
	if !evidence.ConsensusAuthenticated() || !now.Before(evidence.anchorTime.Add(time.Duration(evidence.anchor.PeriodSeconds)*time.Second)) || evidence.anchorTime.After(now.Add(maxClockSkew)) {
		return fail(UntrustedConsensus, "proof", "expired_anchor_complete")
	}
	if !validHead(evidence.evidence.Observation.Head, now) || !validHead(evidence.evidence.Observation.IndependentHead, now) || !validHead(evidence.evidence.WitnessHead, now) {
		return fail(StaleHead, "proof", "complete")
	}
	return nil
}

func copyProof(p PortableProof, kind, hash string) (PortableProof, error) {
	refuse := func() (PortableProof, error) { return PortableProof{}, fail(InvalidResponse, "proof", "contract") }
	if p.Version != PortableProofVersion || p.ChainID != ChainID || (kind != "deposit" && kind != "transfer") || p.Kind != kind || !digest(hash) || p.TxHash != strings.ToUpper(hash) || len(p.Responses) == 0 || len(p.Responses) > maxProofResponses {
		return refuse()
	}
	out := PortableProof{p.Version, p.ChainID, p.Kind, p.TxHash, make([]ProofResponse, len(p.Responses))}
	total, wireUpperBound := 0, 512
	for n, response := range p.Responses {
		if len(response.Path) > 128 || len(response.Query) > 512 || len(response.Body) == 0 || len(response.Body) > maxResponseBytes || len(response.Body) > maxProofBodyBytes-total || !chainjson.ValidFolded(response.Body) {
			return refuse()
		}
		allowed := false
		switch response.Source {
		case "primary":
			allowed = response.Path == "/status" || response.Path == "/tx" || response.Path == "/commit" || response.Path == "/block_results" || response.Path == "/validators"
		case "witness":
			allowed = response.Path == "/status" || response.Path == "/commit" || response.Path == "/validators"
		case "rest":
			allowed = response.Path == "/cosmos/tx/v1beta1/txs/"+p.TxHash && response.Query == ""
		}
		query, err := url.ParseQuery(response.Query)
		if !allowed || err != nil || len(query) > 4 || query.Encode() != response.Query {
			return refuse()
		}
		total += len(response.Body)
		// json.Marshal may HTML-escape raw JSON strings. Bound that expansion
		// without constructing a potentially 84 MiB temporary encoded proof.
		wireUpperBound += len(response.Body) + 5*(bytes.Count(response.Body, []byte("<"))+bytes.Count(response.Body, []byte(">"))+bytes.Count(response.Body, []byte("&"))) + 3*(bytes.Count(response.Body, []byte("\u2028"))+bytes.Count(response.Body, []byte("\u2029"))) + 256 + 6*(len(response.Path)+len(response.Query)+len(response.Source))
		if wireUpperBound > MaxPortableProofBytes {
			return refuse()
		}
		out.Responses[n] = ProofResponse{response.Source, response.Path, response.Query, append(json.RawMessage(nil), response.Body...)}
	}
	return out, nil
}

type proofKey struct{ source, path, query string }
type proofReplay struct {
	mu        sync.Mutex
	responses map[proofKey][]json.RawMessage
	remaining int
}

func newProofReplay(responses []ProofResponse) *proofReplay {
	r := &proofReplay{responses: make(map[proofKey][]json.RawMessage), remaining: len(responses)}
	for _, response := range responses {
		key := proofKey{response.Source, response.Path, response.Query}
		r.responses[key] = append(r.responses[key], response.Body)
	}
	return r
}

func (r *proofReplay) RoundTrip(request *http.Request) (*http.Response, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if request.Context().Err() != nil {
		return nil, request.Context().Err()
	}
	source := strings.TrimSuffix(request.URL.Hostname(), ".satchel-proof.invalid")
	if request.Method != http.MethodGet || request.URL.Scheme != "https" || request.URL.Host != source+".satchel-proof.invalid" || request.URL.User != nil || request.URL.RawPath != "" || request.URL.Fragment != "" {
		return nil, errors.New("invalid_proof_request")
	}
	key := proofKey{source, request.URL.Path, request.URL.RawQuery}
	queue := r.responses[key]
	if len(queue) == 0 {
		return nil, errors.New("missing_proof_response")
	}
	body := queue[0]
	r.responses[key] = queue[1:]
	r.remaining--
	return &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": {"application/json"}}, ContentLength: int64(len(body)), Body: io.NopCloser(bytes.NewReader(body)), Request: request}, nil
}

func (r *proofReplay) complete() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.remaining == 0
}
