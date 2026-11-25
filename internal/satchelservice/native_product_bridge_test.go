package satchelservice

// Disposable subprocess support for the actual app product journey. The SDK
// chain stays alive while its separate real-keyring signer can crash/restart.
// Financial operations are executed on demand; this fixture has no recipe of
// future hashes, no app database writer and no escrow-return signing shortcut.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	bankapi "cosmossdk.io/api/cosmos/bank/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"cosmossdk.io/log"
	abci "github.com/cometbft/cometbft/abci/types"
	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/crypto"
	cryptocodec "github.com/cosmos/cosmos-sdk/crypto/codec"
	"github.com/cosmos/cosmos-sdk/crypto/keyring"
	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	authsign "github.com/cosmos/cosmos-sdk/x/auth/signing"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/app"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

type nativeProductBridgeInput struct {
	FixtureOnly               bool   `json:"fixture_only"`
	Directory                 string `json:"directory"`
	ReadyFile                 string `json:"ready_file"`
	WagerApprovalPublicKeyHex string `json:"wager_approval_public_key_hex"`
	WithdrawalPublicKeyHex    string `json:"withdrawal_approval_public_key_hex"`
}

type nativeProductChain struct {
	*nativeHTTPChain
	keys         map[string]*secp.PrivKey
	transactions map[string]*core.ResultTx
	rests        map[string]any
	dropVaultACK bool
}

func newNativeProductChain(t *testing.T) *nativeProductChain {
	t.Helper()
	options := viper.New()
	options.Set(flags.FlagHome, t.TempDir())
	application := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, options, baseapp.SetChainID(satchel.ChainID))
	t.Cleanup(func() { require.NoError(t, application.Close()) })
	validator := cmted.GenPrivKeyFromSecret([]byte("isolated-product-bridge-validator-only"))
	validators := cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(validator.PubKey(), 10)})
	f := &nativeProductChain{keys: map[string]*secp.PrivKey{}, transactions: map[string]*core.ResultTx{}, rests: map[string]any{}}
	accounts := []authtypes.GenesisAccount{}
	balances := []banktypes.Balance{}
	for n, role := range []string{"owner", "vault", "escrow", "opponent"} {
		key := secp.GenPrivKeyFromSecret([]byte("isolated-satchel-lifecycle-test-only/" + role))
		f.keys[role] = key
		address := sdk.AccAddress(key.PubKey().Address())
		accounts = append(accounts, authtypes.NewBaseAccount(address, key.PubKey(), uint64(n), 0))
		amount := int64(100000004)
		if role == "vault" {
			amount = 500000000 // separately funded, real SDK equity for custody's conservative margin
		} else if role == "escrow" {
			amount = 100
		}
		balances = append(balances, banktypes.Balance{Address: address.String(), Coins: sdk.NewCoins(sdk.NewInt64Coin(satchel.Denom, amount))})
	}
	genesis, err := simtestutil.GenesisStateWithValSet(application.AppCodec(), application.DefaultGenesis(), validators, accounts, balances...)
	require.NoError(t, err)
	raw, err := cmtjson.Marshal(genesis)
	require.NoError(t, err)
	start := time.Now().UTC().Add(-time.Second)
	init, err := application.InitChain(&abci.RequestInitChain{ChainId: satchel.ChainID, Time: start.Add(-time.Second), AppStateBytes: raw, ConsensusParams: simtestutil.DefaultConsensusParams})
	require.NoError(t, err)
	f.nativeHTTPChain = &nativeHTTPChain{application: application, validator: validator, validators: validators, commits: map[int64]*core.ResultCommit{},
		results: map[int64]*core.ResultBlockResults{}, appHash: init.AppHash, start: start, executed: make(chan struct{}), releaseACK: make(chan struct{})}
	for n := 0; n < 3; n++ {
		f.commitProduct(t, nil)
	}
	return f
}

func (f *nativeProductChain) address(role string) string {
	return sdk.AccAddress(f.keys[role].PubKey().Address()).String()
}

// Caller owns chain.mu. Every block is a genuine SDK commit with a signed,
// continuous Comet header and a fresh monotonically increasing chain time.
func (f *nativeProductChain) commitProduct(t *testing.T, txs [][]byte) *abci.ResponseFinalizeBlock {
	at := time.Now().UTC()
	if f.head > 0 && !at.After(f.commits[f.head].Time) {
		at = f.commits[f.head].Time.Add(time.Millisecond)
	}
	f.start = at.Add(-time.Duration(f.head+1) * 10 * time.Millisecond)
	return f.commit(t, txs)
}

