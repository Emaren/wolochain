package satchel

// This fixture is one continuous, in-memory SDK application, not four funded
// snapshots. The deterministic keys and validator below have test authority only.
// Exporting the transcript never provisions a production wallet or trust root.
import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	cmted "github.com/cometbft/cometbft/crypto/ed25519"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmtversion "github.com/cometbft/cometbft/proto/tendermint/version"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	version "github.com/cometbft/cometbft/version"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/tx/signing"
	authsign "github.com/cosmos/cosmos-sdk/x/auth/signing"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/app"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

type lifecycleWallet struct {
	key     *secp256k1.PrivKey
	address sdk.AccAddress
}

type lifecycleStep struct {
	Name          string           `json:"name"`
	Intent        TransferIntent   `json:"intent"`
	TxHash        string           `json:"tx_hash"`
	TxBytes       []byte           `json:"tx_bytes"`
	FeeUWolo      string           `json:"fee_uwolo"`
	Height        int64            `json:"height"`
	HeadHeight    int64            `json:"head_height"`
	Observation   Observation      `json:"observation"`
	Receipt       ReceiptCandidate `json:"receipt"`
	Proof         PortableProof    `json:"proof"`
	VaultBalance  string           `json:"vault_balance_uwolo"`
	VaultProof    BankProof        `json:"vault_bank_proof"`
	EscrowProof   BankProof        `json:"escrow_bank_proof"`
	DepositIntent *Intent          `json:"deposit_intent,omitempty"`
	DepositProof  *PortableProof   `json:"deposit_proof,omitempty"`
	ReplayHeight  int64            `json:"replay_height"`
	ReplayCode    uint32           `json:"replay_code"`
}

// TestAuthenticatedContinuousSDKLifecycle exports a portable proof for each
// actual payment in the same SDK state machine. All ante fees are funded
// separately from the owner's 100-WOLO custody principal. Identical-byte replay
// is committed after each payment and fails without changing the role balances.
func TestAuthenticatedContinuousSDKLifecycle(t *testing.T) {
	if path := os.Getenv("SATCHEL_LIFECYCLE_RECIPE"); path != "" {
		recipe := readLifecycleRecipe(t, path)
		t.Run(recipe.Scenario, func(t *testing.T) { runContinuousSDKLifecycle(t, recipe.Scenario, false, &recipe) })
		return
	}
	for _, matched := range []bool{false, true} {
		name := "full_unmatched_refund"
		if matched {
			name = "matched_counterparty_payout"
		}
		t.Run(name, func(t *testing.T) { runContinuousSDKLifecycle(t, name, matched, nil) })
	}
	recipe := twelveCanonicalTicketRecipe()
	t.Run(recipe.Scenario, func(t *testing.T) { runContinuousSDKLifecycle(t, recipe.Scenario, false, &recipe) })
}

