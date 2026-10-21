package satchelservice

// This qualifies the real private HTTP, encrypted SDK keyring and durable
// engine together. A separate test process is killed after an in-memory SDK
// commit, before the broadcast acknowledgement. The validator, funds, approval
// authorities and signed execution permit below have isolated test authority
// only; none is production custody certification or an independent operator.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"cosmossdk.io/collections"
	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmtversion "github.com/cometbft/cometbft/proto/tendermint/version"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	cmtversioninfo "github.com/cometbft/cometbft/version"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	distrtypes "github.com/cosmos/cosmos-sdk/x/distribution/types"
	"github.com/emaren/wolochain/app"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

const nativeHTTPChildEnv = "SATCHEL_TEST_NATIVE_HTTP_CHILD"

type nativeHTTPChildConfig struct {
	ConfigPath, ReadyPath, CountsPath string
}

type nativeHTTPCounts struct {
	Signs, Broadcasts, Confirmations int32
	DurableFenceObserved             bool
}

// Observability wraps, rather than substitutes for, native signing/transport.
type nativeHTTPBackend struct {
	*observedNativeBackend
	engine     *Engine
	countsPath string
	fenced     bool
}

func (b *nativeHTTPBackend) counts() error {
	data, err := json.Marshal(nativeHTTPCounts{b.signs.Load(), b.broadcasts.Load(), b.confirmations.Load(), b.fenced})
	if err != nil {
		return err
	}
	if err = os.WriteFile(b.countsPath+".tmp", data, 0600); err != nil {
		return err
	}
	return os.Rename(b.countsPath+".tmp", b.countsPath)
}

func (b *nativeHTTPBackend) Sign(ctx context.Context, r TransferRequest) (SignedTransaction, error) {
	signed, err := b.observedNativeBackend.Sign(ctx, r)
	if countErr := b.counts(); countErr != nil {
		return SignedTransaction{}, countErr
	}
	return signed, err
}

func (b *nativeHTTPBackend) Broadcast(ctx context.Context, s SignedTransaction) (BroadcastResult, error) {
	if err := b.engine.db.View(func(tx *bolt.Tx) error {
		id := string(tx.Bucket(meta).Get([]byte("active")))
		r, err := load(tx, id)
		if err != nil || r.Result.Status != "UNKNOWN" || r.Result.Reason != "broadcast_started" || !bytes.Equal(r.Signed.Bytes, s.Bytes) {
			return fmt.Errorf("native test broadcast preceded its durable fence")
		}
		return nil
	}); err != nil {
		return BroadcastResult{}, err
	}
	b.fenced = true
	b.broadcasts.Add(1)
	if err := b.counts(); err != nil {
		return BroadcastResult{}, err
	}
	return b.KeyringBackend.Broadcast(ctx, s)
}

func (b *nativeHTTPBackend) Confirm(ctx context.Context, r TransferRequest, s SignedTransaction) (Confirmation, error) {
	b.confirmations.Add(1)
	if err := b.counts(); err != nil {
		return Confirmation{}, err
	}
	return b.KeyringBackend.Confirm(ctx, r, s)
}

// Same evidence-only delegation as the command's serviceEngine. No signing or
// accounting implementation is replaced by this test adapter.
type nativeHTTPProofEngine struct {
	*Engine
	reader *satchel.TrustedReader
}

func (e *nativeHTTPProofEngine) DepositProof(ctx context.Context, r DepositProofRequest) (FinancialProof, error) {
	return e.Engine.DepositProof(ctx, r, e.reader)
}
func (e *nativeHTTPProofEngine) OperationProof(ctx context.Context, id string) (FinancialProof, error) {
	return e.Engine.OperationProof(ctx, id, e.reader)
}
func (e *nativeHTTPProofEngine) ReturnProof(ctx context.Context, id string) (FinancialProof, error) {
	return e.Engine.ReturnProof(ctx, id, e.reader)
}
func (e *nativeHTTPProofEngine) BankProof(ctx context.Context) (satchel.BankProof, error) {
	return e.Engine.BankProof(ctx, e.reader)
}

func nativeHTTPBinaryDigest(t *testing.T) string {
	t.Helper()
	path, err := os.Executable()
	require.NoError(t, err)
	f, err := os.Open(path)
	require.NoError(t, err)
	defer f.Close()
	h := sha256.New()
	_, err = io.Copy(h, f)
	require.NoError(t, err)
	return hex.EncodeToString(h.Sum(nil))
}

