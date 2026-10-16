package satchel

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"net/url"
	"reflect"
	"strconv"
	"strings"
	"time"

	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	"github.com/emaren/wolochain/internal/chainevents"
	"google.golang.org/protobuf/encoding/protojson"
)

// rpc uses the pinned CometBFT decoder and types, rather than a second chain
// protocol implementation. The envelope and proto3 presence guards are stricter
// than legacy settlement lookups and do not alter those execution paths.
func (s *readSession) rpc(ctx context.Context, base *url.URL, source, method string, query url.Values, dst any) (map[string]json.RawMessage, error) {
	data, err := s.get(ctx, base, source, method, "/"+method, query)
	if err != nil {
		return nil, err
	}
	var envelope struct {
		JSONRPC       string `json:"jsonrpc"`
		Result, Error json.RawMessage
	}
	if json.Unmarshal(data, &envelope) != nil || envelope.JSONRPC != "2.0" {
		return nil, fail(InvalidResponse, source, method)
	}
	if len(envelope.Error) > 0 && !bytes.Equal(bytes.TrimSpace(envelope.Error), []byte("null")) {
		return nil, fail(SourceUnavailable, source, method)
	}
	fields, ok := object(envelope.Result)
	if !ok {
		return nil, fail(InvalidResponse, source, method)
	}
	normalizeCode := func(raw json.RawMessage) (json.RawMessage, bool) {
		obj, ok := object(raw)
		if !ok {
			return nil, false
		}
		code, ok := executionCode(obj)
		if !ok {
			return nil, false
		}
		obj["code"] = json.RawMessage(strconv.FormatUint(uint64(code), 10))
		out, _ := json.Marshal(obj)
		return out, true
	}
	if method == "tx" {
		result, ok := normalizeCode(fields["tx_result"])
		if !ok {
			return nil, fail(InvalidResponse, source, method)
		}
		fields["tx_result"] = result
	}
	if method == "block_results" {
		var results []json.RawMessage
		if json.Unmarshal(fields["txs_results"], &results) != nil || len(results) == 0 || len(results) > 4096 {
			return nil, fail(InvalidResponse, source, method)
		}
		for i, result := range results {
			normalized, ok := normalizeCode(result)
			if !ok {
				return nil, fail(InvalidResponse, source, method)
			}
			results[i] = normalized
		}
		fields["txs_results"], _ = json.Marshal(results)
	}
	encoded, _ := json.Marshal(fields)
	if cmtjson.Unmarshal(encoded, dst) != nil {
		return nil, fail(InvalidResponse, source, method)
	}
	return fields, nil
}

func (s *readSession) head(ctx context.Context, base *url.URL, source string) (Head, error) {
	var status core.ResultStatus
	fields, err := s.rpc(ctx, base, source, "status", nil, &status)
	if err != nil {
		return Head{}, err
	}
	sync, ok := object(fields["sync_info"])
	if !ok {
		return Head{}, fail(InvalidResponse, source, "status")
	}
	var catchingUp *bool
	if json.Unmarshal(sync["catching_up"], &catchingUp) != nil || catchingUp == nil {
		return Head{}, fail(InvalidResponse, source, "status")
	}
	if status.NodeInfo.Network != ChainID {
		return Head{}, fail(WrongChain, source, "status")
	}
	h := Head{ChainID, status.SyncInfo.LatestBlockHeight, strings.ToUpper(hex.EncodeToString(status.SyncInfo.LatestBlockHash)), status.SyncInfo.LatestBlockTime, s.reader.now(), catchingUp}
	if !validHead(h, s.reader.now()) {
		return Head{}, fail(StaleHead, source, "status")
	}
	return h, nil
}

func (s *readSession) commit(ctx context.Context, base *url.URL, source string, height int64, allowLatestSeen bool) (*core.ResultCommit, error) {
	var result core.ResultCommit
	fields, err := s.rpc(ctx, base, source, "commit", url.Values{"height": {strconv.FormatInt(height, 10)}}, &result)
	if err != nil {
		return nil, err
	}
	if result.Header != nil && result.Header.ChainID != ChainID {
		return nil, fail(WrongChain, source, "commit")
	}
	// ValidateBasic checks shape and header/commit hash binding. It expressly
	// DOES NOT verify validator signatures or establish a light-client root.
	var canonical *bool
	// Comet /commit returns a seen (canonical=false) commit at its latest
	// height. Only that observed latest height may use this representation;
	// historical commits must be the canonical next-block-backed form.
	if json.Unmarshal(fields["canonical"], &canonical) != nil || canonical == nil || (!*canonical && !allowLatestSeen) || result.SignedHeader.ValidateBasic(ChainID) != nil || result.Height != height {
		return nil, fail(InvalidResponse, source, "commit")
	}
	return &result, nil
}