// This exercises native execution and authenticated proof plumbing. Entitlement
// decisions, HD ledger mutations, Watcher triggers and live custody are outside
// this fixture; its supplied transfer intents are not a substitute for them.
func runContinuousSDKLifecycle(t *testing.T, scenario string, matched bool, recipe *sdkLifecycleRecipe) {
	t.Helper()
	exportDir := os.Getenv("SATCHEL_LIFECYCLE_FIXTURE_DIR")
	now := time.Date(2026, 10, 19, 12, 0, 0, 0, time.UTC)
	if exportDir != "" {
		require.True(t, filepath.IsAbs(exportDir))
		now = time.Now().UTC().Truncate(time.Millisecond)
	}
	if recipe != nil && recipe.Now != "" {
		frozen, e := time.Parse(time.RFC3339Nano, recipe.Now)
		require.NoError(t, e)
		actual := time.Now().UTC()
		require.False(t, frozen.After(actual.Add(5*time.Second)), "test recipe clock cannot manufacture future finality")
		require.True(t, frozen.After(actual.Add(-30*time.Second)), "test recipe replay must remain currently fresh")
		now = frozen
	}
	wallet := func(name string) lifecycleWallet {
		key := secp256k1.GenPrivKeyFromSecret([]byte("isolated-satchel-lifecycle-test-only/" + name))
		return lifecycleWallet{key, sdk.AccAddress(key.PubKey().Address())}
	}
	owner, vault, escrow, opponent := wallet("owner"), wallet("vault"), wallet("escrow"), wallet("opponent")
	require.NotEqual(t, owner.address, vault.address)
	require.NotEqual(t, vault.address, escrow.address)
	require.NotEqual(t, owner.address, escrow.address)
	opts := viper.New()
	opts.Set(flags.FlagHome, t.TempDir())
	application := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, opts, baseapp.SetChainID(ChainID))
	t.Cleanup(func() { require.NoError(t, application.Close()) })
	validator := cmted.GenPrivKeyFromSecret([]byte("isolated-satchel-lifecycle-validator-test-only"))
	vals := cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(validator.PubKey(), 10)})
	accounts := []authtypes.GenesisAccount{
		authtypes.NewBaseAccount(owner.address, owner.key.PubKey(), 0, 0),
		authtypes.NewBaseAccount(vault.address, vault.key.PubKey(), 1, 0),
		authtypes.NewBaseAccount(escrow.address, escrow.key.PubKey(), 2, 0),
	}
	var opponentInitial int64
	if matched || recipe != nil {
		accounts = append(accounts, authtypes.NewBaseAccount(opponent.address, opponent.key.PubKey(), 3, 0))
		opponentInitial = 12000001 // independently supplied counterparty principal plus ante fee
		if recipe != nil {
			opponentInitial = 100000004
		}
	}
	balance := func(w lifecycleWallet, amount int64) banktypes.Balance {
		return banktypes.Balance{Address: w.address.String(), Coins: sdk.NewCoins(sdk.NewInt64Coin(Denom, amount))}
	}
	balances := []banktypes.Balance{balance(owner, 100000001), balance(vault, 100), balance(escrow, 100)}
	if matched || recipe != nil {
		balances = append(balances, balance(opponent, opponentInitial))
	}
	genesis, err := simtestutil.GenesisStateWithValSet(application.AppCodec(), application.DefaultGenesis(), vals, accounts, balances...)
	require.NoError(t, err)
	state, err := cmtjson.Marshal(genesis)
	require.NoError(t, err)
	start := now.Add(-2 * time.Second)
	init, err := application.InitChain(&abci.RequestInitChain{ChainId: ChainID, Time: start.Add(-time.Second), AppStateBytes: state, ConsensusParams: simtestutil.DefaultConsensusParams})
	require.NoError(t, err)
	commits := map[int64]*core.ResultCommit{}
	results := map[int64]*core.ResultBlockResults{}
	transactions := map[string]*core.ResultTx{}
	rests := map[string]map[string]any{}
	bankStates := []map[string]any{}
	snapshot := func(label string, height int64, expected [3]int64, expectedOpponent, fees int64) {
		ctx := application.NewUncachedContext(false, cmtproto.Header{Height: height})
		if height == 0 {
			ctx = application.NewContextLegacy(false, cmtproto.Header{})
		}
		values := map[string]string{}
		for n, entry := range []struct {
			name   string
			wallet lifecycleWallet
		}{{"owner", owner}, {"vault", vault}, {"escrow", escrow}} {
			actual := application.BankKeeper.GetBalance(ctx, entry.wallet.address, Denom).Amount
			require.Equal(t, sdkmath.NewInt(expected[n]), actual, label+" "+entry.name)
			values[entry.name] = actual.String()
		}
		opponentActual := application.BankKeeper.GetBalance(ctx, opponent.address, Denom).Amount
		require.Equal(t, sdkmath.NewInt(expectedOpponent), opponentActual, label+" counterparty")
		values["opponent"] = opponentActual.String()
		require.Equal(t, int64(100000201)+opponentInitial, expected[0]+expected[1]+expected[2]+expectedOpponent+fees, "principal and operating fees conserve")
		bankStates = append(bankStates, map[string]any{"after": label, "height": height, "balances_uwolo": values, "cumulative_fee_uwolo": strconv.FormatInt(fees, 10)})
	}
	snapshot("genesis", 0, [3]int64{100000001, 100, 100}, opponentInitial, 0)
	appHash := init.AppHash
	var lastResults []*abci.ExecTxResult
	var height int64
	commitBlock := func(txs [][]byte) *abci.ResponseFinalizeBlock {
		height++
		cometTxs := make(cmt.Txs, len(txs))
		for n, tx := range txs {
			cometTxs[n] = cmt.Tx(tx)
		}
		h := &cmt.Header{Version: cmtversion.Consensus{Block: version.BlockProtocol}, ChainID: ChainID, Height: height,
			Time: start.Add(time.Duration(height) * 10 * time.Millisecond), ValidatorsHash: vals.Hash(), NextValidatorsHash: vals.Hash(),
			ConsensusHash: bytes.Repeat([]byte{2}, 32), AppHash: appHash, ProposerAddress: validator.PubKey().Address(),
			DataHash: cometTxs.Hash(), LastResultsHash: cmt.NewResults(lastResults).Hash()}
		if height > 1 {
			h.LastBlockID = commits[height-1].Commit.BlockID
			h.LastCommitHash = commits[height-1].Commit.Hash()
		}
		id := cmt.BlockID{Hash: h.Hash(), PartSetHeader: cmt.PartSetHeader{Total: 1, Hash: bytes.Repeat([]byte{6}, 32)}}
		vote := cmtproto.Vote{Type: cmtproto.PrecommitType, Height: height, BlockID: id.ToProto(), Timestamp: h.Time, ValidatorAddress: validator.PubKey().Address()}
		sig, err := validator.Sign(cmt.VoteSignBytes(ChainID, &vote))
		require.NoError(t, err)
		commit := &cmt.Commit{Height: height, BlockID: id, Signatures: []cmt.CommitSig{{BlockIDFlag: cmt.BlockIDFlagCommit, ValidatorAddress: validator.PubKey().Address(), Timestamp: h.Time, Signature: sig}}}
		commits[height] = core.NewResultCommit(h, commit, true)
		executed, err := application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: height, Hash: id.Hash, Time: h.Time, NextValidatorsHash: vals.Hash(), Txs: txs})
		require.NoError(t, err)
		_, err = application.Commit()
		require.NoError(t, err)
		results[height] = &core.ResultBlockResults{Height: height, TxsResults: executed.TxResults}
		lastResults = executed.TxResults
		appHash = executed.AppHash
		return executed
	}
	signSend := func(from, to lifecycleWallet, amount int64, memo string) []byte {
		ctx := application.NewUncachedContext(false, cmtproto.Header{Height: height})
		if height == 0 {
			ctx = application.NewContextLegacy(false, cmtproto.Header{})
		}
		account := application.AuthKeeper.GetAccount(ctx, from.address)
		require.NotNil(t, account)
		builder := application.TxConfig().NewTxBuilder()
		require.NoError(t, builder.SetMsgs(banktypes.NewMsgSend(from.address, to.address, sdk.NewCoins(sdk.NewInt64Coin(Denom, amount)))))
		builder.SetMemo(memo)
		builder.SetFeeAmount(sdk.NewCoins(sdk.NewInt64Coin(Denom, 1)))
		builder.SetGasLimit(200000)
		mode, err := authsign.APISignModeToInternal(application.TxConfig().SignModeHandler().DefaultMode())
		require.NoError(t, err)
		sig := signing.SignatureV2{PubKey: from.key.PubKey(), Data: &signing.SingleSignatureData{SignMode: mode}, Sequence: account.GetSequence()}
		require.NoError(t, builder.SetSignatures(sig))
		signBytes, err := authsign.GetSignBytesAdapter(context.Background(), application.TxConfig().SignModeHandler(), mode,
			authsign.SignerData{Address: from.address.String(), ChainID: ChainID, AccountNumber: account.GetAccountNumber(), Sequence: account.GetSequence(), PubKey: from.key.PubKey()}, builder.GetTx())
		require.NoError(t, err)
		sig.Data.(*signing.SingleSignatureData).Signature, err = from.key.Sign(signBytes)
		require.NoError(t, err)
		require.NoError(t, builder.SetSignatures(sig))
		data, err := application.TxConfig().TxEncoder()(builder.GetTx())
		require.NoError(t, err)
		return data
	}
	// The SDK explicitly refuses state proofs at height <=1. Start the same
	// chain with an empty block; all financial effects then have provable state.
	commitBlock(nil)
	steps := []lifecycleStep{}
	type paymentSpec struct {
		name     string
		from, to lifecycleWallet
		amount   int64
		memo     string
		expected [3]int64
		opponent int64
	}
	specs := []paymentSpec{
		{"deposit", owner, vault, 100000000, "aoe2war/satchel/v1/lifecycle-owner/abcdefghijklmnop", [3]int64{0, 100000100, 100}, opponentInitial},
		{"wager", vault, escrow, 12000000, "AoE2HDBets bet ticket v1 · ticket 1", [3]int64{0, 88000099, 12000100}, opponentInitial},
	}
	if matched {
		specs = append(specs,
			paymentSpec{"counterparty_funding", opponent, escrow, 12000000, "AoE2HDBets bet ticket v1 · ticket 2", [3]int64{0, 88000099, 24000100}, 0},
			paymentSpec{"matched_payout", escrow, vault, 24000000, "aoe2war/satchel/claim-return/v1/101", [3]int64{0, 112000099, 99}, 0},
			paymentSpec{"withdrawal", vault, owner, 112000000, "aoe2war/satchel/withdraw/v1/00000000-0000-4000-8000-000000000001", [3]int64{112000000, 98, 99}, 0})
	} else {
		specs = append(specs,
			paymentSpec{"full_unmatched_refund", escrow, vault, 12000000, "aoe2war/satchel/claim-return/v1/101", [3]int64{0, 100000099, 99}, 0},
			paymentSpec{"withdrawal", vault, owner, 100000000, "aoe2war/satchel/withdraw/v1/00000000-0000-4000-8000-000000000001", [3]int64{100000000, 98, 99}, 0})
	}
	if recipe != nil {
		specs = nil
		wallets := map[string]lifecycleWallet{"owner": owner, "vault": vault, "escrow": escrow, "opponent": opponent}
		remaining := map[string]int64{"owner": 100000001, "vault": 100, "escrow": 100, "opponent": opponentInitial}
		for _, transfer := range recipe.Steps {
			amount, e := strconv.ParseInt(transfer.AmountUWolo, 10, 64)
			require.NoError(t, e)
			require.GreaterOrEqual(t, remaining[transfer.SenderRole], amount+1, "manifest cannot invent funds: "+transfer.Name)
			remaining[transfer.SenderRole] -= amount + 1
			remaining[transfer.RecipientRole] += amount
			specs = append(specs, paymentSpec{transfer.Name, wallets[transfer.SenderRole], wallets[transfer.RecipientRole], amount, transfer.Memo,
				[3]int64{remaining["owner"], remaining["vault"], remaining["escrow"]}, remaining["opponent"]})
		}
	}
	for n, spec := range specs {
		data := signSend(spec.from, spec.to, spec.amount, spec.memo)
		executed := commitBlock([][]byte{data})
		require.Len(t, executed.TxResults, 1)
		result := executed.TxResults[0]
		require.Zero(t, result.Code, result.Log)
		txHeight := height
		tx := cmt.Tx(data)
		hash := strings.ToUpper(hex.EncodeToString(tx.Hash()))
		transactions[hash] = &core.ResultTx{Hash: tx.Hash(), Height: height, Index: 0, TxResult: *result, Tx: tx, Proof: cmt.Txs{tx}.Proof(0)}
		var raw txapi.TxRaw
		var body txapi.TxBody
		require.NoError(t, proto.Unmarshal(data, &raw))
		require.NoError(t, proto.Unmarshal(raw.BodyBytes, &body))
		bodyJSON, err := protojson.Marshal(&body)
		require.NoError(t, err)
		var bodyObject map[string]any
		require.NoError(t, json.Unmarshal(bodyJSON, &bodyObject))
		resultJSON, err := json.Marshal(result)
		require.NoError(t, err)
		var resultObject map[string]any
		require.NoError(t, json.Unmarshal(resultJSON, &resultObject))
		resultObject["height"], resultObject["txhash"], resultObject["timestamp"], resultObject["logs"] = strconv.FormatInt(height, 10), hash, commits[height].Time.Format(time.RFC3339Nano), []any{}
		delete(resultObject, "code") // Legitimate Cosmos successful zero-code omission.
		rests[hash] = map[string]any{"tx": map[string]any{"body": bodyObject}, "tx_response": resultObject}
		snapshot(spec.name, height, spec.expected, spec.opponent, int64(n+1))
		commitBlock(nil)
		commitBlock(nil)
		commitBlock(nil)
		steps = append(steps, lifecycleStep{Name: spec.name, Intent: TransferIntent{spec.from.address.String(), spec.to.address.String(), strconv.FormatInt(spec.amount, 10), spec.memo}, TxHash: hash, TxBytes: data, FeeUWolo: "1", Height: txHeight, HeadHeight: height, VaultBalance: strconv.FormatInt(spec.expected[1], 10)})
		repeated := commitBlock([][]byte{data})
		require.Len(t, repeated.TxResults, 1)
		require.NotZero(t, repeated.TxResults[0].Code, "actual ante handler must refuse identical sequence")
		steps[n].ReplayHeight, steps[n].ReplayCode = height, repeated.TxResults[0].Code
		snapshot(spec.name+"_replay_refused", height, spec.expected, spec.opponent, int64(n+1))
	}
	// Query the actual retained IAVL versions rather than synthesizing balances
	// from the assertions above. Each proof must bind to the next signed header.
	bankQueries := map[string]*abci.ResponseQuery{}
	for _, step := range steps {
		stateHeight := step.HeadHeight - 1
		for _, account := range []string{vault.address.String(), escrow.address.String()} {
			key, err := nativeBankKey(account)
			require.NoError(t, err)
			query, err := application.Query(context.Background(), &abci.RequestQuery{Path: "/store/bank/key", Data: key, Height: stateHeight, Prove: true})
			require.NoError(t, err)
			require.Zero(t, query.Code, query.Log)
			bankQueries[bankQuery(stateHeight, key).Encode()] = query
		}
	}
	anchor := TrustAnchor{Height: 1, Hash: hex.EncodeToString(commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "isolated-continuous-sdk-lifecycle-test-only"}
	// The two local transcript roles share one deliberately isolated validator.
	// They exercise authenticated signatures, not independent production operators.
	var activeHead int64
	serve := func() *httptest.Server {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			require.Equal(t, http.MethodGet, r.Method)
			require.Equal(t, "identity", r.Header.Get("Accept-Encoding"))
			w.Header().Set("Content-Type", "application/json")
			var value any
			switch r.URL.Path {
			case "/abci_query":
				query := bankQueries[r.URL.RawQuery]
				require.NotNil(t, query)
				value = core.ResultABCIQuery{Response: *query}
			case "/status":
				status := core.ResultStatus{}
				status.NodeInfo.Network = ChainID
				status.SyncInfo.LatestBlockHeight, status.SyncInfo.LatestBlockHash, status.SyncInfo.LatestBlockTime = activeHead, commits[activeHead].Header.Hash(), commits[activeHead].Time
				value = status
			case "/tx":
				require.Equal(t, "true", r.URL.Query().Get("prove"))
				value = transactions[strings.TrimPrefix(r.URL.Query().Get("hash"), "0x")]
			case "/block_results":
				h, err := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
				require.NoError(t, err)
				value = results[h]
			case "/commit":
				h, err := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
				require.NoError(t, err)
				value = commits[h]
			case "/validators":
				h, err := strconv.ParseInt(r.URL.Query().Get("height"), 10, 64)
				require.NoError(t, err)
				require.Equal(t, "1", r.URL.Query().Get("page"))
				require.Equal(t, "100", r.URL.Query().Get("per_page"))
				value = &core.ResultValidators{BlockHeight: h, Validators: vals.Validators, Count: len(vals.Validators), Total: len(vals.Validators)}
			default:
				const prefix = "/cosmos/tx/v1beta1/txs/"
				require.True(t, strings.HasPrefix(r.URL.Path, prefix))
				value = rests[strings.TrimPrefix(r.URL.Path, prefix)]
				encoded, err := json.Marshal(value)
				require.NoError(t, err)
				_, err = w.Write(encoded)
				require.NoError(t, err)
				return
			}
			require.NotNil(t, value)
			encoded, err := cmtjson.Marshal(value)
			require.NoError(t, err)
			_, err = fmt.Fprintf(w, `{"jsonrpc":"2.0","id":-1,"result":%s}`, encoded)
			require.NoError(t, err)
		}))
		t.Cleanup(server.Close)
		return server
	}
	primary, witness := serve(), serve()
	reader, err := NewTrustedReader(SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL}, anchor)
	require.NoError(t, err)
	t.Cleanup(reader.Close)
	reader.reader.now = func() time.Time { return now }
	verifier, err := NewProofVerifier(anchor)
	require.NoError(t, err)
	verifier.now = func() time.Time { return now }
	for n := range steps {
		step := &steps[n]
		activeHead = step.HeadHeight
		evidence, proof, err := reader.ReadTransferProof(context.Background(), step.Intent, step.TxHash)
		require.NoError(t, err, step.Name)
		require.True(t, evidence.ConsensusAuthenticated())
		require.False(t, evidence.CreditAuthorized())
		require.Equal(t, step.TxBytes, evidence.Observation().TxBytes)
		require.Equal(t, int64(4), evidence.Observation().Head.Height-evidence.Observation().Height+1)
		require.Equal(t, uint32(1), *evidence.Observation().TransferIndex, "fee precedes actual bank send")
		verified, err := verifier.VerifyTransferProof(context.Background(), step.Intent, step.TxHash, proof)
		require.NoError(t, err)
		require.Equal(t, evidence.Receipt(), verified.Receipt())
		step.Observation, step.Receipt, step.Proof = evidence.Observation(), evidence.Receipt(), proof
		// Spendability uses the most recent state already authenticated by the
		// primary head, not an earlier asset snapshot before subsequent outflows.
		stateHeight := step.HeadHeight - 1
		bank, bankProof, err := reader.ReadBankProof(context.Background(), vault.address.String(), stateHeight)
		require.NoError(t, err, step.Name)
		require.Equal(t, step.VaultBalance, bank.BalanceUWolo())
		require.Equal(t, stateHeight, bank.Height())
		require.Equal(t, step.HeadHeight, bank.CommitHeight())
		require.True(t, bank.FreshAt(now))
		verifiedBank, err := verifier.VerifyBankProof(context.Background(), vault.address.String(), stateHeight, bankProof)
		require.NoError(t, err, step.Name)
		require.Equal(t, step.VaultBalance, verifiedBank.BalanceUWolo())
		step.VaultProof = bankProof
		escrowBank, escrowProof, err := reader.ReadBankProof(context.Background(), escrow.address.String(), stateHeight)
		require.NoError(t, err, step.Name)
		require.Equal(t, bank.Height(), escrowBank.Height())
		require.Equal(t, bank.AppHash(), escrowBank.AppHash())
		require.Equal(t, bank.BlockHash(), escrowBank.BlockHash())
		_, err = verifier.VerifyBankProof(context.Background(), escrow.address.String(), stateHeight, escrowProof)
		require.NoError(t, err)
		step.EscrowProof = escrowProof
		canonical, err := verifier.VerifyMessageTransferProof(context.Background(), step.Intent, step.TxHash, proof)
		require.NoError(t, err, step.Name)
		require.Equal(t, uint32(0), canonical.Receipt().TransferIndex)
		require.Equal(t, uint32(1), *canonical.Observation().TransferIndex, "canonical message identity must preserve raw fee/send events")
		require.Equal(t, uint32(1), evidence.Receipt().TransferIndex, "legacy outgoing receipt remains event ordinal one")
		if step.Name == "deposit" {
			intent := Intent{OwnerID: "lifecycle-owner", Sender: step.Intent.Sender, Vault: step.Intent.Recipient, AmountUWolo: step.Intent.AmountUWolo, Memo: step.Intent.Memo, CreatedAt: start.Add(-time.Second), ExpiresAt: now.Add(10 * time.Minute)}
			deposit, depositProof, err := reader.ReadDepositProof(context.Background(), intent, step.TxHash)
			require.NoError(t, err)
			require.Equal(t, uint32(0), deposit.Receipt().TransferIndex)
			_, err = verifier.VerifyDepositProof(context.Background(), intent, step.TxHash, depositProof)
			require.NoError(t, err)
			step.DepositIntent, step.DepositProof = &intent, &depositProof
		}
	}
	require.False(t, CurrentCapability().Available())
	if exportDir != "" {
		exportDir = filepath.Join(exportDir, scenario)
		require.NoError(t, os.MkdirAll(exportDir, 0700))
		fixture := map[string]any{"fixture_only": true, "mainnet_authority": false, "chain_id": ChainID, "denom": Denom, "now": now, "anchor": anchor,
			"roles":  map[string]any{"owner_id": "lifecycle-owner", "owner": owner.address.String(), "vault": vault.address.String(), "escrow": escrow.address.String(), "opponent": opponent.address.String(), "owner_public_key_hex": hex.EncodeToString(owner.key.PubKey().Bytes()), "vault_public_key_hex": hex.EncodeToString(vault.key.PubKey().Bytes()), "escrow_public_key_hex": hex.EncodeToString(escrow.key.PubKey().Bytes()), "owner_private_key_hex_test_only": hex.EncodeToString(owner.key.Bytes()), "owner_private_key_warning": "DETERMINISTIC ISOLATED FIXTURE ONLY; NEVER FUND OR PROVISION"},
			"recipe": recipe, "scenario": scenario, "bank_states": bankStates, "steps": steps, "committed_block_count": height, "successful_transfers": len(steps), "total_fee_uwolo": strconv.Itoa(len(steps)), "production_custody_available": false}
		encoded, err := json.MarshalIndent(fixture, "", "  ")
		require.NoError(t, err)
		require.NoError(t, os.WriteFile(filepath.Join(exportDir, "isolated-sdk-lifecycle.json"), encoded, 0600))
	}
}
