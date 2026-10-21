package satchel

// Genuine Wolo SDK bank/IAVL/multistore proofs, authenticated with synthetic
// Comet validators. These fixtures have no production key or trust authority.
import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/app"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
)

type nativeBankFixture struct {
	f             *readerFixture
	vals          *cmt.ValidatorSet
	vault, absent string
	queries       map[string]*abci.ResponseQuery
}

func newNativeBankFixture(t *testing.T) *nativeBankFixture {
	t.Helper()
	f, vals := signedReaderFixture(t)
	opts := viper.New()
	opts.Set(flags.FlagHome, t.TempDir())
	a := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, opts, baseapp.SetChainID(ChainID))
	t.Cleanup(func() { require.NoError(t, a.Close()) })
	key := secp256k1.GenPrivKeyFromSecret([]byte("isolated-native-bank-proof-sender"))
	sender, vault := sdk.AccAddress(key.PubKey().Address()), sdk.AccAddress(bytes.Repeat([]byte{0x73}, 20))
	absent := sdk.AccAddress(bytes.Repeat([]byte{0x74}, 20))
	genesisVals, err := simtestutil.CreateRandomValidatorSet()
	require.NoError(t, err)
	genesis, err := simtestutil.GenesisStateWithValSet(a.AppCodec(), a.DefaultGenesis(), genesisVals,
		[]authtypes.GenesisAccount{authtypes.NewBaseAccount(sender, key.PubKey(), 0, 0)},
		banktypes.Balance{Address: sender.String(), Coins: sdk.NewCoins(sdk.NewCoin(Denom, sdkmath.NewInt(10000000)))})
	require.NoError(t, err)
	state, err := cmtjson.Marshal(genesis)
	require.NoError(t, err)
	_, err = a.InitChain(&abci.RequestInitChain{ChainId: ChainID, InitialHeight: 100, Time: f.commits[100].Time, AppStateBytes: state, ConsensusParams: simtestutil.DefaultConsensusParams})
	require.NoError(t, err)
	signed, err := simtestutil.GenSignedMockTx(rand.New(rand.NewSource(1)), a.TxConfig(), []sdk.Msg{banktypes.NewMsgSend(sender, vault, sdk.NewCoins(sdk.NewInt64Coin(Denom, 7000000)))}, sdk.NewCoins(sdk.NewInt64Coin(Denom, 1)), 200000, ChainID, []uint64{0}, []uint64{0}, key)
	require.NoError(t, err)
	data, err := a.TxConfig().TxEncoder()(signed)
	require.NoError(t, err)
	executed, err := a.FinalizeBlock(&abci.RequestFinalizeBlock{Height: 100, Time: f.commits[100].Time, NextValidatorsHash: genesisVals.Hash(), Txs: [][]byte{data}})
	require.NoError(t, err)
	require.Zero(t, executed.TxResults[0].Code, executed.TxResults[0].Log)
	_, err = a.Commit()
	require.NoError(t, err)
	require.Equal(t, int64(100), a.LastCommitID().Version)
	queries := map[string]*abci.ResponseQuery{}
	for _, address := range []string{vault.String(), absent.String()} {
		key, err := nativeBankKey(address)
		require.NoError(t, err)
		q, err := a.Query(context.Background(), &abci.RequestQuery{Path: "/store/bank/key", Data: key, Height: 100, Prove: true})
		require.NoError(t, err)
		require.Zero(t, q.Code, q.Log)
		require.NotNil(t, q.ProofOps)
		require.Len(t, q.ProofOps.Ops, 2)
		queries[strings.ToUpper(hex.EncodeToString(key))] = q
	}
	// The actual H=100 state root belongs to H+1's AppHash. Retain a different
	// H AppHash so the off-by-one regression cannot accidentally pass.
	f.commits[101].AppHash = append([]byte(nil), a.LastCommitID().Hash...)
	f.commits[102].AppHash = append([]byte(nil), a.LastCommitID().Hash...)
	validator := cmted.GenPrivKeyFromSecret([]byte("synthetic-light-client-fixture"))
	for height := int64(100); height <= 102; height++ {
		h := f.commits[height].Header
		if height > 100 {
			h.LastBlockID = f.commits[height-1].Commit.BlockID
			h.LastCommitHash = f.commits[height-1].Commit.Hash()
		}
		id := cmt.BlockID{Hash: h.Hash(), PartSetHeader: cmt.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
		vote := cmtproto.Vote{Type: cmtproto.PrecommitType, Height: height, BlockID: id.ToProto(), Timestamp: h.Time, ValidatorAddress: validator.PubKey().Address()}
		signature, err := validator.Sign(cmt.VoteSignBytes(ChainID, &vote))
		require.NoError(t, err)
		f.commits[height].Commit = &cmt.Commit{Height: height, BlockID: id, Signatures: []cmt.CommitSig{{BlockIDFlag: cmt.BlockIDFlagCommit, ValidatorAddress: validator.PubKey().Address(), Timestamp: h.Time, Signature: signature}}}
	}
	f.status.SyncInfo.LatestBlockHash = f.commits[102].Header.Hash()
	return &nativeBankFixture{f, vals, vault.String(), absent.String(), queries}
}

