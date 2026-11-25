package satchelservice

// This integration executes the production engine's actual encrypted-keyring
// transaction in an isolated in-memory WoloChain SDK application. Its httptest
// transport is not a consensus witness, and no production key or chain is used.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmt "github.com/cometbft/cometbft/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/app"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

// Instrument the real backend without replacing its SDK signing, payload
// validation, broadcast transport or confirmation implementation.
type observedNativeBackend struct {
	*KeyringBackend
	signs, broadcasts, confirmations atomic.Int32
}

func (b *observedNativeBackend) Sign(ctx context.Context, r TransferRequest) (SignedTransaction, error) {
	b.signs.Add(1)
	return b.KeyringBackend.Sign(ctx, r)
}
func (b *observedNativeBackend) Broadcast(ctx context.Context, s SignedTransaction) (BroadcastResult, error) {
	b.broadcasts.Add(1)
	return b.KeyringBackend.Broadcast(ctx, s)
}
func (b *observedNativeBackend) Confirm(ctx context.Context, r TransferRequest, s SignedTransaction) (Confirmation, error) {
	b.confirmations.Add(1)
	return b.KeyringBackend.Confirm(ctx, r, s)
}

func TestNativeEngineSDKExecutionRetainsUnknownAfterLostAcknowledgement(t *testing.T) {
	for _, ack := range []string{"dropped", "malformed"} {
		t.Run(ack, func(t *testing.T) {
			cfg, oldFixture := isolatedBackendConfig(t)
			vault := sdk.AccAddress(oldFixture.signer.key.PubKey().Address())
			escrow, err := sdk.AccAddressFromBech32(cfg.ApprovedDestinations[0])
			require.NoError(t, err)
			options := viper.New()
			options.Set(flags.FlagHome, t.TempDir())
			application := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, options, baseapp.SetChainID("wolo-1"))
			defer func() { require.NoError(t, application.Close()) }()
			validators, err := simtestutil.CreateRandomValidatorSet()
			require.NoError(t, err)
			genesis, err := simtestutil.GenesisStateWithValSet(application.AppCodec(), application.DefaultGenesis(), validators,
				[]authtypes.GenesisAccount{authtypes.NewBaseAccount(vault, oldFixture.signer.key.PubKey(), 0, 0)},
				banktypes.Balance{Address: vault.String(), Coins: sdk.NewCoins(sdk.NewCoin("uwolo", sdkmath.NewInt(10000000)))})
			require.NoError(t, err)
			state, err := cmtjson.Marshal(genesis)
			require.NoError(t, err)
			blockTime := time.Now().UTC().Add(-time.Second)
			_, err = application.InitChain(&abci.RequestInitChain{ChainId: "wolo-1", Time: blockTime.Add(-time.Second), AppStateBytes: state, ConsensusParams: simtestutil.DefaultConsensusParams})
			require.NoError(t, err)
			// Commit the initialized accounts before the backend's real REST read.
			_, err = application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: 1, Time: blockTime, NextValidatorsHash: validators.Hash()})
			require.NoError(t, err)
			_, err = application.Commit()
			require.NoError(t, err)
			var mu sync.Mutex
			var executionErr error
			var executedBytes []byte
			var executionCount, rpcBroadcasts atomic.Int32
			var engine *Engine
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				mu.Lock()
				defer mu.Unlock()
				ctx := application.NewUncachedContext(false, cmtproto.Header{Height: application.LastBlockHeight()})
				switch r.URL.Path {
				case "/status":
					// This local header is signing timeout metadata, not authenticated
					// Comet finality or a production chain trust checkpoint.
					header := cmt.Header{ChainID: "wolo-1", Height: application.LastBlockHeight(), Time: blockTime,
						ValidatorsHash: validators.Hash(), NextValidatorsHash: validators.Hash(), AppHash: application.LastCommitID().Hash}
					_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"node_info": map[string]any{"network": "wolo-1"}, "sync_info": map[string]any{"latest_block_height": strconv.FormatInt(application.LastBlockHeight(), 10), "latest_block_hash": strings.ToUpper(hex.EncodeToString(header.Hash())), "latest_block_time": blockTime.Format(time.RFC3339Nano), "catching_up": false}}})
				case "/cosmos/auth/v1beta1/accounts/" + cfg.Vault:
					account := application.AuthKeeper.GetAccount(ctx, vault)
					if account == nil {
						executionErr = fmt.Errorf("actual SDK vault account missing")
						w.WriteHeader(500)
						return
					}
					_ = json.NewEncoder(w).Encode(map[string]any{"account": map[string]any{"@type": "/cosmos.auth.v1beta1.BaseAccount", "address": vault.String(), "account_number": strconv.FormatUint(account.GetAccountNumber(), 10), "sequence": strconv.FormatUint(account.GetSequence(), 10), "pub_key": map[string]string{"@type": "/cosmos.crypto.secp256k1.PubKey", "key": base64.StdEncoding.EncodeToString(account.GetPubKey().Bytes())}}})
				case "/":
					rpcBroadcasts.Add(1)
					var request struct {
						Method string            `json:"method"`
						Params map[string]string `json:"params"`
					}
					if r.Method != http.MethodPost || json.NewDecoder(r.Body).Decode(&request) != nil || request.Method != "broadcast_tx_sync" {
						executionErr = fmt.Errorf("invalid actual backend broadcast wire")
						w.WriteHeader(400)
						return
					}
					data, err := base64.StdEncoding.Strict().DecodeString(request.Params["tx"])
					if err != nil {
						executionErr = err
						w.WriteHeader(400)
						return
					}
					// Independently inspect the journal at the financial boundary:
					// exact bytes and UNKNOWN must exist before SDK execution.
					err = engine.db.View(func(tx *bolt.Tx) error {
						stored, err := load(tx, oldFixture.request.OperationID)
						if err != nil {
							return err
						}
						if stored.Result.Status != "UNKNOWN" || stored.Result.Reason != "broadcast_started" || !bytes.Equal(stored.Signed.Bytes, data) {
							return fmt.Errorf("payment bytes were not durably fenced before execution")
						}
						return nil
					})
					if err != nil {
						executionErr = err
						w.WriteHeader(500)
						return
					}
					blockTime = blockTime.Add(time.Second)
					finalized, err := application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: application.LastBlockHeight() + 1, Time: blockTime, NextValidatorsHash: validators.Hash(), Txs: [][]byte{data}})
					if err != nil || len(finalized.TxResults) != 1 {
						executionErr = fmt.Errorf("SDK FinalizeBlock failed: %v", err)
						w.WriteHeader(500)
						return
					}
					if result := finalized.TxResults[0]; result.Code != 0 {
						executionErr = fmt.Errorf("actual SDK rejected native transaction: code=%d log=%s", result.Code, result.Log)
						w.WriteHeader(500)
						return
					}
					if _, err = application.Commit(); err != nil {
						executionErr = err
						w.WriteHeader(500)
						return
					}
					executionCount.Add(1)
					executedBytes = append([]byte(nil), data...)
					// The bank effect is already committed. Losing this response must
					// never permit another signing or broadcast invocation.
					if ack == "dropped" {
						connection, _, err := w.(http.Hijacker).Hijack()
						if err != nil {
							executionErr = err
							return
						}
						_ = connection.Close()
						return
					}
					_, _ = w.Write([]byte(`{}`))
				default:
					w.WriteHeader(404)
				}
			}))
			defer server.Close()
			cfg.RPC, cfg.REST = server.URL, server.URL
			policy := Policy{Vault: cfg.Vault, BettingEscrow: escrow.String(), ProtectedAddresses: []string{escrow.String()}, MaxAmountUWolo: 1000000000, WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
			cfg.WagerVerifier = policy.VerifyWager
			native, err := NewKeyringBackend(cfg)
			require.NoError(t, err)
			defer native.Close()
			backend := &observedNativeBackend{KeyringBackend: native}
			directory, err := filepath.EvalSymlinks(t.TempDir())
			require.NoError(t, err)
			require.NoError(t, os.Chmod(directory, 0700))
			journalPath := filepath.Join(directory, "native-execution.db")
			engine, err = Open(journalPath, policy, backend)
			require.NoError(t, err)
			defer engine.Close()
			request := oldFixture.request
			result, err := engine.Submit(t.Context(), request)
			require.NoError(t, err)
			mu.Lock()
			require.NoError(t, executionErr)
			require.Equal(t, int32(1), executionCount.Load(), "the SDK must actually execute successfully")
			ctx := application.NewUncachedContext(false, cmtproto.Header{Height: application.LastBlockHeight()})
			require.Equal(t, "7000000", application.BankKeeper.GetBalance(ctx, escrow, "uwolo").Amount.String())
			require.Equal(t, "2997500", application.BankKeeper.GetBalance(ctx, vault, "uwolo").Amount.String(), "exact transfer plus separate 2500uwolo gas fee")
			require.Equal(t, "2500", application.BankKeeper.GetBalance(ctx, authtypes.NewModuleAddress(authtypes.FeeCollectorName), "uwolo").Amount.String())
			require.Equal(t, uint64(1), application.AuthKeeper.GetAccount(ctx, vault).GetSequence())
			actualHash := strings.ToUpper(hex.EncodeToString(cmt.Tx(executedBytes).Hash()))
			mu.Unlock()
			require.Equal(t, "UNKNOWN", result.Status, "committed bank effect cannot repair a lost ACK without authenticated reconciliation")
			require.Equal(t, actualHash, result.TxHash)
			require.True(t, result.DurableFenced)
			checkpoint := readTestCustodyJournal(t, engine)
			require.Equal(t, "7000000", checkpoint.HeldOutboundUWolo)
			require.Equal(t, "0", checkpoint.ConfirmedOutboundUWolo)
			require.Equal(t, int32(1), backend.signs.Load())
			require.Equal(t, int32(1), backend.broadcasts.Load())
			require.Equal(t, int32(0), backend.confirmations.Load())
			require.Equal(t, int32(0), oldFixture.signer.calls.Load(), "the synthetic backend signer must never be used")
			require.Equal(t, int32(0), oldFixture.broadcasts.Load(), "the synthetic acknowledgement fixture must never be used")
			require.NoError(t, engine.Close())
			native.Close()
			reopenedNative, err := NewKeyringBackend(cfg)
			require.NoError(t, err)
			defer reopenedNative.Close()
			reopenedBackend := &observedNativeBackend{KeyringBackend: reopenedNative}
			reopened, err := Open(journalPath, policy, reopenedBackend)
			require.NoError(t, err)
			defer reopened.Close()
			reopened.now = func() time.Time { return time.Now().Add(time.Hour) }
			for i := 0; i < 3; i++ {
				again, err := reopened.Submit(t.Context(), request)
				require.NoError(t, err)
				require.Equal(t, result, again)
			}
			require.Equal(t, checkpoint, readTestCustodyJournal(t, reopened))
			require.Zero(t, reopenedBackend.signs.Load())
			require.Zero(t, reopenedBackend.broadcasts.Load())
			require.Zero(t, reopenedBackend.confirmations.Load())
			require.Equal(t, int32(1), rpcBroadcasts.Load(), "restart/duplicate requests retransmitted an already executed transfer")
		})
	}
}
