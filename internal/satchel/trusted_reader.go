package satchel

// This opt-in path authenticates validator commits using CometBFT's actual
// light client. No checkpoint is obtained from an untrusted RPC automatically.
// Operators must independently provision the initial height/hash and witness.
import (
	"context"
	"encoding/hex"
	"errors"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtsecp "github.com/cometbft/cometbft/crypto/secp256k1"
	"github.com/cometbft/cometbft/light"
	"github.com/cometbft/cometbft/light/provider"
	"github.com/cometbft/cometbft/light/store"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
)

type TrustAnchor struct {
	Height            int64  `json:"height"`
	Hash              string `json:"hash"`
	PeriodSeconds     int64  `json:"period_seconds"`
	EvidenceReference string `json:"evidence_reference"`
}
type TrustedReader struct {
	reader *ChainReader
	anchor TrustAnchor
	gate   chan struct{}
}
type AuthenticatedEvidence struct {
	evidence   ChainEvidence
	anchor     TrustAnchor
	anchorTime time.Time
}

func (e AuthenticatedEvidence) Observation() Observation {
	o := e.evidence.Observation
	o.TxBytes = append([]byte(nil), o.TxBytes...)
	o.Transfers = append([]Transfer(nil), o.Transfers...)
	if o.Code != nil {
		v := *o.Code
		o.Code = &v
	}
	if o.TransferIndex != nil {
		v := *o.TransferIndex
		o.TransferIndex = &v
	}
	if o.Head.CatchingUp != nil {
		v := *o.Head.CatchingUp
		o.Head.CatchingUp = &v
	}
	if o.IndependentHead.CatchingUp != nil {
		v := *o.IndependentHead.CatchingUp
		o.IndependentHead.CatchingUp = &v
	}
	return o
}
func (e AuthenticatedEvidence) Receipt() ReceiptCandidate { return e.evidence.Receipt }
func (e AuthenticatedEvidence) ConsensusAuthenticated() bool {
	return e.anchor.Height > 0 && !e.anchorTime.IsZero()
}

// Authentication of a chain result is not custody, owner authorization, global
// receipt consumption, reserve coverage, or permission to post a ledger credit.
func (AuthenticatedEvidence) CreditAuthorized() bool { return false }

func validTrustAnchor(a TrustAnchor) bool {
	return a.Height > 0 && digest(a.Hash) && a.PeriodSeconds >= 60 && a.PeriodSeconds <= 86400 && strings.TrimSpace(a.EvidenceReference) != "" && len(a.EvidenceReference) <= 512
}

func NewTrustedReader(cfg SourceConfig, a TrustAnchor) (*TrustedReader, error) {
	if !validTrustAnchor(a) || cfg.WitnessRPC == "" || cfg.WitnessRPC == cfg.RPC {
		return nil, fail(InvalidConfiguration, "trust", "anchor")
	}
	r, e := NewChainReader(cfg)
	if e != nil {
		return nil, e
	}
	if strings.EqualFold(r.rpc.Scheme+"://"+r.rpc.Host, r.witness.Scheme+"://"+r.witness.Host) && r.rpc.Path == r.witness.Path {
		r.Close()
		return nil, fail(InvalidConfiguration, "trust", "witness")
	}
	return &TrustedReader{r, a, make(chan struct{}, 1)}, nil
}
func (r *TrustedReader) Close() {
	if r != nil {
		r.reader.Close()
	}
}