func (f *nativeProductChain) executeProduct(t *testing.T, data []byte) (string, string) {
	t.Helper()
	result := f.commitProduct(t, [][]byte{data})
	require.Len(t, result.TxResults, 1)
	require.Zero(t, result.TxResults[0].Code, result.TxResults[0].Log)
	tx := cmt.Tx(data)
	hash := strings.ToUpper(hex.EncodeToString(tx.Hash()))
	f.transactions[hash] = &core.ResultTx{Hash: tx.Hash(), Height: f.head, Index: 0, TxResult: *result.TxResults[0], Tx: tx, Proof: cmt.Txs{tx}.Proof(0)}
	var raw txapi.TxRaw
	var body txapi.TxBody
	require.NoError(t, proto.Unmarshal(data, &raw))
	require.NoError(t, proto.Unmarshal(raw.BodyBytes, &body))
	encoded, err := protojson.Marshal(&body)
	require.NoError(t, err)
	var bodyJSON map[string]any
	require.NoError(t, json.Unmarshal(encoded, &bodyJSON))
	encoded, err = json.Marshal(result.TxResults[0])
	require.NoError(t, err)
	var resultJSON map[string]any
	require.NoError(t, json.Unmarshal(encoded, &resultJSON))
	resultJSON["height"], resultJSON["txhash"], resultJSON["timestamp"], resultJSON["logs"] = strconv.FormatInt(f.head, 10), hash, f.commits[f.head].Time.Format(time.RFC3339Nano), []any{}
	delete(resultJSON, "code")
	f.rests[hash] = map[string]any{"tx": map[string]any{"body": bodyJSON}, "tx_response": resultJSON}
	var send bankapi.MsgSend
	require.Len(t, body.Messages, 1)
	require.NoError(t, proto.Unmarshal(body.Messages[0].Value, &send))
	f.broadcasts++
	for n := 0; n < 3; n++ {
		f.commitProduct(t, nil)
	}
	return hash, send.FromAddress
}

func (f *nativeProductChain) sendProduct(t *testing.T, from, to, amount, memo string) string {
	t.Helper()
	key := f.keys[from]
	address := sdk.AccAddress(key.PubKey().Address())
	ctx := f.application.NewUncachedContext(false, cmtproto.Header{Height: f.head})
	account := f.application.AuthKeeper.GetAccount(ctx, address)
	amountN, err := strconv.ParseInt(amount, 10, 64)
	require.NoError(t, err)
	require.Positive(t, amountN)
	builder := f.application.TxConfig().NewTxBuilder()
	require.NoError(t, builder.SetMsgs(banktypes.NewMsgSend(address, sdk.AccAddress(f.keys[to].PubKey().Address()), sdk.NewCoins(sdk.NewInt64Coin(satchel.Denom, amountN)))))
	builder.SetMemo(memo)
	builder.SetFeeAmount(sdk.NewCoins(sdk.NewInt64Coin(satchel.Denom, 1)))
	builder.SetGasLimit(200000)
	mode, err := authsign.APISignModeToInternal(f.application.TxConfig().SignModeHandler().DefaultMode())
	require.NoError(t, err)
	sig := signing.SignatureV2{PubKey: key.PubKey(), Data: &signing.SingleSignatureData{SignMode: mode}, Sequence: account.GetSequence()}
	require.NoError(t, builder.SetSignatures(sig))
	signBytes, err := authsign.GetSignBytesAdapter(context.Background(), f.application.TxConfig().SignModeHandler(), mode, authsign.SignerData{
		Address: address.String(), ChainID: satchel.ChainID, AccountNumber: account.GetAccountNumber(), Sequence: account.GetSequence(), PubKey: key.PubKey()}, builder.GetTx())
	require.NoError(t, err)
	sig.Data.(*signing.SingleSignatureData).Signature, err = key.Sign(signBytes)
	require.NoError(t, err)
	require.NoError(t, builder.SetSignatures(sig))
	data, err := f.application.TxConfig().TxEncoder()(builder.GetTx())
	require.NoError(t, err)
	hash, _ := f.executeProduct(t, data)
	return hash
}