func nativeHTTPBackendConfig(c Config, policy Policy) BackendConfig {
	return BackendConfig{RPC: c.RPC, REST: c.REST, WitnessRPC: c.WitnessRPC, Vault: c.Vault, PublicKeyHex: c.PublicKeyHex,
		KeyringDir: c.KeyringDir, KeyName: c.KeyName, PassphraseFile: c.PassphraseFile, FeesUWolo: c.FeesUWolo,
		MaxAmountUWolo: strconv.FormatUint(c.MaxAmountUWolo, 10), GasLimit: c.GasLimit, TimeoutBlocks: c.TimeoutBlocks,
		ApprovedDestinations: []string{c.BettingEscrow}, ProtectedAddresses: c.ProtectedAddresses, WagerVerifier: policy.VerifyWager}
}

func runNativeHTTPChild(t *testing.T, encoded string) {
	t.Helper()
	var child nativeHTTPChildConfig
	require.NoError(t, json.Unmarshal([]byte(encoded), &child))
	c, digest, err := LoadConfig(child.ConfigPath)
	require.NoError(t, err)
	binaryDigest := nativeHTTPBinaryDigest(t)
	authorized := func(context.Context) bool { return VerifyPermit(c, digest, binaryDigest) }
	require.True(t, authorized(t.Context()), "only the isolated signed test permit may open the test service")
	reader, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: c.RPC, REST: c.REST, WitnessRPC: c.WitnessRPC}, c.TrustAnchor)
	require.NoError(t, err)
	defer reader.Close()
	require.NoError(t, reader.CheckTrust(t.Context()))
	approval, err := hex.DecodeString(c.WithdrawalApprovalKeyHex)
	require.NoError(t, err)
	wager, err := hex.DecodeString(c.WagerApprovalKeyHex)
	require.NoError(t, err)
	policy := Policy{Vault: c.Vault, BettingEscrow: c.BettingEscrow, ProtectedAddresses: c.ProtectedAddresses,
		MaxAmountUWolo: c.MaxAmountUWolo, WithdrawalApprovalKey: approval, WagerApprovalKey: wager}
	backendConfig := nativeHTTPBackendConfig(c, policy)
	backendConfig.ConfirmTransaction = func(ctx context.Context, r TransferRequest, signed SignedTransaction) (Confirmation, error) {
		e, err := reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, signed.Hash)
		if err != nil {
			return Confirmation{Status: "UNKNOWN"}, err
		}
		if !e.ConsensusAuthenticated() || e.CreditAuthorized() || !bytes.Equal(e.Observation().TxBytes, signed.Bytes) {
			return Confirmation{Status: "UNKNOWN"}, fmt.Errorf("native test authenticated transaction mismatch")
		}
		return Confirmation{Status: "CONFIRMED", ReceiptID: e.Receipt().ID(), Height: e.Observation().Height, BlockHash: e.Observation().BlockHash}, nil
	}
	native, err := NewKeyringBackend(backendConfig)
	require.NoError(t, err)
	defer native.Close()
	backend := &nativeHTTPBackend{observedNativeBackend: &observedNativeBackend{KeyringBackend: native}, countsPath: child.CountsPath}
	engine, err := Open(c.StatePath, policy, backend)
	require.NoError(t, err)
	defer engine.Close()
	backend.engine = engine
	require.NoError(t, backend.counts())
	public, err := hex.DecodeString(c.PublicKeyHex)
	require.NoError(t, err)
	fingerprint := sha256.Sum256(public)
	token, err := ReadPrivateFile(c.TokenFile, 1024)
	require.NoError(t, err)
	handler, err := NewHTTPHandler(&nativeHTTPProofEngine{Engine: engine, reader: reader}, HTTPConfig{Token: string(token), Accepting: true, Authorize: authorized,
		Health: HTTPHealth{Accepting: true, VaultAddress: c.Vault, KeyFingerprint: hex.EncodeToString(fingerprint[:]), BuildSHA256: binaryDigest, ExclusiveAuthorityVerified: true}})
	require.NoError(t, err)
	server, err := NewPrivateHTTPServer("127.0.0.1:0", handler)
	require.NoError(t, err)
	listener, err := net.Listen("tcp", server.Addr)
	require.NoError(t, err)
	defer listener.Close()
	require.NoError(t, os.WriteFile(child.ReadyPath, []byte("http://"+listener.Addr().String()), 0600))
	require.ErrorIs(t, server.Serve(listener), http.ErrServerClosed)
}

type nativeHTTPProcess struct {
	command *exec.Cmd
	done    chan error
	output  bytes.Buffer
	stopped bool
}