func (f *nativeBankFixture) reader(t *testing.T, mutate func(*http.Request, []byte) []byte) *TrustedReader {
	t.Helper()
	serve := func() *httptest.Server {
		s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			require.Equal(t, http.MethodGet, r.Method)
			var body []byte
			switch r.URL.Path {
			case "/abci_query":
				key := strings.TrimPrefix(r.URL.Query().Get("data"), "0x")
				q := f.queries[key]
				require.NotNil(t, q)
				require.Equal(t, bankQuery(100, q.Key).Encode(), r.URL.RawQuery)
				result, err := cmtjson.Marshal(core.ResultABCIQuery{Response: *q})
				require.NoError(t, err)
				body = []byte(fmt.Sprintf(`{"jsonrpc":"2.0","id":-1,"result":%s}`, result))
			case "/validators":
				height, _ := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
				result, err := cmtjson.Marshal(core.ResultValidators{BlockHeight: height, Validators: f.vals.Validators, Count: len(f.vals.Validators), Total: len(f.vals.Validators)})
				require.NoError(t, err)
				body = []byte(fmt.Sprintf(`{"jsonrpc":"2.0","id":-1,"result":%s}`, result))
			default:
				body = f.f.response(t, r)
			}
			if mutate != nil {
				body = mutate(r, body)
			}
			_, _ = w.Write(body)
		}))
		t.Cleanup(s.Close)
		return s
	}
	p, w := serve(), serve()
	r, err := NewTrustedReader(SourceConfig{RPC: p.URL, REST: p.URL, WitnessRPC: w.URL}, fixtureAnchor(f.f))
	require.NoError(t, err)
	r.reader.now = func() time.Time { return f.f.now }
	t.Cleanup(r.Close)
	return r
}

func cloneBankProof(t *testing.T, p BankProof) BankProof {
	t.Helper()
	b, err := json.Marshal(p)
	require.NoError(t, err)
	var out BankProof
	require.NoError(t, json.Unmarshal(b, &out))
	return out
}
func mutateBankQuery(t *testing.T, p *BankProof, mutate func(*abci.ResponseQuery)) {
	t.Helper()
	for n, response := range p.Responses {
		if response.Path == "/abci_query" {
			var envelope struct {
				JSONRPC string               `json:"jsonrpc"`
				ID      json.RawMessage      `json:"id"`
				Result  core.ResultABCIQuery `json:"result"`
			}
			require.NoError(t, cmtjson.Unmarshal(response.Body, &envelope))
			mutate(&envelope.Result.Response)
			b, err := cmtjson.Marshal(envelope)
			require.NoError(t, err)
			p.Responses[n].Body = b
			return
		}
	}
	t.Fatal("missing bank query")
}

func TestAuthenticatedNativeBankProof(t *testing.T) {
	f := newNativeBankFixture(t)
	r := f.reader(t, nil)
	for _, vault := range []string{f.vault, f.absent} {
		t.Run(vault, func(t *testing.T) {
			e, p, err := r.ReadBankProof(context.Background(), vault, 100)
			require.NoError(t, err)
			want := "7000000"
			if vault == f.absent {
				want = "0"
			}
			require.Equal(t, want, e.BalanceUWolo())
			require.Equal(t, vault, e.VaultAddress())
			require.Equal(t, int64(100), e.Height())
			require.Equal(t, int64(101), e.CommitHeight())
			require.Equal(t, strings.ToUpper(hex.EncodeToString(f.f.commits[101].AppHash)), e.AppHash())
			require.NotEqual(t, strings.ToUpper(hex.EncodeToString(f.f.commits[100].AppHash)), e.AppHash())
			require.Equal(t, strings.ToUpper(hex.EncodeToString(f.f.commits[101].Hash())), e.BlockHash())
			require.True(t, e.FreshAt(f.f.now))
			require.False(t, e.FreshAt(f.f.now.Add(31*time.Second)))
			require.False(t, e.CreditAuthorized())
			require.False(t, (AuthenticatedBankEvidence{}).FreshAt(f.f.now))
			b, err := json.Marshal(e)
			require.NoError(t, err)
			require.Equal(t, `{}`, string(b))
			b, err = json.Marshal(p)
			require.NoError(t, err)
			decoded, err := DecodeBankProof(b)
			require.NoError(t, err)
			v, err := NewProofVerifier(fixtureAnchor(f.f))
			require.NoError(t, err)
			v.now = func() time.Time { return f.f.now }
			offline, err := v.VerifyBankProof(context.Background(), vault, 100, decoded)
			require.NoError(t, err)
			require.Equal(t, want, offline.BalanceUWolo())
			require.True(t, offline.FreshAt(f.f.now))
		})
	}
}