func (f *nativeProductChain) serveProduct(t *testing.T, witness bool) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		method, params, id := strings.TrimPrefix(r.URL.Path, "/"), r.URL.Query(), json.RawMessage(`-1`)
		if r.Method == http.MethodPost {
			if r.URL.Path == "/" {
				var request struct {
					Method string
					Params map[string]json.RawMessage
					ID     json.RawMessage
				}
				require.NoError(t, json.NewDecoder(r.Body).Decode(&request))
				method, id = request.Method, request.ID
				params = url.Values{}
				for key, raw := range request.Params {
					var text string
					if json.Unmarshal(raw, &text) != nil {
						text = string(raw)
					}
					params.Set(key, text)
				}
			} else {
				require.NoError(t, r.ParseForm())
				params = r.Form
			}
		}
		if f.head > 0 && time.Since(f.commits[f.head].Time) > 5*time.Second {
			f.commitProduct(t, nil)
		}
		height, _ := strconv.ParseInt(params.Get("height"), 10, 64)
		var value any
		switch method {
		case "status":
			status := core.ResultStatus{}
			status.NodeInfo.Network = satchel.ChainID
			status.SyncInfo.LatestBlockHeight, status.SyncInfo.LatestBlockHash, status.SyncInfo.LatestBlockTime = f.head, f.commits[f.head].Header.Hash(), f.commits[f.head].Time
			value = status
		case "commit":
			if height == 0 {
				height = f.head
			}
			value = f.commits[height]
		case "validators":
			value = &core.ResultValidators{BlockHeight: height, Validators: f.validators.Validators, Count: len(f.validators.Validators), Total: len(f.validators.Validators)}
		case "block_results":
			value = f.results[height]
		case "tx":
			hash := strings.ToUpper(strings.TrimPrefix(params.Get("hash"), "0x"))
			value = f.transactions[hash]
			if value == nil {
				http.NotFound(w, r)
				return
			}
		case "abci_query":
			path := params.Get("path")
			if unquoted, err := strconv.Unquote(path); err == nil {
				path = unquoted
			}
			data, err := hex.DecodeString(strings.TrimPrefix(params.Get("data"), "0x"))
			if err != nil {
				data, err = base64.StdEncoding.DecodeString(params.Get("data"))
			}
			require.NoError(t, err)
			query, err := f.application.Query(r.Context(), &abci.RequestQuery{Path: path, Data: data, Height: height, Prove: params.Get("prove") == "true"})
			require.NoError(t, err)
			value = core.ResultABCIQuery{Response: *query}
		case "broadcast_tx_sync":
			require.False(t, witness)
			data, err := base64.StdEncoding.DecodeString(params.Get("tx"))
			if err != nil {
				data, err = hex.DecodeString(strings.TrimPrefix(params.Get("tx"), "0x"))
			}
			require.NoError(t, err)
			hash, sender := f.executeProduct(t, data)
			if sender == f.address("vault") && f.dropVaultACK {
				f.dropVaultACK = false
				connection, _, err := w.(http.Hijacker).Hijack()
				require.NoError(t, err)
				_ = connection.Close()
				return
			}
			hashBytes, err := hex.DecodeString(hash)
			require.NoError(t, err)
			value = &core.ResultBroadcastTx{Hash: hashBytes}
		default:
			f.serveProductREST(t, w, r)
			return
		}
		encoded, err := cmtjson.Marshal(value)
		require.NoError(t, err)
		_, _ = fmt.Fprintf(w, `{"jsonrpc":"2.0","id":%s,"result":%s}`, id, encoded)
	}))
	t.Cleanup(server.Close)
	return server
}