func startNativeHTTPProcess(t *testing.T, child nativeHTTPChildConfig) (*nativeHTTPProcess, string) {
	t.Helper()
	require.NoError(t, os.RemoveAll(child.ReadyPath))
	encoded, err := json.Marshal(child)
	require.NoError(t, err)
	p := &nativeHTTPProcess{done: make(chan error, 1)}
	p.command = exec.Command(os.Args[0], "-test.run=^TestNativePrivateHTTPServiceSDKRecovery$", "-test.count=1", "-test.timeout=60s")
	p.command.Env = append(os.Environ(), nativeHTTPChildEnv+"="+string(encoded))
	p.command.Stdout, p.command.Stderr = &p.output, &p.output
	require.NoError(t, p.command.Start())
	go func() { p.done <- p.command.Wait() }()
	t.Cleanup(func() { p.kill(t) })
	timeout := time.NewTimer(15 * time.Second)
	defer timeout.Stop()
	tick := time.NewTicker(10 * time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case err := <-p.done:
			p.stopped = true
			t.Fatalf("isolated native service exited before readiness: %v: %s", err, p.output.String())
		case <-timeout.C:
			p.kill(t)
			t.Fatalf("isolated native service startup timed out: %s", p.output.String())
		case <-tick.C:
			data, err := os.ReadFile(child.ReadyPath)
			if err == nil && strings.HasPrefix(string(data), "http://127.0.0.1:") {
				return p, string(data)
			}
		}
	}
}

func (p *nativeHTTPProcess) kill(t *testing.T) {
	t.Helper()
	if !p.stopped {
		require.NoError(t, p.command.Process.Kill())
		<-p.done
		p.stopped = true
	}
}

// This RPC fixture serves actual SDK execution results, transaction bytes,
// retained IAVL proofs and correctly signed continuous Comet headers. The two
// local servers share one isolated validator; they do not claim independence.
type nativeHTTPChain struct {
	mu          sync.Mutex
	application *app.App
	validator   cmted.PrivKey
	validators  *cmt.ValidatorSet
	commits     map[int64]*core.ResultCommit
	results     map[int64]*core.ResultBlockResults
	transaction *core.ResultTx
	rest        any
	appHash     []byte
	lastResults []*abci.ExecTxResult
	head        int64
	start       time.Time
	vault       sdk.AccAddress
	bankKey     []byte
	broadcasts  int
	executed    chan struct{}
	releaseACK  chan struct{}
	ackReleased sync.Once
}

func newNativeHTTPChain(t *testing.T, signer *testBackendSigner) *nativeHTTPChain {
	t.Helper()
	options := viper.New()
	options.Set(flags.FlagHome, t.TempDir())
	application := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, options, baseapp.SetChainID(satchel.ChainID))
	t.Cleanup(func() { require.NoError(t, application.Close()) })
	validator := cmted.GenPrivKeyFromSecret([]byte("native-private-http-sdk-validator-test-only"))
	validators := cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(validator.PubKey(), 10)})
	vault := sdk.AccAddress(signer.key.PubKey().Address())
	genesis, err := simtestutil.GenesisStateWithValSet(application.AppCodec(), application.DefaultGenesis(), validators,
		[]authtypes.GenesisAccount{authtypes.NewBaseAccount(vault, signer.key.PubKey(), 0, 0)},
		banktypes.Balance{Address: vault.String(), Coins: sdk.NewCoins(sdk.NewCoin(satchel.Denom, sdkmath.NewInt(10000000)))})
	require.NoError(t, err)
	state, err := cmtjson.Marshal(genesis)
	require.NoError(t, err)
	start := time.Now().UTC().Add(-2 * time.Second)
	init, err := application.InitChain(&abci.RequestInitChain{ChainId: satchel.ChainID, Time: start, AppStateBytes: state, ConsensusParams: simtestutil.DefaultConsensusParams})
	require.NoError(t, err)
	key, err := collections.EncodeKeyWithPrefix(banktypes.BalancesPrefix, collections.PairKeyCodec(sdk.AccAddressKey, collections.StringKey), collections.Join(vault, satchel.Denom))
	require.NoError(t, err)
	f := &nativeHTTPChain{application: application, validator: validator, validators: validators, vault: vault, bankKey: key,
		commits: map[int64]*core.ResultCommit{}, results: map[int64]*core.ResultBlockResults{}, appHash: init.AppHash,
		start: start, executed: make(chan struct{}), releaseACK: make(chan struct{})}
	f.commit(t, nil)
	return f
}

func (f *nativeHTTPChain) release() { f.ackReleased.Do(func() { close(f.releaseACK) }) }