// CheckTrust performs real bounded read-only authentication before a signing
// boundary is opened. Shape-valid, expired or unreachable anchors cannot make
// the private service accepting. It consumes no receipt and sends no evidence.
func (r *TrustedReader) CheckTrust(ctx context.Context) error {
	if r == nil || r.reader == nil {
		return fail(InvalidConfiguration, "trust", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	select {
	case r.gate <- struct{}{}:
		defer func() { <-r.gate }()
	case <-ctx.Done():
		return fail(contextCode(ctx), "trust", "capacity")
	}
	session := &readSession{r.reader, maxEvidenceBytes}
	head, err := session.head(ctx, r.reader.rpc, "primary")
	if err != nil {
		return err
	}
	witness, err := session.head(ctx, r.reader.witness, "witness")
	if err != nil || witness.Height < head.Height {
		return fail(InconsistentObservations, "trust", "witness_head")
	}
	budget := &lightBudget{remaining: 8 << 20, calls: 64}
	p := &boundedProvider{r.reader, r.reader.rpc, "primary", budget}
	w := &boundedProvider{r.reader, r.reader.witness, "witness", budget}
	hash, _ := hex.DecodeString(r.anchor.Hash)
	client, err := light.NewClient(ctx, ChainID, light.TrustOptions{Height: r.anchor.Height, Hash: hash, Period: time.Duration(r.anchor.PeriodSeconds) * time.Second}, p, []provider.Provider{w}, &memoryLightStore{blocks: map[int64]*cmt.LightBlock{}}, light.MaxRetryAttempts(0), light.MaxClockDrift(5*time.Second), light.PruningSize(64), light.ConfirmationFunction(func(string) bool { return false }))
	if err != nil {
		return fail(UntrustedConsensus, "trust", "initialize")
	}
	anchor, err := client.TrustedLightBlock(r.anchor.Height)
	if err != nil {
		return fail(UntrustedConsensus, "trust", "anchor")
	}
	for _, h := range []Head{head, witness} {
		lb, err := client.VerifyLightBlockAtHeight(ctx, h.Height, r.reader.now())
		if err != nil || !strings.EqualFold(hex.EncodeToString(lb.Hash()), h.BlockHash) || !lb.Time.Equal(h.BlockTime) {
			return fail(UntrustedConsensus, "trust", "live_head")
		}
	}
	now := r.reader.now()
	if !now.Before(anchor.Time.Add(time.Duration(r.anchor.PeriodSeconds)*time.Second)) || anchor.Time.After(now.Add(5*time.Second)) || !validHead(head, now) || !validHead(witness, now) || ctx.Err() != nil {
		return fail(UntrustedConsensus, "trust", "expired_anchor")
	}
	return nil
}
func (r *TrustedReader) ReadTransfer(ctx context.Context, i TransferIntent, hash string) (AuthenticatedEvidence, error) {
	return r.read(ctx, func(ctx context.Context) (ChainEvidence, error) { return r.reader.ReadTransfer(ctx, i, hash) })
}
func (r *TrustedReader) ReadDeposit(ctx context.Context, i Intent, hash string) (AuthenticatedEvidence, error) {
	evidence, err := r.read(ctx, func(ctx context.Context) (ChainEvidence, error) { return r.reader.ReadDeposit(ctx, i, hash) })
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	if !validIntent(i, r.reader.now()) {
		return AuthenticatedEvidence{}, fail(InvalidIntent, "intent", "trusted_complete")
	}
	return evidence, nil
}
func (r *TrustedReader) read(ctx context.Context, collect func(context.Context) (ChainEvidence, error)) (AuthenticatedEvidence, error) {
	if r == nil || r.reader == nil {
		return AuthenticatedEvidence{}, fail(InvalidConfiguration, "trust", "reader")
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	select {
	case r.gate <- struct{}{}:
		defer func() { <-r.gate }()
	case <-ctx.Done():
		return AuthenticatedEvidence{}, fail(contextCode(ctx), "trust", "capacity")
	}
	e, err := collect(ctx)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	if e.Observation.Head.Height-e.Observation.Height+1 < 3 {
		return AuthenticatedEvidence{}, fail(StaleHead, "trust", "depth")
	}
	budget := &lightBudget{remaining: 8 << 20, calls: 64}
	p := &boundedProvider{r.reader, r.reader.rpc, "primary", budget}
	w := &boundedProvider{r.reader, r.reader.witness, "witness", budget}
	hash, _ := hex.DecodeString(r.anchor.Hash)
	// Fresh in-memory trust on each reconciliation re-verifies the provisioned
	// anchor. Restart cannot silently adopt a peer's new checkpoint. Capacity and
	// wall-clock bounds may refuse large validator transitions safely.
	client, err := light.NewClient(ctx, ChainID, light.TrustOptions{Height: r.anchor.Height, Hash: hash, Period: time.Duration(r.anchor.PeriodSeconds) * time.Second}, p, []provider.Provider{w}, &memoryLightStore{blocks: map[int64]*cmt.LightBlock{}}, light.MaxRetryAttempts(0), light.MaxClockDrift(5*time.Second), light.PruningSize(64), light.ConfirmationFunction(func(string) bool { return false }))
	if err != nil {
		return AuthenticatedEvidence{}, fail(UntrustedConsensus, "trust", "initialize")
	}
	now := r.reader.now()
	anchor, err := client.TrustedLightBlock(r.anchor.Height)
	if err != nil || !now.Before(anchor.Time.Add(time.Duration(r.anchor.PeriodSeconds)*time.Second)) || anchor.Time.After(now.Add(5*time.Second)) {
		return AuthenticatedEvidence{}, fail(UntrustedConsensus, "trust", "expired_anchor")
	}
	for _, height := range []int64{e.Observation.Height, e.Observation.Height + 1, e.Observation.Head.Height} {
		lb, err := client.VerifyLightBlockAtHeight(ctx, height, now)
		if err != nil {
			return AuthenticatedEvidence{}, fail(UntrustedConsensus, "trust", "verify_commit")
		}
		if height == e.Observation.Height && !strings.EqualFold(hex.EncodeToString(lb.Hash()), e.Observation.BlockHash) {
			return AuthenticatedEvidence{}, fail(InconsistentObservations, "trust", "inclusion")
		}
		if height == e.Observation.Head.Height && (!strings.EqualFold(hex.EncodeToString(lb.Hash()), e.Observation.Head.BlockHash) || !lb.Time.Equal(e.Observation.Head.BlockTime)) {
			return AuthenticatedEvidence{}, fail(InconsistentObservations, "trust", "head")
		}
		// Bind the H+1 result commitment to the exact independently verified header
		// used by C3, rather than merely checking some header at the same height.
		if height == e.Observation.Height+1 {
			if !strings.EqualFold(e.resultCommitHash, hex.EncodeToString(lb.Hash())) {
				return AuthenticatedEvidence{}, fail(InconsistentObservations, "trust", "result_header")
			}
		}
	}
	finished := r.reader.now()
	if !finished.Before(anchor.Time.Add(time.Duration(r.anchor.PeriodSeconds)*time.Second)) || anchor.Time.After(finished.Add(5*time.Second)) {
		return AuthenticatedEvidence{}, fail(UntrustedConsensus, "trust", "expired_anchor_complete")
	}
	if !validHead(e.Observation.Head, finished) || ctx.Err() != nil {
		return AuthenticatedEvidence{}, fail(StaleHead, "trust", "complete")
	}
	// C3 checked both witness identities before light-client I/O. Authentication
	// must preserve that freshness contract through completion, including the
	// actual witness status when it is ahead of the compared primary height.
	if !validHead(e.WitnessHead, finished) || !validHead(e.Observation.IndependentHead, finished) {
		return AuthenticatedEvidence{}, fail(StaleHead, "witness", "complete")
	}
	return AuthenticatedEvidence{evidence: e, anchor: r.anchor, anchorTime: anchor.Time}, nil
}

type lightBudget struct {
	mu        sync.Mutex
	remaining int64
	calls     int
}
type boundedProvider struct {
	reader *ChainReader
	base   *url.URL
	label  string
	budget *lightBudget
}

func (p *boundedProvider) ChainID() string { return ChainID }
func (p *boundedProvider) ReportEvidence(context.Context, cmt.Evidence) error {
	return errors.New("read_only_provider")
}
func (p *boundedProvider) LightBlock(ctx context.Context, height int64) (*cmt.LightBlock, error) {
	p.budget.mu.Lock()
	defer p.budget.mu.Unlock()
	if p.base == nil || p.budget.calls < 2+boolInt(height == 0) || p.budget.remaining <= 0 {
		return nil, fail(SourceUnavailable, "trust", "resource_limit")
	}
	p.budget.calls -= 2
	s := &readSession{p.reader, p.budget.remaining}
	defer func() { p.budget.remaining = s.remaining }()
	if height == 0 {
		head, err := s.head(ctx, p.base, p.label)
		if err != nil {
			return nil, err
		}
		height = head.Height
		p.budget.calls--
	}
	c, err := s.commit(ctx, p.base, p.label, height, true)
	if err != nil {
		return nil, err
	}
	var v core.ResultValidators
	_, err = s.rpc(ctx, p.base, p.label, "validators", url.Values{"height": {strconv.FormatInt(height, 10)}, "page": {"1"}, "per_page": {"100"}}, &v)
	if err != nil || v.BlockHeight != height || v.Total <= 0 || v.Total > 100 || v.Count != v.Total || len(v.Validators) != v.Total {
		return nil, fail(InvalidResponse, "trust", "validators")
	}
	seen := map[string]bool{}
	var power int64
	for _, val := range v.Validators {
		if val == nil || val.PubKey == nil {
			return nil, fail(InvalidResponse, "trust", "validator_key")
		}
		switch key := val.PubKey.(type) {
		case cmted.PubKey:
			if len(key) != cmted.PubKeySize {
				return nil, fail(InvalidResponse, "trust", "validator_key")
			}
		case cmtsecp.PubKey:
			if len(key) != cmtsecp.PubKeySize {
				return nil, fail(InvalidResponse, "trust", "validator_key")
			}
		default:
			return nil, fail(InvalidResponse, "trust", "validator_key")
		}
		if seen[string(val.Address)] || val.ValidateBasic() != nil || val.VotingPower <= 0 || val.VotingPower > cmt.MaxTotalVotingPower-power {
			return nil, fail(InvalidResponse, "trust", "validator_power")
		}
		seen[string(val.Address)] = true
		power += val.VotingPower
	}
	block := &cmt.LightBlock{SignedHeader: &c.SignedHeader, ValidatorSet: cmt.NewValidatorSet(v.Validators)}
	if block.ValidateBasic(ChainID) != nil {
		return nil, fail(UntrustedConsensus, "trust", "light_block")
	}
	return block, nil
}

// This bounded Store is deliberately ephemeral; the reviewed anchor is the
// sole persistent root of trust. It stores no untrusted network checkpoint.
type memoryLightStore struct{ blocks map[int64]*cmt.LightBlock }

func (s *memoryLightStore) SaveLightBlock(b *cmt.LightBlock) error {
	if len(s.blocks) >= 64 && s.blocks[b.Height] == nil {
		return errors.New("light_store_capacity")
	}
	s.blocks[b.Height] = b
	return nil
}
func (s *memoryLightStore) DeleteLightBlock(h int64) error { delete(s.blocks, h); return nil }
func (s *memoryLightStore) LightBlock(h int64) (*cmt.LightBlock, error) {
	b := s.blocks[h]
	if b == nil {
		return nil, store.ErrLightBlockNotFound
	}
	return b, nil
}
func (s *memoryLightStore) LastLightBlockHeight() (int64, error) {
	h := int64(-1)
	for k := range s.blocks {
		if k > h {
			h = k
		}
	}
	return h, nil
}
func (s *memoryLightStore) FirstLightBlockHeight() (int64, error) {
	h := int64(-1)
	for k := range s.blocks {
		if h < 0 || k < h {
			h = k
		}
	}
	return h, nil
}
func (s *memoryLightStore) LightBlockBefore(h int64) (*cmt.LightBlock, error) {
	var b *cmt.LightBlock
	for k, v := range s.blocks {
		if k < h && (b == nil || k > b.Height) {
			b = v
		}
	}
	if b == nil {
		return nil, store.ErrLightBlockNotFound
	}
	return b, nil
}
func (s *memoryLightStore) Prune(n uint16) error {
	for len(s.blocks) > int(n) {
		h, _ := s.FirstLightBlockHeight()
		delete(s.blocks, h)
	}
	return nil
}
func (s *memoryLightStore) Size() uint16 { return uint16(len(s.blocks)) }

func boolInt(b bool) int {
	if b {
		return 1
	}
	return 0
}