func TestBankProofRejectsUncommittedOrSubstitutedState(t *testing.T) {
	f := newNativeBankFixture(t)
	_, proof, err := f.reader(t, nil).ReadBankProof(context.Background(), f.vault, 100)
	require.NoError(t, err)
	for _, test := range []struct {
		name   string
		change func(*BankProof)
	}{
		{"wrong_chain", func(p *BankProof) { p.ChainID = "not-wolo" }},
		{"wrong_denom", func(p *BankProof) { p.Denom = "stake" }},
		{"wrong_address", func(p *BankProof) { p.Address = f.absent }},
		{"wrong_height", func(p *BankProof) { p.Height = 101 }},
		{"wrong_query_key", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.Key[len(q.Key)-1] ^= 1 }) }},
		{"wrong_response_height", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.Height = 101 }) }},
		{"failed_query", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.Code = 7 }) }},
		{"modified_value", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.Value = []byte("9000000") }) }},
		{"false_zero", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.Value = nil }) }},
		{"missing_proof", func(p *BankProof) { mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps = nil }) }},
		{"modified_iavl", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops[0].Data[0] ^= 1 })
		}},
		{"modified_multistore", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops[1].Data[0] ^= 1 })
		}},
		{"wrong_multistore_key", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops[1].Key = []byte("staking") })
		}},
		{"unsupported_proof_type", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops[0].Type = "iavl:v" })
		}},
		{"extra_op", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops = append(q.ProofOps.Ops, q.ProofOps.Ops[0]) })
		}},
		{"oversized_op", func(p *BankProof) {
			mutateBankQuery(t, p, func(q *abci.ResponseQuery) { q.ProofOps.Ops[0].Data = bytes.Repeat([]byte{1}, 65537) })
		}},
		{"unused_response", func(p *BankProof) { p.Responses = append(p.Responses, p.Responses[0]) }},
		{"duplicate_query", func(p *BankProof) {
			for _, r := range p.Responses {
				if r.Path == "/abci_query" {
					p.Responses = append(p.Responses, r)
					return
				}
			}
		}},
		{"query_without_prove", func(p *BankProof) {
			for n, r := range p.Responses {
				if r.Path == "/abci_query" {
					q, _ := url.ParseQuery(r.Query)
					q.Set("prove", "false")
					p.Responses[n].Query = q.Encode()
				}
			}
		}},
		{"modified_signed_root", func(p *BankProof) {
			for n, r := range p.Responses {
				if r.Path == "/commit" && r.Query == "height=101" {
					var env map[string]any
					require.NoError(t, json.Unmarshal(r.Body, &env))
					env["result"].(map[string]any)["signed_header"].(map[string]any)["header"].(map[string]any)["app_hash"] = strings.Repeat("AA", 32)
					p.Responses[n].Body, _ = json.Marshal(env)
				}
			}
		}},
		{"unbound_witness_status_hash", func(p *BankProof) {
			for n, r := range p.Responses {
				if r.Source == "witness" && r.Path == "/status" {
					var env map[string]any
					require.NoError(t, json.Unmarshal(r.Body, &env))
					env["result"].(map[string]any)["sync_info"].(map[string]any)["latest_block_hash"] = strings.Repeat("AA", 32)
					p.Responses[n].Body, _ = json.Marshal(env)
				}
			}
		}},
		{"unbound_witness_status_time", func(p *BankProof) {
			for n, r := range p.Responses {
				if r.Source == "witness" && r.Path == "/status" {
					var env map[string]any
					require.NoError(t, json.Unmarshal(r.Body, &env))
					env["result"].(map[string]any)["sync_info"].(map[string]any)["latest_block_time"] = f.f.now.Add(-time.Second).Format(time.RFC3339Nano)
					p.Responses[n].Body, _ = json.Marshal(env)
				}
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			p := cloneBankProof(t, proof)
			test.change(&p)
			v, _ := NewProofVerifier(fixtureAnchor(f.f))
			v.now = func() time.Time { return f.f.now }
			e, err := v.VerifyBankProof(context.Background(), f.vault, 100, p)
			require.Error(t, err)
			require.False(t, e.FreshAt(f.f.now))
		})
	}
}