func (f *nativeHTTPChain) commit(t *testing.T, txs [][]byte) *abci.ResponseFinalizeBlock {
	t.Helper()
	f.head++
	cometTxs := make(cmt.Txs, len(txs))
	for n, data := range txs {
		cometTxs[n] = cmt.Tx(data)
	}
	h := &cmt.Header{Version: cmtversion.Consensus{Block: cmtversioninfo.BlockProtocol}, ChainID: satchel.ChainID, Height: f.head,
		Time: f.start.Add(time.Duration(f.head) * 10 * time.Millisecond), ValidatorsHash: f.validators.Hash(), NextValidatorsHash: f.validators.Hash(),
		ConsensusHash: bytes.Repeat([]byte{2}, 32), AppHash: f.appHash, ProposerAddress: f.validator.PubKey().Address(), DataHash: cometTxs.Hash(), LastResultsHash: cmt.NewResults(f.lastResults).Hash()}
	if f.head > 1 {
		h.LastBlockID, h.LastCommitHash = f.commits[f.head-1].Commit.BlockID, f.commits[f.head-1].Commit.Hash()
	}
	id := cmt.BlockID{Hash: h.Hash(), PartSetHeader: cmt.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
	vote := cmtproto.Vote{Type: cmtproto.PrecommitType, Height: f.head, BlockID: id.ToProto(), Timestamp: h.Time, ValidatorAddress: f.validator.PubKey().Address()}
	signature, err := f.validator.Sign(cmt.VoteSignBytes(satchel.ChainID, &vote))
	require.NoError(t, err)
	commit := &cmt.Commit{Height: f.head, BlockID: id, Signatures: []cmt.CommitSig{{BlockIDFlag: cmt.BlockIDFlagCommit, ValidatorAddress: f.validator.PubKey().Address(), Timestamp: h.Time, Signature: signature}}}
	f.commits[f.head] = core.NewResultCommit(h, commit, true)
	result, err := f.application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: f.head, Hash: id.Hash, Time: h.Time, NextValidatorsHash: f.validators.Hash(), Txs: txs})
	require.NoError(t, err)
	_, err = f.application.Commit()
	require.NoError(t, err)
	f.results[f.head] = &core.ResultBlockResults{Height: f.head, TxsResults: result.TxResults}
	f.lastResults, f.appHash = result.TxResults, result.AppHash
	return result
}