func (f *nativeProductChain) serveProductREST(t *testing.T, w http.ResponseWriter, r *http.Request) {
	t.Helper()
	ctx := f.application.NewUncachedContext(false, cmtproto.Header{Height: f.head})
	var value any
	switch {
	case strings.HasPrefix(r.URL.Path, "/cosmos/tx/v1beta1/txs/"):
		value = f.rests[strings.TrimPrefix(r.URL.Path, "/cosmos/tx/v1beta1/txs/")]
	case strings.HasPrefix(r.URL.Path, "/cosmos/auth/v1beta1/accounts/"):
		address, err := sdk.AccAddressFromBech32(strings.TrimPrefix(r.URL.Path, "/cosmos/auth/v1beta1/accounts/"))
		require.NoError(t, err)
		account := f.application.AuthKeeper.GetAccount(ctx, address)
		require.NotNil(t, account)
		value = map[string]any{"account": map[string]any{"@type": "/cosmos.auth.v1beta1.BaseAccount", "address": address.String(), "account_number": strconv.FormatUint(account.GetAccountNumber(), 10), "sequence": strconv.FormatUint(account.GetSequence(), 10),
			"pub_key": map[string]string{"@type": "/cosmos.crypto.secp256k1.PubKey", "key": base64.StdEncoding.EncodeToString(account.GetPubKey().Bytes())}}}
	case strings.HasPrefix(r.URL.Path, "/cosmos/bank/v1beta1/balances/"):
		address, err := sdk.AccAddressFromBech32(strings.TrimPrefix(r.URL.Path, "/cosmos/bank/v1beta1/balances/"))
		require.NoError(t, err)
		value = map[string]any{"balances": []sdk.Coin{f.application.BankKeeper.GetBalance(ctx, address, satchel.Denom)}}
	case r.URL.Path == "/cosmos/base/tendermint/v1beta1/node_info":
		value = map[string]any{"default_node_info": map[string]string{"network": satchel.ChainID}}
	case r.URL.Path == "/cosmos/bank/v1beta1/denoms_metadata/uwolo":
		value = map[string]any{"metadata": map[string]string{"base": "uwolo", "display": "wolo"}}
	case r.URL.Path == "/cosmos/staking/v1beta1/params":
		value = map[string]any{"params": map[string]string{"bond_denom": "uwolo"}}
	case r.URL.Path == "/cosmos/mint/v1beta1/params":
		value = map[string]any{"params": map[string]string{"mint_denom": "uwolo"}}
	}
	if value == nil {
		http.NotFound(w, r)
		return
	}
	require.NoError(t, json.NewEncoder(w).Encode(value))
}

func nativeProductKeyring(t *testing.T, directory, name string, key *secp.PrivKey) string {
	t.Helper()
	require.NoError(t, os.MkdirAll(directory, 0700))
	registry := codectypes.NewInterfaceRegistry()
	cryptocodec.RegisterInterfaces(registry)
	const password = "disposable-product-bridge-only"
	keys, err := keyring.New("cosmos", keyring.BackendFile, directory, strings.NewReader(password+"\n"+password+"\n"), codec.NewProtoCodec(registry))
	require.NoError(t, err)
	require.NoError(t, keys.ImportPrivKey(name, crypto.EncryptArmorPrivKey(key, "disposable-import-only", key.Type()), "disposable-import-only"))
	require.NoError(t, os.Chmod(filepath.Join(directory, "keyring-file"), 0700))
	unlock := filepath.Join(directory, "unlock")
	require.NoError(t, os.WriteFile(unlock, []byte(password+"\n"), 0600))
	return unlock
}

type nativeProductSignerInput struct {
	ConfigPath string `json:"config_path"`
	ReadyFile  string `json:"ready_file"`
	CountsFile string `json:"counts_file"`
}

type nativeProductProofEngine struct{ *nativeHTTPProofEngine }

func (e *nativeProductProofEngine) EscrowBankProof(ctx context.Context) (satchel.BankProof, error) {
	_, proof, err := e.reader.ReadCurrentBankProof(ctx, e.policy.BettingEscrow)
	return proof, err
}

