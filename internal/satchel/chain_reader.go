package satchel

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// FailureCode is stable across remote payloads. Errors never echo source URLs,
// credentials, response bodies or remote error strings.
type FailureCode string

const (
	InvalidConfiguration        FailureCode = "invalid_configuration"
	InvalidIntent               FailureCode = "invalid_intent"
	SourceUnavailable           FailureCode = "source_unavailable"
	Canceled                    FailureCode = "canceled"
	TimedOut                    FailureCode = "timed_out"
	ResponseTooLarge            FailureCode = "response_too_large"
	InvalidResponse             FailureCode = "invalid_response"
	WrongChain                  FailureCode = "wrong_chain"
	StaleHead                   FailureCode = "stale_head"
	TransactionMismatch         FailureCode = "transaction_mismatch"
	ExecutionFailed             FailureCode = "execution_failed"
	InvalidInclusion            FailureCode = "invalid_inclusion"
	InvalidResultCommitment     FailureCode = "invalid_result_commitment"
	AmbiguousTransfers          FailureCode = "ambiguous_transfers"
	InconsistentObservations    FailureCode = "inconsistent_observations"
	UntrustedConsensus          FailureCode = "untrusted_consensus_anchor"
	IndependentTrustUnavailable FailureCode = "independent_trust_unavailable"
)

type EvidenceError struct {
	Code              FailureCode
	Source, Operation string
}

func (e *EvidenceError) Error() string { return string(e.Code) + ":" + e.Source + ":" + e.Operation }
func (e *EvidenceError) Unwrap() error {
	if e.Code == Canceled {
		return context.Canceled
	}
	if e.Code == TimedOut {
		return context.DeadlineExceeded
	}
	return nil
}
func fail(code FailureCode, source, operation string) error {
	return &EvidenceError{code, source, operation}
}

// SourceConfig is constructed by the server, never from a deposit request.
// WitnessRPC is optional corroboration, NOT an assertion of operator independence.
type SourceConfig struct{ RPC, REST, WitnessRPC string }

const (
	maxResponseBytes = 1 << 20
	maxEvidenceBytes = 6 << 20
	maxReadDuration  = 8 * time.Second
)

// ChainReader exposes no generic RPC, broadcast, signer, keyring or write API.
// Its transport is owned here: no caller-supplied RoundTripper can bypass limits.
type ChainReader struct {
	rpc, rest, witness *url.URL
	client             *http.Client
	slots              chan struct{}
	now                func() time.Time
	proof              *proofRecorder // private per-read capture; never installed on the live reader
}

func NewChainReader(cfg SourceConfig) (*ChainReader, error) {
	parse := func(s string) (*url.URL, error) {
		u, err := url.Parse(s)
		if err != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.Opaque != "" || u.RawPath != "" {
			return nil, fail(InvalidConfiguration, "config", "source")
		}
		ip := net.ParseIP(u.Hostname())
		if u.Scheme != "https" && !(u.Scheme == "http" && ip != nil && ip.IsLoopback()) {
			return nil, fail(InvalidConfiguration, "config", "source")
		}
		u.Path = strings.TrimRight(u.Path, "/")
		return u, nil
	}
	rpc, err := parse(cfg.RPC)
	if err != nil {
		return nil, err
	}
	rest, err := parse(cfg.REST)
	if err != nil {
		return nil, err
	}
	var witness *url.URL
	if cfg.WitnessRPC != "" {
		witness, err = parse(cfg.WitnessRPC)
		if err != nil {
			return nil, err
		}
	}
	transport := &http.Transport{Proxy: nil, DialContext: (&net.Dialer{Timeout: 2 * time.Second}).DialContext,
		TLSHandshakeTimeout: 2 * time.Second, ResponseHeaderTimeout: 2 * time.Second, DisableCompression: true,
		MaxConnsPerHost: 4, MaxIdleConnsPerHost: 4, MaxIdleConns: 12, IdleConnTimeout: 30 * time.Second, MaxResponseHeaderBytes: 16384}
	return &ChainReader{rpc: rpc, rest: rest, witness: witness, client: &http.Client{Transport: transport, Timeout: 3 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect refused") }}, slots: make(chan struct{}, 4), now: time.Now}, nil
}

func (r *ChainReader) Close() {
	if r != nil && r.client != nil {
		r.client.CloseIdleConnections()
	}
}

// ChainEvidence is always NONCREDITING. It contains a fetched candidate and
// hash/inclusion/result consistency checks relative to unauthenticated headers.
// It cannot establish finality, independently operated sources or vault control.
type ChainEvidence struct {
	Observation      Observation
	Receipt          ReceiptCandidate
	WitnessCompared  bool
	WitnessHead      Head   // actual witness status, which may be ahead of the compared head
	resultCommitHash string // H+1 identity used for the execution-root check
}

func (ChainEvidence) Status() string               { return "NONCREDITING" }
func (ChainEvidence) TrustStatus() string          { return "UNTRUSTED_CONSENSUS_ANCHOR" }
func (ChainEvidence) CreditAuthorized() bool       { return false }
func (ChainEvidence) ConsensusAuthenticated() bool { return false }
func (ChainEvidence) Blockers() []FailureCode {
	return []FailureCode{UntrustedConsensus, IndependentTrustUnavailable}
}

type readSession struct {
	reader    *ChainReader
	remaining int64
}

func contextCode(ctx context.Context) FailureCode {
	if errors.Is(ctx.Err(), context.Canceled) {
		return Canceled
	}
	return TimedOut
}

func (s *readSession) get(ctx context.Context, base *url.URL, source, operation, path string, query url.Values) ([]byte, error) {
	if ctx.Err() != nil {
		return nil, fail(contextCode(ctx), source, operation)
	}
	u := *base
	u.Path += path
	u.RawQuery = query.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fail(InvalidConfiguration, source, operation)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Accept-Encoding", "identity")
	resp, err := s.reader.client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, fail(contextCode(ctx), source, operation)
		}
		var ne net.Error
		if errors.As(err, &ne) && ne.Timeout() {
			return nil, fail(TimedOut, source, operation)
		}
		return nil, fail(SourceUnavailable, source, operation)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fail(SourceUnavailable, source, operation)
	}
	if encoding := resp.Header.Get("Content-Encoding"); encoding != "" && encoding != "identity" {
		return nil, fail(InvalidResponse, source, operation)
	}
	limit := int64(maxResponseBytes)
	if s.remaining < limit {
		limit = s.remaining
	}
	if limit <= 0 || resp.ContentLength > limit {
		return nil, fail(ResponseTooLarge, source, operation)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if ctx.Err() != nil {
		return nil, fail(contextCode(ctx), source, operation)
	}
	if int64(len(data)) > limit {
		return nil, fail(ResponseTooLarge, source, operation)
	}
	if err != nil {
		var ne net.Error
		if errors.As(err, &ne) && ne.Timeout() {
			return nil, fail(TimedOut, source, operation)
		}
		return nil, fail(SourceUnavailable, source, operation)
	}
	s.remaining -= int64(len(data))
	if !strictJSON(data) {
		return nil, fail(InvalidResponse, source, operation)
	}
	if s.reader.proof != nil {
		if err := s.reader.proof.add(source, path, u.RawQuery, data); err != nil {
			return nil, err
		}
	}
	return data, nil
}