func TestBankProofTrustFreshnessAndResourceLimits(t *testing.T) {
	f := newNativeBankFixture(t)
	_, proof, err := f.reader(t, nil).ReadBankProof(context.Background(), f.vault, 100)
	require.NoError(t, err)
	t.Run("foreign_root", func(t *testing.T) {
		a := fixtureAnchor(f.f)
		a.Hash = strings.Repeat("A", 64)
		v, _ := NewProofVerifier(a)
		v.now = func() time.Time { return f.f.now }
		_, err := v.VerifyBankProof(context.Background(), f.vault, 100, proof)
		require.Error(t, err)
	})
	t.Run("nil_context", func(t *testing.T) {
		r := f.reader(t, nil)
		_, _, err := r.ReadBankProof(nil, f.vault, 100)
		require.Error(t, err)
		_, err = r.readBank(nil, f.vault, 100)
		require.Error(t, err)
		v, _ := NewProofVerifier(fixtureAnchor(f.f))
		_, err = v.VerifyBankProof(nil, f.vault, 100, proof)
		require.Error(t, err)
	})
	t.Run("omitted_zero_success_code", func(t *testing.T) {
		p := cloneBankProof(t, proof)
		for n, r := range p.Responses {
			if r.Path == "/abci_query" {
				var env map[string]any
				require.NoError(t, json.Unmarshal(r.Body, &env))
				delete(env["result"].(map[string]any)["response"].(map[string]any), "code")
				p.Responses[n].Body, _ = json.Marshal(env)
			}
		}
		v, _ := NewProofVerifier(fixtureAnchor(f.f))
		v.now = func() time.Time { return f.f.now }
		e, err := v.VerifyBankProof(context.Background(), f.vault, 100, p)
		require.NoError(t, err)
		require.Equal(t, "7000000", e.BalanceUWolo())
	})
	t.Run("replayed_stale", func(t *testing.T) {
		v, _ := NewProofVerifier(fixtureAnchor(f.f))
		v.now = func() time.Time { return f.f.now.Add(31 * time.Second) }
		_, err := v.VerifyBankProof(context.Background(), f.vault, 100, proof)
		require.Error(t, err)
	})
	t.Run("canceled", func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		v, _ := NewProofVerifier(fixtureAnchor(f.f))
		_, err := v.VerifyBankProof(ctx, f.vault, 100, proof)
		require.ErrorIs(t, err, context.Canceled)
	})
	t.Run("height_overflow", func(t *testing.T) {
		_, _, err := f.reader(t, nil).ReadBankProof(context.Background(), f.vault, math.MaxInt64)
		require.Error(t, err)
	})
	t.Run("bounds_before_decoder", func(t *testing.T) {
		_, err := DecodeBankProof(bytes.Repeat([]byte(" "), MaxPortableProofBytes+1))
		require.Error(t, err)
		p := cloneBankProof(t, proof)
		p.Responses = make([]ProofResponse, 81)
		v, _ := NewProofVerifier(fixtureAnchor(f.f))
		_, err = v.VerifyBankProof(context.Background(), f.vault, 100, p)
		require.Error(t, err)
	})
	t.Run("freshness_expires_during_io", func(t *testing.T) {
		var once atomic.Bool
		var clock atomic.Int64
		clock.Store(f.f.now.UnixNano())
		r := f.reader(t, func(_ *http.Request, b []byte) []byte {
			if once.CompareAndSwap(false, true) {
				clock.Add(int64(31 * time.Second))
			}
			return b
		})
		r.reader.now = func() time.Time { return time.Unix(0, clock.Load()) }
		_, _, err := r.ReadBankProof(context.Background(), f.vault, 100)
		require.Error(t, err)
	})
}

func TestNativeBankAmountCompatibilityIsExactAndBounded(t *testing.T) {
	legacyCoin := sdk.NewInt64Coin(Denom, 7)
	legacy, err := legacyCoin.Marshal()
	require.NoError(t, err)
	for _, b := range [][]byte{[]byte("7"), legacy} {
		n, err := nativeBankAmount(b)
		require.NoError(t, err)
		require.Equal(t, "7", n)
	}
	wrongCoin := sdk.NewInt64Coin("stake", 7)
	wrongDenom, err := wrongCoin.Marshal()
	require.NoError(t, err)
	for _, b := range [][]byte{[]byte("-1"), []byte("01"), []byte("9223372036854775808"), []byte("1e9"), wrongDenom, append(legacy, 0x18, 0x01)} {
		_, err := nativeBankAmount(b)
		require.Error(t, err)
	}
}