func TestNativeProductBridgeSignerProcess(t *testing.T) {
	path := os.Getenv("SATCHEL_PRODUCT_SIGNER_TEST_CONFIG")
	if path == "" {
		t.Skip("disposable signer subprocess only")
	}
	var input nativeProductSignerInput
	raw, err := os.ReadFile(path)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(raw, &input))
	cfg, configDigest, err := LoadConfig(input.ConfigPath)
	require.NoError(t, err)
	binary := nativeHTTPBinaryDigest(t)
	reader, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: cfg.RPC, REST: cfg.REST, WitnessRPC: cfg.WitnessRPC}, cfg.TrustAnchor)
	require.NoError(t, err)
	defer reader.Close()
	approval, err := hex.DecodeString(cfg.WithdrawalApprovalKeyHex)
	require.NoError(t, err)
	wager, err := hex.DecodeString(cfg.WagerApprovalKeyHex)
	require.NoError(t, err)
	policy := Policy{Vault: cfg.Vault, BettingEscrow: cfg.BettingEscrow, ProtectedAddresses: cfg.ProtectedAddresses, MaxAmountUWolo: cfg.MaxAmountUWolo, WithdrawalApprovalKey: approval, WagerApprovalKey: wager}
	var authority *CustodyAuthority
	bc := nativeHTTPBackendConfig(cfg, policy)
	bc.WithdrawalVerifier = policy.VerifyWithdrawal
	bc.AuthorizeSign = func(ctx context.Context, request TransferRequest) bool {
		return authority != nil && authority.AuthorizeSign(ctx, request)
	}
	bc.AuthorizeBroadcast = func(ctx context.Context, signed SignedTransaction) bool {
		return authority != nil && authority.AuthorizeBroadcast(ctx, signed)
	}
	bc.ConfirmTransaction = func(ctx context.Context, request TransferRequest, signed SignedTransaction) (Confirmation, error) {
		evidence, err := reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: request.Sender, Recipient: request.Recipient, AmountUWolo: request.AmountUWolo, Memo: request.Memo}, signed.Hash)
		if err != nil || !evidence.ConsensusAuthenticated() || !bytes.Equal(evidence.Observation().TxBytes, signed.Bytes) {
			return Confirmation{Status: "UNKNOWN"}, ErrReviewerHeld
		}
		observation := evidence.Observation()
		return Confirmation{Status: "CONFIRMED", ReceiptID: evidence.Receipt().ID(), Height: observation.Height, BlockHash: observation.BlockHash}, nil
	}
	native, err := NewKeyringBackend(bc)
	require.NoError(t, err)
	defer native.Close()
	backend := &nativeHTTPBackend{observedNativeBackend: &observedNativeBackend{KeyringBackend: native}, countsPath: input.CountsFile}
	engine, err := Open(cfg.StatePath, policy, backend)
	require.NoError(t, err)
	defer engine.Close()
	backend.engine = engine
	authority, err = NewCustodyAuthority(engine, native, reader, input.ConfigPath, configDigest, binary)
	require.NoError(t, err)
	require.NoError(t, engine.RequireCustodyAuthority(authority))
	token, err := ReadPrivateFile(cfg.TokenFile, 4096)
	require.NoError(t, err)
	permitBytes, err := os.ReadFile(cfg.PermitFile)
	require.NoError(t, err)
	refreshReview := func() {
		journal, err := engine.CustodyJournal()
		require.NoError(t, err)
		bank, _, err := reader.ReadCurrentBankProof(t.Context(), cfg.Vault)
		require.NoError(t, err)
		expiry := time.Now().Add(20 * time.Second)
		if bank.ExpiresAt().Before(expiry) {
			expiry = bank.ExpiresAt()
		}
		review := SignedReserveReview{Version: 1, Scope: reserveReviewScope, ChainID: "wolo-1", Denom: "uwolo", Vault: cfg.Vault, StateHeight: bank.Height(), CommitBlockHash: bank.BlockHash(),
			ObservedBankUWolo: bank.BalanceUWolo(), ConfirmedLiabilitiesUWolo: "200000000", UncertainMaxLiabilitiesUWolo: "1", GasReserveUWolo: "10", UnencumberedMinimumUWolo: "10",
			LiabilityInventorySHA256: strings.Repeat("1", 64), NonOverlapWitnessSHA256: strings.Repeat("2", 64), JournalSnapshotSHA256: journal.JournalDigest,
			BuildSHA256: binary, ConfigSHA256: configDigest, PermitSHA256: custodySHA(permitBytes), AllObligationsCovered: true, UnknownClaimsReserved: true, DedicatedVaultIsolated: true,
			IssuedAt: time.Now().Unix() - 1, ExpiresAt: expiry.Unix()}
		signReview(&review, ed25519.NewKeyFromSeed(bytes.Repeat([]byte{71}, 32)), ed25519.NewKeyFromSeed(bytes.Repeat([]byte{72}, 32)))
		custodyWrite(t, cfg.ReserveReviewFile, review)
	}
	public, err := hex.DecodeString(cfg.PublicKeyHex)
	require.NoError(t, err)
	fingerprint := sha256.Sum256(public)
	handler, err := NewHTTPHandler(&nativeProductProofEngine{&nativeHTTPProofEngine{Engine: engine, reader: reader}}, HTTPConfig{Token: strings.TrimSpace(string(token)), Accepting: true,
		Authorize: func(context.Context) bool { return VerifyPermit(cfg, configDigest, binary) }, CustodyCapability: authority.Capability,
		Health: HTTPHealth{Accepting: true, VaultAddress: cfg.Vault, BuildSHA256: binary, KeyFingerprint: hex.EncodeToString(fingerprint[:]), ExclusiveAuthorityVerified: true}})
	require.NoError(t, err)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { refreshReview(); handler.ServeHTTP(w, r) }))
	defer server.Close()
	require.NoError(t, os.WriteFile(input.ReadyFile, []byte(server.URL), 0600))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
}

