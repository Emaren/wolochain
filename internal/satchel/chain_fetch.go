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
	"github.com/cosmos/btcutil/bech32"
	sdkaddress "github.com/cosmos/cosmos-sdk/types/address"
	"github.com/emaren/wolochain/internal/chainevents"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
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

func (s *readSession) restTx(ctx context.Context, hash string, i Intent, rpcTx *core.ResultTx, header *cmt.Header, effects []chainevents.Transfer, deposit bool, canonical *[]chainevents.Transfer) error {
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
	if !reflect.DeepEqual(chainevents.Extract(nil, payload.Response.Events), effects) {
		return fail(InconsistentObservations, "rest", "events")
	}
	if !reflect.DeepEqual(chosen, effects) {
		pos := 0
		for _, effect := range chosen {
			for pos < len(effects) && effects[pos] != effect {
				pos++
			}
			if pos == len(effects) {
				return fail(InconsistentObservations, "rest", "event_order")
			}
			pos++
		}
		effectIndex := outgoingEffectIndex
		if deposit {
			effectIndex = networkEffectIndex
		}
		if _, err := effectIndex(rpcTx.Tx, i, chosen); err != nil {
			return err
		}
	}
	*canonical = chosen
	return nil
}

// ReadDeposit fetches real bytes, inclusion proof, headers and execution result
// commitments from fixed server sources. Every successful return is still
// NONCREDITING: no independently authenticated consensus trust root is available.
// It performs at most 12 bounded GETs, never a write or automatic retry.
func (r *ChainReader) ReadDeposit(ctx context.Context, i Intent, txHash string) (ChainEvidence, error) {
	return r.readTransfer(ctx, i, txHash, true)
}

// TransferIntent is a server-owned immutable outgoing payment or return
// contract. Unlike a deposit intent it can name an existing escrow role and
// reconcile older transactions. It grants neither credit nor signing authority.
type TransferIntent struct{ Sender, Recipient, AmountUWolo, Memo string }

func (r *ChainReader) ReadTransfer(ctx context.Context, i TransferIntent, hash string) (ChainEvidence, error) {
	return r.readTransfer(ctx, Intent{Sender: i.Sender, Vault: i.Recipient, AmountUWolo: i.AmountUWolo, Memo: i.Memo}, hash, false)
}

func validTransferIntent(i Intent) bool {
	return address(i.Sender) && address(i.Vault) && i.Sender != i.Vault && amount(i.AmountUWolo) && len(i.Memo) > 0 && len(i.Memo) <= 256
}

