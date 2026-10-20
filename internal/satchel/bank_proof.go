package satchel

// Exact native bank-state proofs. ABCI state at H is committed by the signed
// AppHash in header H+1, never by an unverified REST balance or header H.
import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"cosmossdk.io/collections"
	"cosmossdk.io/store/rootmulti"
	storetypes "cosmossdk.io/store/types"
	"github.com/cometbft/cometbft/crypto/merkle"
	"github.com/cometbft/cometbft/light"
	"github.com/cometbft/cometbft/light/provider"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	ics23 "github.com/cosmos/ics23/go"
	"github.com/emaren/wolochain/internal/chainjson"
)

const InvalidBankProof FailureCode = "invalid_bank_state_proof"

// BankProof is an untrusted bounded RPC transcript. It supplies no trust root,
// completeness assertion, liability inventory, custody or permission to spend.
type BankProof struct {
	Version   int             `json:"version"`
	ChainID   string          `json:"chain_id"`
	Address   string          `json:"address"`
	Denom     string          `json:"denom"`
	Height    int64           `json:"height"`
	Responses []ProofResponse `json:"responses"`
}

// AuthenticatedBankEvidence has no exported fields or constructor. Only the
// verifier below can bind the exact SDK key/value to a provisioned Comet root.
// This authenticates bank assets, not unencumbered funds or global solvency.
type AuthenticatedBankEvidence struct {
	address, balance, blockHash, appHash string
	height                               int64
	commitTime, anchorTime               time.Time
	anchor                               TrustAnchor
	head, witness                        Head
}

func (e AuthenticatedBankEvidence) VaultAddress() string   { return e.address }
func (e AuthenticatedBankEvidence) BalanceUWolo() string   { return e.balance }
func (e AuthenticatedBankEvidence) Height() int64          { return e.height }
func (e AuthenticatedBankEvidence) CommitHeight() int64    { return e.height + 1 }
func (e AuthenticatedBankEvidence) BlockHash() string      { return e.blockHash }
func (e AuthenticatedBankEvidence) AppHash() string        { return e.appHash }
func (e AuthenticatedBankEvidence) ChainID() string        { return ChainID }
func (e AuthenticatedBankEvidence) Denom() string          { return Denom }
func (e AuthenticatedBankEvidence) CreditAuthorized() bool { return false }
func (e AuthenticatedBankEvidence) FreshAt(now time.Time) bool {
	return e.height > 0 && address(e.address) && e.balance != "" && digest(e.blockHash) && digest(e.appHash) &&
		!e.anchorTime.IsZero() && validTrustAnchor(e.anchor) &&
		now.Before(e.anchorTime.Add(time.Duration(e.anchor.PeriodSeconds)*time.Second)) &&
		!e.anchorTime.After(now.Add(maxClockSkew)) && !e.commitTime.IsZero() &&
		!e.commitTime.After(now.Add(maxClockSkew)) && now.Sub(e.commitTime) <= maxHeadAge &&
		validHead(e.head, now) && validHead(e.witness, now)
}

// nativeBankKey reuses the exact v0.53 SDK collections codec, including the
// nonterminal account-address length prefix. No parallel protocol parser.
func nativeBankKey(vault string) ([]byte, error) {
	if !address(vault) {
		return nil, fail(InvalidIntent, "bank", "address")
	}
	addr, err := sdk.GetFromBech32(vault, "wolo")
	if err != nil || len(addr) != 20 {
		return nil, fail(InvalidIntent, "bank", "address")
	}
	return collections.EncodeKeyWithPrefix(banktypes.BalancesPrefix, collections.PairKeyCodec(sdk.AccAddressKey, collections.StringKey), collections.Join(sdk.AccAddress(addr), Denom))
}

func bankQuery(height int64, key []byte) url.Values {
	return url.Values{"path": {strconv.Quote("/store/bank/key")}, "data": {"0x" + strings.ToUpper(hex.EncodeToString(key))}, "height": {strconv.FormatInt(height, 10)}, "prove": {"true"}}
}

// DecodeBankProof is strict and bounded before nested protobuf decoding.
func DecodeBankProof(data []byte) (BankProof, error) {
	if len(data) == 0 || len(data) > MaxPortableProofBytes || !chainjson.ValidFolded(data) {
		return BankProof{}, fail(InvalidBankProof, "bank", "encoding")
	}
	var p BankProof
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if d.Decode(&p) != nil {
		return BankProof{}, fail(InvalidBankProof, "bank", "encoding")
	}
	return copyBankProof(p, p.Address, p.Height)
}