func TestNativeProductBridgeProcess(t *testing.T) {
	path := os.Getenv("SATCHEL_PRODUCT_BRIDGE_TEST_CONFIG")
	if path == "" {
		t.Skip("disposable app product bridge subprocess only")
	}
	var input nativeProductBridgeInput
	raw, err := os.ReadFile(path)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(raw, &input))
	require.True(t, input.FixtureOnly)
	directory, err := filepath.EvalSymlinks(input.Directory)
	require.NoError(t, err)
	temporary, err := filepath.EvalSymlinks(os.TempDir())
	require.NoError(t, err)
	require.True(t, strings.HasPrefix(directory, temporary+string(filepath.Separator)))
	chain := newNativeProductChain(t)
	primary, witness := chain.serveProduct(t, false), chain.serveProduct(t, true)
	anchor := satchel.TrustAnchor{Height: 1, Hash: hex.EncodeToString(chain.commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "disposable-product-bridge-single-test-validator-only"}
	vaultDirectory, escrowDirectory := filepath.Join(directory, "vault"), filepath.Join(directory, "escrow")
	vaultUnlock := nativeProductKeyring(t, vaultDirectory, "product-vault", chain.keys["vault"])
	escrowUnlock := nativeProductKeyring(t, escrowDirectory, "product-escrow", chain.keys["escrow"])
	public := func(seed byte) string {
		return hex.EncodeToString(ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed}, 32)).Public().(ed25519.PublicKey))
	}
	config := Config{Version: 1, RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL, TrustAnchor: anchor, Vault: chain.address("vault"), PublicKeyHex: hex.EncodeToString(chain.keys["vault"].PubKey().Bytes()),
		BettingEscrow: chain.address("escrow"), ProtectedAddresses: []string{chain.address("escrow")}, KeyringDir: vaultDirectory, KeyName: "product-vault", PassphraseFile: vaultUnlock,
		TokenFile: filepath.Join(directory, "signer-token"), StatePath: filepath.Join(directory, "signer-journal.db"), FeesUWolo: "1", GasLimit: 200000, TimeoutBlocks: 100, MaxAmountUWolo: 50000000000,
		WagerApprovalKeyHex: input.WagerApprovalPublicKeyHex, WithdrawalApprovalKeyHex: input.WithdrawalPublicKeyHex, ActivationAuthorityKeyHex: public(79), AccountingReviewerKeyHex: public(71), CustodyReviewerKeyHex: public(72),
		PermitFile: filepath.Join(directory, "signer-permit.json"), ReserveReviewFile: filepath.Join(directory, "signer-reserve-review.json")}
	configPath := filepath.Join(directory, "signer-config.json")
	custodyWrite(t, configPath, config)
	const token = "disposable-product-bridge-private-bearer-2026"
	require.NoError(t, os.WriteFile(config.TokenFile, []byte(token), 0600))
	_, digest, err := LoadConfig(configPath)
	require.NoError(t, err)
	binaryDigest := nativeHTTPBinaryDigest(t)
	permit := ExecutionPermit{Version: 1, Scope: "satchel-execution-v1", ConfigSHA256: digest, BinarySHA256: binaryDigest, Vault: config.Vault,
		IsolationEvidenceSHA256: strings.Repeat("1", 64), AccountingEvidenceSHA256: strings.Repeat("2", 64), RecoveryEvidenceSHA256: strings.Repeat("3", 64),
		Reviewer: "disposable-product-sdk-authority-only", Reference: "SDK equity500 plus conservative200 liability; no mainnet authority", IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Add(time.Hour).Unix()}
	permit.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, 32)), PermitMessage(permit)))
	custodyWrite(t, config.PermitFile, permit)
	signerInput := nativeProductSignerInput{ConfigPath: configPath, ReadyFile: filepath.Join(directory, "signer-ready"), CountsFile: filepath.Join(directory, "signer-counts.json")}
	signerInputPath := filepath.Join(directory, "signer-input.json")
	custodyWrite(t, signerInputPath, signerInput)
	executable, err := os.Executable()
	require.NoError(t, err)
	var signer *exec.Cmd
	var signerURL string
	var signerMu sync.Mutex
	startSigner := func() {
		_ = os.Remove(signerInput.ReadyFile)
		signer = exec.Command(executable, "-test.run=^TestNativeProductBridgeSignerProcess$", "-test.count=1")
		signer.Env = append(os.Environ(), "SATCHEL_PRODUCT_SIGNER_TEST_CONFIG="+signerInputPath)
		logFile, err := os.OpenFile(filepath.Join(directory, "signer-subprocess.log"), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0600)
		require.NoError(t, err)
		signer.Stdout, signer.Stderr = logFile, logFile
		require.NoError(t, signer.Start())
		_ = logFile.Close()
		deadline := time.Now().Add(15 * time.Second)
		for time.Now().Before(deadline) {
			if ready, err := os.ReadFile(signerInput.ReadyFile); err == nil {
				signerURL = string(ready)
				return
			}
			time.Sleep(20 * time.Millisecond)
		}
		t.Fatal("disposable real signer failed to become ready; inspect signer-subprocess.log")
	}
	startSigner()
	defer func() { _ = signer.Process.Kill(); _ = signer.Wait() }()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/fixture/v1/") {
			if r.Header.Get("Authorization") != "Bearer "+token {
				http.Error(w, "fixture authentication required", 401)
				return
			}
			switch r.URL.Path {
			case "/fixture/v1/send":
				var send struct{ SenderRole, RecipientRole, AmountUWolo, Memo string }
				require.Equal(t, http.MethodPost, r.Method)
				require.NoError(t, json.NewDecoder(r.Body).Decode(&send))
				require.True(t, (send.SenderRole == "owner" && send.RecipientRole == "vault") || (send.SenderRole == "opponent" && send.RecipientRole == "escrow"), "fixture cannot bypass the real vault/legacy escrow product send")
				chain.mu.Lock()
				hash := chain.sendProduct(t, send.SenderRole, send.RecipientRole, send.AmountUWolo, send.Memo)
				chain.mu.Unlock()
				require.NoError(t, json.NewEncoder(w).Encode(map[string]string{"tx_hash": hash}))
			case "/fixture/v1/drop-next-vault-ack":
				chain.mu.Lock()
				chain.dropVaultACK = true
				chain.mu.Unlock()
				require.NoError(t, json.NewEncoder(w).Encode(map[string]bool{"armed": true}))
			case "/fixture/v1/restart-signer":
				signerMu.Lock()
				defer signerMu.Unlock()
				_ = signer.Process.Kill()
				_ = signer.Wait()
				startSigner()
				require.NoError(t, json.NewEncoder(w).Encode(map[string]bool{"restarted_same_journal": true}))
			case "/fixture/v1/snapshot":
				chain.mu.Lock()
				defer chain.mu.Unlock()
				ctx := chain.application.NewUncachedContext(false, cmtproto.Header{Height: chain.head})
				balances := map[string]string{}
				for role, key := range chain.keys {
					balances[role] = chain.application.BankKeeper.GetBalance(ctx, sdk.AccAddress(key.PubKey().Address()), "uwolo").Amount.String()
				}
				require.NoError(t, json.NewEncoder(w).Encode(map[string]any{"fixture_only": true, "mainnet_authority": false, "balances_uwolo": balances, "successful_sends": chain.broadcasts, "head_height": chain.head}))
			default:
				http.NotFound(w, r)
			}
			return
		}
		signerMu.Lock()
		target, err := url.Parse(signerURL)
		signerMu.Unlock()
		require.NoError(t, err)
		httputil.NewSingleHostReverseProxy(target).ServeHTTP(w, r)
	}))
	defer server.Close()
	roles := map[string]string{}
	for role := range chain.keys {
		roles[role] = chain.address(role)
	}
	manifest := map[string]any{"fixture_only": true, "mainnet_authority": false, "directory": directory, "satchel_url": server.URL, "control_url": server.URL,
		"rpc_url": primary.URL, "rest_url": primary.URL, "witness_rpc_url": witness.URL, "roles": roles, "trust_anchor": anchor, "build_sha256": binaryDigest,
		"token": token, "escrow_keyring_dir": escrowDirectory, "escrow_unlock_file": escrowUnlock, "signer_config_file": configPath, "fee_uwolo": "1", "vault_equity_uwolo": "500000000"}
	custodyWrite(t, input.ReadyFile, manifest)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
}