func transferEvents(events []abci.Event) []chainevents.Event {
	out := make([]chainevents.Event, len(events))
	for i, event := range events {
		out[i].Type = event.Type
		for _, a := range event.Attributes {
			out[i].Attributes = append(out[i].Attributes, chainevents.Attribute{Key: a.Key, Value: a.Value})
		}
	}
	return out
}

func normalizedEffects(events []abci.Event) ([]chainevents.Transfer, error) {
	converted := transferEvents(events)
	if chainevents.Validate(nil, converted) != nil {
		return nil, fail(AmbiguousTransfers, "primary", "events")
	}
	return chainevents.Extract(nil, converted), nil
}

func (s *readSession) restTx(ctx context.Context, hash string, i Intent, rpcTx *core.ResultTx, header *cmt.Header, effects []chainevents.Transfer) error {
	data, err := s.get(ctx, s.reader.rest, "rest", "tx", "/cosmos/tx/v1beta1/txs/"+hash, nil)
	if err != nil {
		return err
	}
	var payload struct {
		Tx       *struct{ Body json.RawMessage } `json:"tx"`
		Response *struct {
			Height    string                `json:"height"`
			Hash      string                `json:"txhash"`
			Timestamp string                `json:"timestamp"`
			Logs      []chainevents.LogItem `json:"logs"`
			Events    []chainevents.Event   `json:"events"`
		} `json:"tx_response"`
	}
	fields, ok := object(data)
	if !ok || json.Unmarshal(data, &payload) != nil || payload.Tx == nil || payload.Response == nil {
		return fail(InvalidResponse, "rest", "tx")
	}
	responseFields, ok := object(fields["tx_response"])
	if !ok {
		return fail(InvalidResponse, "rest", "tx")
	}
	code, ok := executionCode(responseFields)
	if !ok {
		return fail(InvalidResponse, "rest", "tx")
	}
	if code != 0 {
		return fail(ExecutionFailed, "rest", "tx")
	}
	var body tx.TxBody
	if protojson.Unmarshal(payload.Tx.Body, &body) != nil {
		return fail(InvalidResponse, "rest", "tx")
	}
	if !exactSendBody(&body, i.Sender, i.Vault, i.AmountUWolo, i.Memo) {
		return fail(TransactionMismatch, "rest", "body")
	}
	height, err := strconv.ParseInt(payload.Response.Height, 10, 64)
	stamp, stampErr := time.Parse(time.RFC3339Nano, payload.Response.Timestamp)
	// SDK x/auth/tx/query.go serializes block time with RFC3339 (seconds).
	// Preserve header precision in evidence; accept its documented REST truncation.
	if err != nil || strconv.FormatInt(height, 10) != payload.Response.Height || height != rpcTx.Height || !strings.EqualFold(payload.Response.Hash, hash) || stampErr != nil || (!stamp.Equal(header.Time) && !stamp.Equal(header.Time.Truncate(time.Second))) {
		return fail(TransactionMismatch, "rest", "identity")
	}
	if chainevents.Validate(payload.Response.Logs, payload.Response.Events) != nil {
		return fail(AmbiguousTransfers, "rest", "events")
	}
	// Compare both representations. Legacy log-first extraction is retained;
	// no extra top-level fee transfer is hidden or assigned a fresh ordinal.
	chosen := chainevents.Extract(payload.Response.Logs, payload.Response.Events)
	if !reflect.DeepEqual(chosen, effects) || !reflect.DeepEqual(chainevents.Extract(nil, payload.Response.Events), effects) {
		return fail(InconsistentObservations, "rest", "events")
	}
	return nil
}