func copyBankProof(p BankProof, vault string, height int64) (BankProof, error) {
	key, err := nativeBankKey(vault)
	if err != nil {
		return BankProof{}, err
	}
	if p.Version != 1 || p.ChainID != ChainID || p.Denom != Denom || p.Address != vault || p.Height != height || height <= 0 || height == math.MaxInt64 || len(p.Responses) == 0 || len(p.Responses) > maxProofResponses {
		return BankProof{}, fail(InvalidBankProof, "bank", "contract")
	}
	out := p
	out.Responses = make([]ProofResponse, len(p.Responses))
	total, queries, wireUpperBound := 0, 0, 512
	for n, r := range p.Responses {
		if len(r.Path) > 128 || len(r.Query) > 512 || len(r.Body) == 0 || len(r.Body) > maxResponseBytes || len(r.Body) > maxProofBodyBytes-total || !chainjson.ValidFolded(r.Body) {
			return BankProof{}, fail(InvalidBankProof, "bank", "response")
		}
		allowed := (r.Source == "primary" || r.Source == "witness") && (r.Path == "/status" || r.Path == "/commit" || r.Path == "/validators")
		if r.Source == "primary" && r.Path == "/abci_query" && r.Query == bankQuery(height, key).Encode() {
			allowed = true
			queries++
		}
		q, err := url.ParseQuery(r.Query)
		if !allowed || err != nil || len(q) > 4 || q.Encode() != r.Query {
			return BankProof{}, fail(InvalidBankProof, "bank", "path")
		}
		total += len(r.Body)
		// RawMessage marshal can expand HTML/line separators. Bound the wire
		// result without first allocating an oversized encoded transcript.
		wireUpperBound += len(r.Body) + 5*(bytes.Count(r.Body, []byte("<"))+bytes.Count(r.Body, []byte(">"))+bytes.Count(r.Body, []byte("&"))) + 3*(bytes.Count(r.Body, []byte("\u2028"))+bytes.Count(r.Body, []byte("\u2029"))) + 256 + 6*(len(r.Path)+len(r.Query)+len(r.Source))
		if wireUpperBound > MaxPortableProofBytes {
			return BankProof{}, fail(ResponseTooLarge, "bank", "wire")
		}
		out.Responses[n] = ProofResponse{r.Source, r.Path, r.Query, append(json.RawMessage(nil), r.Body...)}
	}
	if queries != 1 {
		return BankProof{}, fail(InvalidBankProof, "bank", "query_count")
	}
	return out, nil
}