func (r *ChainReader) readTransfer(ctx context.Context, i Intent, txHash string, deposit bool) (ChainEvidence, error) {
	if r == nil || r.client == nil || r.slots == nil {
		return ChainEvidence{}, fail(InvalidConfiguration, "config", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, maxReadDuration)
	defer cancel()
	if ctx.Err() != nil {
		return ChainEvidence{}, fail(contextCode(ctx), "reader", "read")
	}
	if (deposit && !validIntent(i, r.now())) || (!deposit && !validTransferIntent(i)) || !digest(txHash) {
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
	var canonical []chainevents.Transfer
	effectIndex := outgoingEffectIndex
	if deposit {
		effectIndex = networkEffectIndex
	}
	if _, err = effectIndex(transaction.Tx, i, effects); err != nil {
		return ChainEvidence{}, err
	}
	if err = s.restTx(ctx, hash, i, &transaction, included.Header, effects, deposit, &canonical); err != nil {
		return ChainEvidence{}, err
	}
	zero, ordinal := uint32(0), uint32(0)
	ordinal, err = effectIndex(transaction.Tx, i, canonical)
	if err != nil {
		return ChainEvidence{}, err
	}
	transfers := make([]Transfer, len(canonical))
	for idx, v := range canonical {
		transfers[idx] = Transfer{v.Sender, v.Recipient, v.Denom, v.Amount}
	}
	observation := Observation{ChainID: ChainID, TxHash: hash, TxBytes: []byte(transaction.Tx), Code: &zero, Height: transaction.Height, BlockHash: strings.ToUpper(hex.EncodeToString(included.Header.Hash())), BlockTime: included.Time, Head: head, Transfers: transfers, TransferIndex: &ordinal}
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
	if deposit && !validIntent(i, r.now()) {
		return ChainEvidence{}, fail(InvalidIntent, "intent", "read_complete")
	}
	if ctx.Err() != nil {
		return ChainEvidence{}, fail(contextCode(ctx), "reader", "read_complete")
	}
	var receipt ReceiptCandidate
	if deposit {
		receipt, err = inspectNetworkDeposit(i, observation, r.now(), r.witness != nil)
	} else if !exactSend(observation.TxBytes, i.Sender, i.Vault, i.AmountUWolo, i.Memo) ||
		observation.Transfers[ordinal] != (Transfer{i.Sender, i.Vault, Denom, i.AmountUWolo}) {
		err = fail(TransactionMismatch, "intent", "candidate")
	} else {
		receipt = ReceiptCandidate{ChainID, hash, ordinal}
	}
	if err != nil {
		return ChainEvidence{}, fail(TransactionMismatch, "intent", "candidate")
	}
	return ChainEvidence{Observation: observation, Receipt: receipt, WitnessCompared: r.witness != nil, WitnessHead: actualWitness, resultCommitHash: hex.EncodeToString(next.Header.Hash())}, nil
}

// A successful one-MsgSend transaction may also contain its exact signed ante
// fee effect. Preserve the public C2 pure one-effect contract, but let the
// network reader handle real SDK fee-paying transactions. No arbitrary extra
// transfer, split coin, fee payer/granter or duplicate effect is accepted.
func networkEffectIndex(rawBytes []byte, i Intent, effects []chainevents.Transfer) (uint32, error) {
	if len(effects) == 1 && effects[0] == (chainevents.Transfer{Sender: i.Sender, Recipient: i.Vault, Amount: i.AmountUWolo, Denom: Denom}) {
		return 0, nil
	}
	return outgoingEffectIndex(rawBytes, i, effects)
}

func inspectNetworkDeposit(i Intent, observation Observation, now time.Time, requireWitness bool) (ReceiptCandidate, error) {
	effects := make([]chainevents.Transfer, len(observation.Transfers))
	for n, effect := range observation.Transfers {
		effects[n] = chainevents.Transfer{Sender: effect.Sender, Recipient: effect.Recipient, Denom: effect.Denom, Amount: effect.Amount}
	}
	index, err := networkEffectIndex(observation.TxBytes, i, effects)
	if err != nil || observation.TransferIndex == nil || *observation.TransferIndex != index {
		return ReceiptCandidate{}, fail(AmbiguousTransfers, "deposit", "effects")
	}
	// The canonical authenticated identity is the one decoded MsgSend (message
	// index zero). Events are excluded from Comet's deterministic result root,
	// and therefore event position must not mint another consumable receipt.
	zero := uint32(0)
	observation.Transfers = []Transfer{{i.Sender, i.Vault, Denom, i.AmountUWolo}}
	observation.TransferIndex = &zero
	return inspectDeposit(i, observation, now, requireWitness)
}

// Outgoing transfers retain the shared parser's ordinal. The only permitted
// extra effect is the exact ante fee encoded in the same signed transaction,
// paid by its sender to the canonical SDK fee_collector module. Never renumber
// or accept arbitrary extra sends. Deposit C2 remains unchanged and strict.
func outgoingEffectIndex(rawBytes []byte, i Intent, effects []chainevents.Transfer) (uint32, error) {
	refuse := func() (uint32, error) { return 0, fail(AmbiguousTransfers, "primary", "outgoing_effects") }
	var raw tx.TxRaw
	var auth tx.AuthInfo
	if len(effects) == 0 || len(effects) > 2 || proto.Unmarshal(rawBytes, &raw) != nil || proto.Unmarshal(raw.AuthInfoBytes, &auth) != nil || len(auth.ProtoReflect().GetUnknown()) != 0 || auth.Fee == nil || auth.Tip != nil || len(auth.Fee.ProtoReflect().GetUnknown()) != 0 || auth.Fee.Payer != "" || auth.Fee.Granter != "" || len(auth.Fee.Amount) != 1 || auth.Fee.Amount[0] == nil || auth.Fee.Amount[0].Denom != Denom || !amount(auth.Fee.Amount[0].Amount) {
		return refuse()
	}
	words, err := bech32.ConvertBits(sdkaddress.Module("fee_collector"), 8, 5, true)
	if err != nil {
		return refuse()
	}
	collector, err := bech32.Encode("wolo", words)
	if err != nil {
		return refuse()
	}
	send := chainevents.Transfer{Sender: i.Sender, Recipient: i.Vault, Amount: i.AmountUWolo, Denom: Denom}
	fee := chainevents.Transfer{Sender: i.Sender, Recipient: collector, Amount: auth.Fee.Amount[0].Amount, Denom: Denom}
	var index int = -1
	fees := 0
	for idx, effect := range effects {
		switch effect {
		case send:
			if index >= 0 {
				return refuse()
			}
			index = idx
		case fee:
			fees++
		default:
			return refuse()
		}
	}
	if index < 0 || fees > 1 || len(effects) != 1+fees {
		return refuse()
	}
	return uint32(index), nil
}
