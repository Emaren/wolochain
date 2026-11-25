package satchelservice

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime"
	"net"
	"net/http"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
)

const reviewerCustodyFeeURL = "http://127.0.0.1:8094/satchel/v1/custody/fee-checkpoint"

// The address and operation are fixed. Only the separately provisioned private
// bearer comes from protected operator configuration. Proxy environment,
// redirects, alternate URLs, caller authorities and retries are unavailable.
type ReviewerCustodyFeeClient struct {
	http  *http.Client
	token string
}

func NewReviewerCustodyFeeClient(token string) (*ReviewerCustodyFeeClient, error) {
	if !httpTokenPattern.MatchString(token) {
		return nil, ReviewerCensusUnconfigured
	}
	transport := &http.Transport{
		Proxy: nil, DisableCompression: true, DisableKeepAlives: true, MaxConnsPerHost: 2,
		DialContext:           (&net.Dialer{Timeout: 500 * time.Millisecond}).DialContext,
		ResponseHeaderTimeout: 750 * time.Millisecond,
	}
	return &ReviewerCustodyFeeClient{http: &http.Client{Transport: transport, Timeout: time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return ReviewerCensusSourceInvalid }}, token: token}, nil
}
func (c *ReviewerCustodyFeeClient) ReadReviewerCustodyFees(ctx context.Context, requested []string) (ReviewerCustodyFeeCheckpoint, error) {
	none := ReviewerCustodyFeeCheckpoint{}
	if c == nil || c.http == nil || ctx == nil || ctx.Err() != nil || !httpTokenPattern.MatchString(c.token) || validateCustodyFeeIDs(requested) != nil {
		return none, ReviewerCensusSourceInvalid
	}
	ids := make([]string, len(requested))
	copy(ids, requested)
	raw, err := json.Marshal(custodyFeeCheckpointRequest{Protocol: 1, OperationIDs: ids})
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	ctx, cancel := context.WithTimeout(ctx, time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, reviewerCustodyFeeURL, bytes.NewReader(raw))
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	request.Header.Set("Authorization", "Bearer "+c.token)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return none, ReviewerCensusSourceInvalid
	}
	defer response.Body.Close()
	media, params, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || media != "application/json" || response.StatusCode != http.StatusOK || response.Header.Get("Content-Encoding") != "" || response.ContentLength > custodyFeeCheckpointMaxOutput {
		return none, ReviewerCensusSourceInvalid
	}
	for key, value := range params {
		if key != "charset" || !strings.EqualFold(value, "utf-8") {
			return none, ReviewerCensusSourceInvalid
		}
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, custodyFeeCheckpointMaxOutput+1))
	if err != nil || len(body) > custodyFeeCheckpointMaxOutput || ctx.Err() != nil || !utf8.Valid(body) || !chainjson.ValidFolded(body) {
		return none, ReviewerCensusSourceInvalid
	}
	var out ReviewerCustodyFeeCheckpoint
	if strictHTTPJSON(body, &out) != nil || out.Protocol != 1 || out.Kind != "custody_fee_checkpoint" || out.ChainID != "wolo-1" || out.Denom != "uwolo" ||
		!validAddress(out.Vault) || !validReserveDigest(out.JournalDigest) || !validReserveDigest(out.PolicyDigest) || out.ObservedAtMS <= 0 ||
		len(out.AccountedOperations) != len(ids) || len(out.AccountedFingerprints) != len(ids) || out.UnresolvedFees == nil {
		return none, ReviewerCensusSourceInvalid
	}
	for _, id := range ids {
		if _, ok := out.AccountedOperations[id]; !ok {
			return none, ReviewerCensusSourceInvalid
		}
		if _, ok := out.AccountedFingerprints[id]; !ok {
			return none, ReviewerCensusSourceInvalid
		}
	}
	return out, nil
}
func (c *ReviewerCustodyFeeClient) Close() {
	if c != nil && c.http != nil {
		c.http.CloseIdleConnections()
	}
}

// This file contains independently prepared public signed coverage, not a
// private signing key. The existing protected-file reader nevertheless enforces
// the same ownership/symlink/permission boundary as other custody inputs.
type ReviewerReserveFile struct{ path string }

func NewReviewerReserveFile(path string) (*ReviewerReserveFile, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, ReviewerCensusUnconfigured
	}
	if _, err := readPrivateFileBounded(path, reviewerReserveCensusMaxBytes, reviewerReserveCensusMaxBytes); err != nil {
		return nil, ReviewerCensusCoverageInvalid
	}
	return &ReviewerReserveFile{path: path}, nil
}
func (f *ReviewerReserveFile) ReadReviewerReserveCoverage(ctx context.Context) ([]byte, error) {
	if f == nil || ctx == nil || ctx.Err() != nil {
		return nil, ReviewerCensusCoverageInvalid
	}
	raw, err := readPrivateFileBounded(f.path, reviewerReserveCensusMaxBytes, reviewerReserveCensusMaxBytes)
	if err != nil || ctx.Err() != nil {
		return nil, ReviewerCensusCoverageInvalid
	}
	return raw, nil
}

var _ ReviewerCustodyFeeReader = (*ReviewerCustodyFeeClient)(nil)
var _ ReviewerReserveCoverageReader = (*ReviewerReserveFile)(nil)