// ReadBankProof collects actual server-owned read-only ABCI evidence. The
// request fixes H, the vault and uwolo; the source cannot choose another key.
func (r *TrustedReader) ReadBankProof(ctx context.Context, vault string, height int64) (AuthenticatedBankEvidence, BankProof, error) {
	if ctx == nil || r == nil || r.reader == nil {
		return AuthenticatedBankEvidence{}, BankProof{}, fail(InvalidConfiguration, "bank", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	recorder := &proofRecorder{}
	copyReader := *r.reader
	copyReader.proof = recorder
	isolated := &TrustedReader{reader: &copyReader, anchor: r.anchor, gate: r.gate}
	e, err := isolated.readBank(ctx, vault, height)
	if err != nil {
		return AuthenticatedBankEvidence{}, BankProof{}, err
	}
	p, err := copyBankProof(BankProof{1, ChainID, vault, Denom, height, recorder.snapshot()}, vault, height)
	if ctx.Err() != nil {
		return AuthenticatedBankEvidence{}, BankProof{}, fail(contextCode(ctx), "bank", "proof_complete")
	}
	if err != nil || !e.FreshAt(r.reader.now()) {
		if err == nil {
			err = fail(StaleHead, "bank", "complete")
		}
		return AuthenticatedBankEvidence{}, BankProof{}, err
	}
	return e, p, nil
}

// VerifyBankProof replays the same collector and real Comet light client
// entirely offline against the verifier's independently provisioned root.
func (v *ProofVerifier) VerifyBankProof(ctx context.Context, vault string, height int64, proof BankProof) (AuthenticatedBankEvidence, error) {
	if ctx == nil || v == nil || v.now == nil || v.slots == nil || !validTrustAnchor(v.anchor) {
		return AuthenticatedBankEvidence{}, fail(InvalidConfiguration, "bank", "verifier")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	select {
	case v.slots <- struct{}{}:
		defer func() { <-v.slots }()
	case <-ctx.Done():
		return AuthenticatedBankEvidence{}, fail(contextCode(ctx), "bank", "capacity")
	}
	p, err := copyBankProof(proof, vault, height)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	replay := newProofReplay(p.Responses)
	r, err := NewTrustedReader(SourceConfig{RPC: "https://primary.satchel-proof.invalid", REST: "https://rest.satchel-proof.invalid", WitnessRPC: "https://witness.satchel-proof.invalid"}, v.anchor)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	r.Close()
	r.reader.client = &http.Client{Transport: replay, Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("bank_proof_redirect_refused") }}
	r.reader.now = v.now
	e, err := r.readBank(ctx, vault, height)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	if !replay.complete() || !e.FreshAt(v.now()) || ctx.Err() != nil {
		return AuthenticatedBankEvidence{}, fail(InvalidBankProof, "bank", "incomplete")
	}
	return e, nil
}

func (r *TrustedReader) readBank(ctx context.Context, vault string, height int64) (AuthenticatedBankEvidence, error) {
	if ctx == nil || r == nil || r.reader == nil || r.gate == nil || !validTrustAnchor(r.anchor) {
		return AuthenticatedBankEvidence{}, fail(InvalidConfiguration, "bank", "reader")
	}
	key, err := nativeBankKey(vault)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	if height <= 0 || height == math.MaxInt64 || height+1 < r.anchor.Height {
		return AuthenticatedBankEvidence{}, fail(InvalidIntent, "bank", "height")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	select {
	case r.gate <- struct{}{}:
		defer func() { <-r.gate }()
	case <-ctx.Done():
		return AuthenticatedBankEvidence{}, fail(contextCode(ctx), "bank", "capacity")
	}
	s := &readSession{r.reader, maxEvidenceBytes}
	head, err := s.head(ctx, r.reader.rpc, "primary")
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	witness, err := s.head(ctx, r.reader.witness, "witness")
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	if height+1 > head.Height || witness.Height < head.Height {
		return AuthenticatedBankEvidence{}, fail(StaleHead, "bank", "height")
	}
	var result core.ResultABCIQuery
	fields, err := s.rpc(ctx, r.reader.rpc, "primary", "abci_query", bankQuery(height, key), &result)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	response, ok := object(fields["response"])
	if !ok {
		return AuthenticatedBankEvidence{}, fail(InvalidBankProof, "bank", "query")
	}
	code, ok := executionCode(response)
	if !ok || code != 0 || result.Response.Code != 0 || result.Response.Height != height || !bytes.Equal(result.Response.Key, key) || len(result.Response.Value) > 128 || result.Response.ProofOps == nil {
		return AuthenticatedBankEvidence{}, fail(InvalidBankProof, "bank", "query")
	}
	budget := &lightBudget{remaining: 8 << 20, calls: 64}
	p := &boundedProvider{r.reader, r.reader.rpc, "primary", budget}
	w := &boundedProvider{r.reader, r.reader.witness, "witness", budget}
	hash, _ := hex.DecodeString(r.anchor.Hash)
	client, err := light.NewClient(ctx, ChainID, light.TrustOptions{Height: r.anchor.Height, Hash: hash, Period: time.Duration(r.anchor.PeriodSeconds) * time.Second}, p, []provider.Provider{w}, &memoryLightStore{blocks: map[int64]*cmt.LightBlock{}}, light.MaxRetryAttempts(0), light.MaxClockDrift(maxClockSkew), light.PruningSize(64), light.ConfirmationFunction(func(string) bool { return false }))
	if err != nil {
		return AuthenticatedBankEvidence{}, fail(UntrustedConsensus, "bank", "initialize")
	}
	anchor, err := client.TrustedLightBlock(r.anchor.Height)
	if err != nil {
		return AuthenticatedBankEvidence{}, fail(UntrustedConsensus, "bank", "anchor")
	}
	var committed *cmt.LightBlock
	for _, h := range []int64{height + 1, head.Height, witness.Height} {
		lb, err := client.VerifyLightBlockAtHeight(ctx, h, r.reader.now())
		if err != nil {
			return AuthenticatedBankEvidence{}, fail(UntrustedConsensus, "bank", "commit")
		}
		if h == height+1 {
			committed = lb
		}
		if (h == head.Height && (!bytes.Equal(lb.Hash(), mustHex(head.BlockHash)) || !lb.Time.Equal(head.BlockTime))) || (h == witness.Height && (!bytes.Equal(lb.Hash(), mustHex(witness.BlockHash)) || !lb.Time.Equal(witness.BlockTime))) {
			return AuthenticatedBankEvidence{}, fail(InconsistentObservations, "bank", "head_commit")
		}
	}
	if committed == nil || len(committed.AppHash) != 32 {
		return AuthenticatedBankEvidence{}, fail(InvalidBankProof, "bank", "root")
	}
	if err := verifyBankCommitment(result, key, committed.AppHash); err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	balance, err := nativeBankAmount(result.Response.Value)
	if err != nil {
		return AuthenticatedBankEvidence{}, err
	}
	e := AuthenticatedBankEvidence{vault, balance, strings.ToUpper(hex.EncodeToString(committed.Hash())), strings.ToUpper(hex.EncodeToString(committed.AppHash)), height, committed.Time, anchor.Time, r.anchor, head, witness}
	if ctx.Err() != nil {
		return AuthenticatedBankEvidence{}, fail(contextCode(ctx), "bank", "complete")
	}
	if !e.FreshAt(r.reader.now()) {
		return AuthenticatedBankEvidence{}, fail(StaleHead, "bank", "complete")
	}
	return e, nil
}

func mustHex(s string) []byte { b, _ := hex.DecodeString(s); return b }

func verifyBankCommitment(q core.ResultABCIQuery, key, root []byte) (err error) {
	refuse := func() error { return fail(InvalidBankProof, "bank", "commitment") }
	defer func() {
		if recover() != nil {
			err = refuse()
		}
	}()
	ops := q.Response.ProofOps
	if ops == nil || len(ops.Ops) != 2 || ops.Ops[0].Type != storetypes.ProofOpIAVLCommitment || ops.Ops[1].Type != storetypes.ProofOpSimpleMerkleCommitment || !bytes.Equal(ops.Ops[0].Key, key) || !bytes.Equal(ops.Ops[1].Key, []byte(banktypes.StoreKey)) {
		return refuse()
	}
	for _, op := range ops.Ops {
		if len(op.Data) == 0 || len(op.Data) > 65536 {
			return refuse()
		}
		var p ics23.CommitmentProof
		if p.Unmarshal(op.Data) != nil {
			return refuse()
		}
		if ex := p.GetExist(); ex != nil {
			if len(ex.Path) > 64 {
				return refuse()
			}
		} else if nx := p.GetNonexist(); nx != nil {
			if (nx.Left != nil && len(nx.Left.Path) > 64) || (nx.Right != nil && len(nx.Right.Path) > 64) {
				return refuse()
			}
		} else {
			return refuse()
		}
	}
	path := merkle.KeyPath{}.AppendKey([]byte(banktypes.StoreKey), merkle.KeyEncodingURL).AppendKey(key, merkle.KeyEncodingURL).String()
	runtime := rootmulti.DefaultProofRuntime()
	if len(q.Response.Value) == 0 {
		err = runtime.VerifyAbsence(ops, root, path)
	} else {
		err = runtime.VerifyValue(ops, root, path, q.Response.Value)
	}
	if err != nil {
		return refuse()
	}
	return nil
}

func nativeBankAmount(value []byte) (string, error) {
	if len(value) == 0 {
		return "0", nil
	} // accepted only after ICS23 nonmembership
	var decimal string
	if n, err := sdk.IntValue.Decode(value); err == nil {
		canonical, err := sdk.IntValue.Encode(n)
		if err != nil || !bytes.Equal(canonical, value) {
			return "", fail(InvalidBankProof, "bank", "amount")
		}
		decimal = n.String()
	} else {
		// SDK v0.53 retains historical Coin-encoded balances. Bind its denom
		// explicitly rather than trusting the compatibility decoder alone.
		var coin sdk.Coin
		if coin.Unmarshal(value) != nil || coin.Denom != Denom || coin.Amount.IsNil() {
			return "", fail(InvalidBankProof, "bank", "amount")
		}
		canonical, err := coin.Marshal()
		if err != nil || !bytes.Equal(canonical, value) {
			return "", fail(InvalidBankProof, "bank", "amount")
		}
		decimal = coin.Amount.String()
	}
	n, err := strconv.ParseInt(decimal, 10, 64)
	if err != nil || n < 0 || strconv.FormatInt(n, 10) != decimal {
		return "", fail(InvalidBankProof, "bank", "amount")
	}
	return decimal, nil
}