func (f *nativeHTTPChain) serve(t *testing.T, witness bool) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		var value any
		h, _ := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
		switch r.URL.Path {
		case "/":
			require.False(t, witness, "witness must remain read-only")
			require.Equal(t, http.MethodPost, r.Method)
			var request struct {
				Method string
				Params map[string]string
			}
			require.NoError(t, json.NewDecoder(r.Body).Decode(&request))
			require.Equal(t, "broadcast_tx_sync", request.Method)
			data, err := base64.StdEncoding.Strict().DecodeString(request.Params["tx"])
			require.NoError(t, err)
			f.broadcasts++
			result := f.commit(t, [][]byte{data})
			require.Len(t, result.TxResults, 1)
			require.Zero(t, result.TxResults[0].Code, result.TxResults[0].Log)
			tx := cmt.Tx(data)
			hash := strings.ToUpper(hex.EncodeToString(tx.Hash()))
			f.transaction = &core.ResultTx{Hash: tx.Hash(), Height: f.head, Index: 0, TxResult: *result.TxResults[0], Tx: tx, Proof: cmt.Txs{tx}.Proof(0)}
			var raw txapi.TxRaw
			var body txapi.TxBody
			require.NoError(t, proto.Unmarshal(data, &raw))
			require.NoError(t, proto.Unmarshal(raw.BodyBytes, &body))
			bodyJSON, err := protojson.Marshal(&body)
			require.NoError(t, err)
			var bodyObject map[string]any
			require.NoError(t, json.Unmarshal(bodyJSON, &bodyObject))
			resultJSON, err := json.Marshal(result.TxResults[0])
			require.NoError(t, err)
			var resultObject map[string]any
			require.NoError(t, json.Unmarshal(resultJSON, &resultObject))
			resultObject["height"], resultObject["txhash"], resultObject["timestamp"], resultObject["logs"] = strconv.FormatInt(f.head, 10), hash, f.commits[f.head].Time.Format(time.RFC3339Nano), []any{}
			delete(resultObject, "code") // Actual successful Cosmos zero-code omission.
			f.rest = map[string]any{"tx": map[string]any{"body": bodyObject}, "tx_response": resultObject}
			for i := 0; i < 3; i++ {
				f.commit(t, nil)
			}
			close(f.executed)
			<-f.releaseACK // The parent kills only the isolated signer process here.
			_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"hash": hash}})
			return
		case "/status":
			status := core.ResultStatus{}
			status.NodeInfo.Network = satchel.ChainID
			status.SyncInfo.LatestBlockHeight, status.SyncInfo.LatestBlockHash, status.SyncInfo.LatestBlockTime = f.head, f.commits[f.head].Header.Hash(), f.commits[f.head].Time
			value = status
		case "/commit":
			value = f.commits[h]
		case "/validators":
			require.Equal(t, "1", r.URL.Query().Get("page"))
			require.Equal(t, "100", r.URL.Query().Get("per_page"))
			value = &core.ResultValidators{BlockHeight: h, Validators: f.validators.Validators, Count: len(f.validators.Validators), Total: len(f.validators.Validators)}
		case "/tx":
			require.Equal(t, "true", r.URL.Query().Get("prove"))
			require.Equal(t, "0x"+hex.EncodeToString(f.transaction.Hash), strings.ToLower(r.URL.Query().Get("hash")))
			value = f.transaction
		case "/block_results":
			value = f.results[h]
		case "/abci_query":
			require.Equal(t, strconv.Quote("/store/bank/key"), r.URL.Query().Get("path"))
			require.Equal(t, "0x"+strings.ToUpper(hex.EncodeToString(f.bankKey)), r.URL.Query().Get("data"))
			require.Equal(t, "true", r.URL.Query().Get("prove"))
			query, err := f.application.Query(r.Context(), &abci.RequestQuery{Path: "/store/bank/key", Data: f.bankKey, Height: h, Prove: true})
			require.NoError(t, err)
			require.Zero(t, query.Code, query.Log)
			value = core.ResultABCIQuery{Response: *query}
		case "/cosmos/auth/v1beta1/accounts/" + f.vault.String():
			ctx := f.application.NewUncachedContext(false, cmtproto.Header{Height: f.head})
			account := f.application.AuthKeeper.GetAccount(ctx, f.vault)
			require.NotNil(t, account)
			_ = json.NewEncoder(w).Encode(map[string]any{"account": map[string]any{"@type": "/cosmos.auth.v1beta1.BaseAccount", "address": f.vault.String(),
				"account_number": strconv.FormatUint(account.GetAccountNumber(), 10), "sequence": strconv.FormatUint(account.GetSequence(), 10),
				"pub_key": map[string]string{"@type": "/cosmos.crypto.secp256k1.PubKey", "key": base64.StdEncoding.EncodeToString(account.GetPubKey().Bytes())}}})
			return
		default:
			require.Equal(t, "/cosmos/tx/v1beta1/txs/"+strings.ToUpper(hex.EncodeToString(f.transaction.Hash)), r.URL.Path)
			_ = json.NewEncoder(w).Encode(f.rest)
			return
		}
		require.Equal(t, http.MethodGet, r.Method)
		encoded, err := cmtjson.Marshal(value)
		require.NoError(t, err)
		_, _ = fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, encoded)
	}))
	t.Cleanup(func() { f.release(); server.Close() })
	return server
}

func nativeHTTPWire(t *testing.T, url, path string, body any, token string) (int, []byte, error) {
	t.Helper()
	var data []byte
	var err error
	method := http.MethodGet
	if body != nil {
		method = http.MethodPost
		data, err = json.Marshal(body)
		require.NoError(t, err)
	}
	request, err := http.NewRequestWithContext(t.Context(), method, url+path, bytes.NewReader(data))
	require.NoError(t, err)
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 8 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return 0, nil, err
	}
	defer response.Body.Close()
	data, err = io.ReadAll(io.LimitReader(response.Body, int64(MaxFinancialProofBytes)+1))
	return response.StatusCode, data, err
}

func nativeHTTPWager(r TransferRequest) map[string]any {
	return map[string]any{"protocol": 2, "request_id": r.OperationID, "chain_id": r.ChainID, "signer_role": httpCustodyRole,
		"from_address": r.Sender, "to_address": r.Recipient, "amount": httpCoin{Denom: r.Denom, Amount: r.AmountUWolo}, "memo": r.Memo, "owner_id": r.OwnerID, "reservation": r.Reservation}
}

func readNativeHTTPCounts(t *testing.T, path string) nativeHTTPCounts {
	t.Helper()
	data, err := os.ReadFile(path)
	require.NoError(t, err)
	var counts nativeHTTPCounts
	require.NoError(t, json.Unmarshal(data, &counts))
	return counts
}