// ReadDeposit fetches real bytes, inclusion proof, headers and execution result
// commitments from fixed server sources. Every successful return is still
// NONCREDITING: no independently authenticated consensus trust root is available.
// It performs at most 12 bounded GETs, never a write or automatic retry.
func (r *ChainReader) ReadDeposit(ctx context.Context, i Intent, txHash string) (ChainEvidence, error) {
	if r == nil || r.client == nil || r.slots == nil {
		return ChainEvidence{}, fail(InvalidConfiguration, "config", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, maxReadDuration)
	defer cancel()
	if ctx.Err() != nil {
		return ChainEvidence{}, fail(contextCode(ctx), "reader", "read")
	}
	if !validIntent(i, r.now()) || !digest(txHash) {
		return ChainEvidence{}, fail(InvalidIntent, "intent", "read")
	}
	select {
	case r.slots <- struct{}{}:
		defer func() { <-r.slots }()
	case <-ctx.Done():
		return ChainEvidence{}, fail(contextCode(ctx), "reader", "capacity")
	}
	s := &readSession{r, maxEvidenceBytes}
	hash := strings.ToUpper(txHash)
	head, err := s.head(ctx, r.rpc, "primary")
	if err != nil {
		return ChainEvidence{}, err
	}
	var transaction core.ResultTx
	_, err = s.rpc(ctx, r.rpc, "primary", "tx", url.Values{"hash": {"0x" + hash}, "prove": {"true"}}, &transaction)
	if err != nil {
		return ChainEvidence{}, err
	}
	if !strings.EqualFold(hex.EncodeToString(transaction.Hash), hash) || len(transaction.Tx) == 0 || len(transaction.Tx) > 65536 || !bytes.Equal(transaction.Tx.Hash(), transaction.Hash) {
		return ChainEvidence{}, fail(TransactionMismatch, "primary", "tx")
	}
	if transaction.TxResult.Code != 0 {
		return ChainEvidence{}, fail(ExecutionFailed, "primary", "tx")
	}
	if transaction.Height <= 0 || transaction.Height >= head.Height {
		return ChainEvidence{}, fail(StaleHead, "primary", "inclusion_height")
	}
	cache := map[int64]*core.ResultCommit{}
	load := func(height int64) (*core.ResultCommit, error) {
		if c := cache[height]; c != nil {
			return c, nil
		}
		c, err := s.commit(ctx, r.rpc, "primary", height, height == head.Height)
		if err == nil {
			cache[height] = c
		}
		return c, err
	}
	included, err := load(transaction.Height)
	if err != nil {
		return ChainEvidence{}, err
	}
	next, err := load(transaction.Height + 1)
	if err != nil {
		return ChainEvidence{}, err
	}
	current, err := load(head.Height)
	if err != nil {
		return ChainEvidence{}, err
	}
	if !strings.EqualFold(hex.EncodeToString(current.Header.Hash()), head.BlockHash) || !current.Time.Equal(head.BlockTime) || !bytes.Equal(next.LastBlockID.Hash, included.Header.Hash()) || next.Time.Before(included.Time) || current.Time.Before(next.Time) {
		return ChainEvidence{}, fail(InconsistentObservations, "primary", "headers")
	}
	if transaction.Proof.Proof.Total > 4096 || len(transaction.Proof.Proof.Aunts) > 32 || transaction.Proof.Proof.Index != int64(transaction.Index) || !bytes.Equal(transaction.Proof.Data, transaction.Tx) || transaction.Proof.Validate(included.DataHash) != nil {
		return ChainEvidence{}, fail(InvalidInclusion, "primary", "tx_proof")
	}
	var results core.ResultBlockResults
	_, err = s.rpc(ctx, r.rpc, "primary", "block_results", url.Values{"height": {strconv.FormatInt(transaction.Height, 10)}}, &results)
	if err != nil {
		return ChainEvidence{}, err
	}
	if results.Height != transaction.Height || int64(len(results.TxsResults)) != transaction.Proof.Proof.Total || uint64(transaction.Index) >= uint64(len(results.TxsResults)) || !bytes.Equal(cmt.NewResults(results.TxsResults).Hash(), next.LastResultsHash) {
		return ChainEvidence{}, fail(InvalidResultCommitment, "primary", "block_results")
	}
	bound := results.TxsResults[transaction.Index]
	if !bytes.Equal(cmt.NewResults([]*abci.ExecTxResult{bound}).Hash(), cmt.NewResults([]*abci.ExecTxResult{&transaction.TxResult}).Hash()) {
		return ChainEvidence{}, fail(InvalidResultCommitment, "primary", "tx_result")
	}
	effects, err := normalizedEffects(transaction.TxResult.Events)
	if err != nil {
		return ChainEvidence{}, err
	}
	boundEffects, err := normalizedEffects(bound.Events)
	if err != nil {
		return ChainEvidence{}, err
	}
	if !reflect.DeepEqual(effects, boundEffects) {
		return ChainEvidence{}, fail(InconsistentObservations, "primary", "result_events")
	}
	if len(effects) != 1 {
		return ChainEvidence{}, fail(AmbiguousTransfers, "primary", "events")
	}
	if err = s.restTx(ctx, hash, i, &transaction, included.Header, effects); err != nil {
		return ChainEvidence{}, err
	}
	zero, ordinal := uint32(0), uint32(0)
	observation := Observation{ChainID: ChainID, TxHash: hash, TxBytes: []byte(transaction.Tx), Code: &zero, Height: transaction.Height, BlockHash: strings.ToUpper(hex.EncodeToString(included.Header.Hash())), BlockTime: included.Time, Head: head, Transfers: []Transfer{{effects[0].Sender, effects[0].Recipient, effects[0].Denom, effects[0].Amount}}, TransferIndex: &ordinal}
	var actualWitness Head
	if r.witness != nil {
		whead, err := s.head(ctx, r.witness, "witness")
		if err != nil {
			return ChainEvidence{}, err
		}
		if whead.Height < head.Height {
			return ChainEvidence{}, fail(InconsistentObservations, "witness", "head")
		}
		actualWitness = whead
		wcache := map[int64]*core.ResultCommit{}
		for _, height := range []int64{transaction.Height, transaction.Height + 1, head.Height, whead.Height} {
			if wcache[height] != nil {
				continue
			}
			remote, err := s.commit(ctx, r.witness, "witness", height, height == whead.Height)
			if err != nil {
				return ChainEvidence{}, err
			}
			wcache[height] = remote
			if primary := cache[height]; primary != nil && !bytes.Equal(remote.Header.Hash(), primary.Header.Hash()) {
				return ChainEvidence{}, fail(InconsistentObservations, "witness", "commit")
			}
		}
		latest := wcache[whead.Height]
		if !strings.EqualFold(hex.EncodeToString(latest.Header.Hash()), whead.BlockHash) || !latest.Time.Equal(whead.BlockTime) {
			return ChainEvidence{}, fail(InconsistentObservations, "witness", "status_commit")
		}
		compared := wcache[head.Height]
		if latest.Time.Before(compared.Time) {
			return ChainEvidence{}, fail(InconsistentObservations, "witness", "header_time")
		}
		observation.IndependentHead = Head{compared.ChainID, compared.Height, strings.ToUpper(hex.EncodeToString(compared.Header.Hash())), compared.Time, whead.ObservedAt, whead.CatchingUp}
	}
	// Recheck wall-clock freshness after I/O; never manufacture a second head
	// when there is no witness. The C2 public pure check remains unchanged.
	if !validHead(observation.Head, r.now()) {
		return ChainEvidence{}, fail(StaleHead, "primary", "read_complete")
	}
	if r.witness != nil && (!validHead(actualWitness, r.now()) || !validHead(observation.IndependentHead, r.now())) {
		return ChainEvidence{}, fail(StaleHead, "witness", "read_complete")
	}
	if !validIntent(i, r.now()) {
		return ChainEvidence{}, fail(InvalidIntent, "intent", "read_complete")
	}
	if ctx.Err() != nil {
		return ChainEvidence{}, fail(contextCode(ctx), "reader", "read_complete")
	}
	receipt, err := inspectDeposit(i, observation, r.now(), r.witness != nil)
	if err != nil {
		return ChainEvidence{}, fail(TransactionMismatch, "intent", "candidate")
	}
	return ChainEvidence{Observation: observation, Receipt: receipt, WitnessCompared: r.witness != nil, WitnessHead: actualWitness}, nil
}