func TestNativePrivateHTTPServiceSDKRecovery(t *testing.T) {
	if encoded := os.Getenv(nativeHTTPChildEnv); encoded != "" {
		runNativeHTTPChild(t, encoded)
		return
	}
	backendConfig, oldFixture := isolatedBackendConfig(t)
	chain := newNativeHTTPChain(t, oldFixture.signer)
	primary, witness := chain.serve(t, false), chain.serve(t, true)
	directory, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	require.NoError(t, os.Chmod(directory, 0700))
	activationKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, ed25519.SeedSize))
	c := Config{Version: 1, RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL, Vault: backendConfig.Vault, PublicKeyHex: backendConfig.PublicKeyHex,
		BettingEscrow: backendConfig.ApprovedDestinations[0], ProtectedAddresses: backendConfig.ApprovedDestinations, MaxAmountUWolo: 1000000000,
		KeyringDir: backendConfig.KeyringDir, KeyName: backendConfig.KeyName, PassphraseFile: backendConfig.PassphraseFile, FeesUWolo: backendConfig.FeesUWolo,
		GasLimit: backendConfig.GasLimit, TimeoutBlocks: backendConfig.TimeoutBlocks, TokenFile: filepath.Join(directory, "token"), StatePath: filepath.Join(directory, "journal.db"), PermitFile: filepath.Join(directory, "permit.json"),
		WithdrawalApprovalKeyHex: hex.EncodeToString(engineTestApprovalKey().Public().(ed25519.PublicKey)), WagerApprovalKeyHex: hex.EncodeToString(engineTestWagerApprovalKey().Public().(ed25519.PublicKey)),
		ActivationAuthorityKeyHex: hex.EncodeToString(activationKey.Public().(ed25519.PublicKey)),
		TrustAnchor:               satchel.TrustAnchor{Height: 1, Hash: hex.EncodeToString(chain.commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "isolated-native-private-http-sdk-test-only"}}
	child := nativeHTTPChildConfig{ConfigPath: filepath.Join(directory, "config.json"), ReadyPath: filepath.Join(directory, "ready"), CountsPath: filepath.Join(directory, "counts.json")}
	configJSON, err := json.Marshal(c)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(child.ConfigPath, configJSON, 0600))
	require.NoError(t, os.WriteFile(c.TokenFile, []byte(testHTTPToken), 0600))
	_, configDigest, err := LoadConfig(child.ConfigPath)
	require.NoError(t, err)
	fixtureDigest := sha256.Sum256([]byte("isolated fixture evidence only: never live financial authority"))
	permit := ExecutionPermit{Version: 1, Scope: "satchel-execution-v1", ConfigSHA256: configDigest, BinarySHA256: nativeHTTPBinaryDigest(t), Vault: c.Vault,
		IsolationEvidenceSHA256: hex.EncodeToString(fixtureDigest[:]), AccountingEvidenceSHA256: hex.EncodeToString(fixtureDigest[:]), RecoveryEvidenceSHA256: hex.EncodeToString(fixtureDigest[:]),
		Reviewer: "isolated-test-only", Reference: "synthetic SDK funds; no production activation or solvency claim", IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Unix() + 120}
	permit.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(activationKey, PermitMessage(permit)))
	permitJSON, err := json.Marshal(permit)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(c.PermitFile, permitJSON, 0600))
	process, url := startNativeHTTPProcess(t, child)
	request := oldFixture.request
	for _, mode := range []string{"bearer", "role", "owner", "recipient", "amount", "fee", "approval_role"} {
		t.Run("reject_"+mode, func(t *testing.T) {
			var r TransferRequest
			data, err := json.Marshal(request)
			require.NoError(t, err)
			require.NoError(t, json.Unmarshal(data, &r))
			wire, token := nativeHTTPWager(r), testHTTPToken
			switch mode {
			case "bearer":
				token = strings.Repeat("Z", 64)
			case "role":
				wire["signer_role"] = "legacy-betting-escrow"
			case "owner":
				wire["owner_id"] = "another-owner"
			case "recipient":
				wire["to_address"] = c.Vault
			case "amount":
				wire["amount"] = httpCoin{Denom: "uwolo", Amount: "8000000"}
			case "fee":
				r.Reservation.FeeUWolo = "1"
			case "approval_role":
				r.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestApprovalKey(), WagerReservationMessage(*r.Reservation)))
			}
			status, _, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", wire, token)
			require.NoError(t, err)
			require.GreaterOrEqual(t, status, 400)
			require.Equal(t, nativeHTTPCounts{}, readNativeHTTPCounts(t, child.CountsPath), "invalid wire reached the actual signer")
		})
	}
	competing, err := NewKeyringBackend(nativeHTTPBackendConfig(c, Policy{}))
	if competing != nil {
		competing.Close()
	}
	require.Error(t, err, "another process obtained the running HTTP service's private keyring")
	requestDone := make(chan error, 1)
	go func() {
		_, _, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(request), testHTTPToken)
		requestDone <- err
	}()
	select {
	case <-chain.executed:
	case <-time.After(10 * time.Second):
		t.Fatal("native HTTP transaction did not reach actual SDK execution")
	}
	require.Equal(t, nativeHTTPCounts{Signs: 1, Broadcasts: 1, DurableFenceObserved: true}, readNativeHTTPCounts(t, child.CountsPath))
	process.kill(t) // SIGKILL, with no Engine.Close or journal/keyring cleanup.
	chain.release()
	require.Error(t, <-requestDone, "killed private HTTP request incorrectly reported a payment acknowledgement")
	db, err := bolt.Open(c.StatePath, 0600, &bolt.Options{ReadOnly: true, Timeout: time.Second})
	require.NoError(t, err)
	var persisted record
	require.NoError(t, db.View(func(tx *bolt.Tx) error { var err error; persisted, err = load(tx, request.OperationID); return err }))
	require.NoError(t, db.Close())
	require.Equal(t, "UNKNOWN", persisted.Result.Status)
	require.Equal(t, "broadcast_started", persisted.Result.Reason)
	require.Equal(t, request, persisted.Request)
	require.Equal(t, []byte(chain.transaction.Tx), persisted.Signed.Bytes)
	require.Equal(t, strings.ToUpper(hex.EncodeToString(chain.transaction.Hash)), persisted.Result.TxHash)
	_, url = startNativeHTTPProcess(t, child)
	type wireResult struct {
		status int
		raw    []byte
		err    error
	}
	duplicates := make(chan wireResult, 4)
	start := make(chan struct{})
	for i := 0; i < cap(duplicates); i++ {
		go func() {
			<-start
			status, raw, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(request), testHTTPToken)
			duplicates <- wireResult{status, raw, err}
		}()
	}
	close(start)
	for i := 0; i < cap(duplicates); i++ {
		out := <-duplicates
		require.NoError(t, out.err)
		require.Equal(t, http.StatusOK, out.status)
		var result Result
		require.NoError(t, json.Unmarshal(out.raw, &result))
		require.Equal(t, persisted.Result, result, "restart renewed or altered the uncertain payment")
	}
	require.Equal(t, nativeHTTPCounts{}, readNativeHTTPCounts(t, child.CountsPath))
	// Revoking fixture execution authority must stop submissions while leaving
	// authenticated proof retrieval and read-only reconciliation available.
	require.NoError(t, os.Remove(c.PermitFile))
	status, _, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(request), testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusServiceUnavailable, status)
	status, heldJournalJSON, err := nativeHTTPWire(t, url, "/satchel/v1/custody/journal", nil, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status)
	var heldJournal CustodyJournal
	require.NoError(t, json.Unmarshal(heldJournalJSON, &heldJournal))
	require.Equal(t, "7000000", heldJournal.HeldOutboundUWolo)
	require.Equal(t, "0", heldJournal.ConfirmedOutboundUWolo)
	require.Equal(t, uint64(1), heldJournal.UnresolvedCount)
	status, proofJSON, err := nativeHTTPWire(t, url, "/satchel/v1/proofs/operation", map[string]string{"operation_id": request.OperationID}, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status, string(proofJSON))
	proof, err := DecodeFinancialProof(proofJSON)
	require.NoError(t, err)
	expected := FinancialProofContext{Protocol: 1, Kind: request.Kind, OwnerID: request.OwnerID, OperationID: request.OperationID,
		Sender: request.Sender, Recipient: request.Recipient, AmountUWolo: request.AmountUWolo, Memo: request.Memo, TxHash: persisted.Result.TxHash, Reservation: request.Reservation}
	authority := FinancialProofVerifierConfig{TrustAnchor: c.TrustAnchor, Vault: c.Vault, BettingEscrow: c.BettingEscrow, ApprovalPublicKeyHex: c.WithdrawalApprovalKeyHex, WagerApprovalPublicKeyHex: c.WagerApprovalKeyHex}
	receipt, err := VerifyFinancialProof(t.Context(), authority, expected, proof)
	require.NoError(t, err)
	require.False(t, receipt.CreditAuthorized)
	require.Equal(t, int64(2), receipt.Height)
	require.Equal(t, uint32(1), receipt.TransferIndex, "actual SDK ante fee precedes bank MsgSend")
	require.Equal(t, persisted.Result.TxHash, receipt.TxHash)
	require.Equal(t, nativeHTTPCounts{}, readNativeHTTPCounts(t, child.CountsPath), "read-only proof retrieval invoked native execution")
	status, unchangedJournalJSON, err := nativeHTTPWire(t, url, "/satchel/v1/custody/journal", nil, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status)
	require.JSONEq(t, string(heldJournalJSON), string(unchangedJournalJSON), "proof retrieval silently released the durable uncertain-payment hold")
	status, raw, err := nativeHTTPWire(t, url, "/satchel/v1/reconcile", map[string]string{"operation_id": request.OperationID}, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status, string(raw))
	var confirmed Result
	require.NoError(t, json.Unmarshal(raw, &confirmed))
	require.Equal(t, "CONFIRMED", confirmed.Status)
	require.Equal(t, persisted.Result.TxHash, confirmed.TxHash)
	require.True(t, confirmed.DurableFenced)
	for i := 0; i < 3; i++ {
		status, _, err := nativeHTTPWire(t, url, "/satchel/v1/reconcile", map[string]string{"operation_id": request.OperationID}, testHTTPToken)
		require.NoError(t, err)
		require.Equal(t, http.StatusOK, status)
	}
	require.Equal(t, nativeHTTPCounts{Confirmations: 1}, readNativeHTTPCounts(t, child.CountsPath))
	chain.mu.Lock()
	replayed := chain.commit(t, [][]byte{persisted.Signed.Bytes})
	require.Len(t, replayed.TxResults, 1)
	require.NotZero(t, replayed.TxResults[0].Code, "real SDK ante handler accepted an identical-byte replay")
	chain.commit(t, nil)
	ctx := chain.application.NewUncachedContext(false, cmtproto.Header{Height: chain.head})
	escrow, err := sdk.AccAddressFromBech32(c.BettingEscrow)
	require.NoError(t, err)
	require.Equal(t, "7000000", chain.application.BankKeeper.GetBalance(ctx, escrow, "uwolo").Amount.String())
	require.Equal(t, "2997500", chain.application.BankKeeper.GetBalance(ctx, chain.vault, "uwolo").Amount.String())
	// BeginBlock moves collected fees into distribution in subsequent blocks.
	// Account for both real module balances instead of inventing extra reserves.
	fees := chain.application.BankKeeper.GetBalance(ctx, authtypes.NewModuleAddress(authtypes.FeeCollectorName), "uwolo").Amount.
		Add(chain.application.BankKeeper.GetBalance(ctx, authtypes.NewModuleAddress(distrtypes.ModuleName), "uwolo").Amount)
	require.Equal(t, "2500", fees.String())
	require.Equal(t, uint64(1), chain.application.AuthKeeper.GetAccount(ctx, chain.vault).GetSequence())
	require.Equal(t, 1, chain.broadcasts)
	chain.mu.Unlock()
	status, bankJSON, err := nativeHTTPWire(t, url, "/satchel/v1/proofs/bank", map[string]int{"protocol": 1}, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status, string(bankJSON))
	bankProof, err := satchel.DecodeBankProof(bankJSON)
	require.NoError(t, err)
	verifier, err := satchel.NewProofVerifier(c.TrustAnchor)
	require.NoError(t, err)
	bank, err := verifier.VerifyBankProof(t.Context(), c.Vault, bankProof.Height, bankProof)
	require.NoError(t, err)
	require.True(t, bank.CurrentAt(time.Now()))
	require.False(t, bank.CreditAuthorized())
	require.Equal(t, "2997500", bank.BalanceUWolo())
	status, journalJSON, err := nativeHTTPWire(t, url, "/satchel/v1/custody/journal", nil, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status)
	var journal CustodyJournal
	require.NoError(t, json.Unmarshal(journalJSON, &journal))
	require.Equal(t, uint64(1), journal.OperationsCount)
	require.Equal(t, "7000000", journal.ConfirmedOutboundUWolo)
	require.Equal(t, "0", journal.HeldOutboundUWolo)
	require.Zero(t, journal.UnresolvedCount)
	require.Equal(t, "UNAVAILABLE", journal.CustodyCapability)
	require.False(t, journal.CreditAuthorized || journal.SolvencyAuthorized || journal.BankBalanceAuthenticated)
	require.Equal(t, nativeHTTPCounts{Confirmations: 1}, readNativeHTTPCounts(t, child.CountsPath))
	require.Zero(t, oldFixture.signer.calls.Load(), "synthetic backend signer was used instead of the real encrypted keyring")
	require.Zero(t, oldFixture.broadcasts.Load(), "synthetic RPC acknowledgements were used instead of actual SDK commits")
	require.False(t, satchel.CurrentCapability().Available())
}
