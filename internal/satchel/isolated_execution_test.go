package satchel

// This test executes a signed MsgSend in the actual in-memory WoloChain SDK
// application. Validator signatures below are isolated test-chain attestations,
// never evidence of mainnet custody or a production trust checkpoint.
import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"math/rand"
	"os"
	"path/filepath"
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
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

func TestAuthenticatedProofFromIsolatedSDKExecution(t *testing.T) {
	f, _ := signedReaderFixture(t)
	// A deliberately opt-in test fixture export uses current time so another
	// process can exercise the production offline verifier without clock bypass.
	exportDir := os.Getenv("SATCHEL_PROOF_FIXTURE_DIR")
	if exportDir != "" {
		require.True(t, filepath.IsAbs(exportDir))
		delta := time.Now().UTC().Truncate(time.Millisecond).Sub(f.now)
		f.now = f.now.Add(delta)
		f.intent.CreatedAt = f.intent.CreatedAt.Add(delta)
		f.intent.ExpiresAt = f.intent.ExpiresAt.Add(delta)
		for _, commit := range f.commits {
			commit.Header.Time = commit.Header.Time.Add(delta)
		}
		f.status.SyncInfo.LatestBlockTime = f.commits[102].Time
	}
	opts := viper.New()
	opts.Set(flags.FlagHome, t.TempDir())
	application := app.New(log.NewNopLogger(), dbm.NewMemDB(), nil, true, opts, baseapp.SetChainID(ChainID))
	t.Cleanup(func() { require.NoError(t, application.Close()) })
	key := secp256k1.GenPrivKeyFromSecret([]byte("isolated-bank-sender-no-mainnet-authority"))
	sender := sdk.AccAddress(key.PubKey().Address())
	recipient := sdk.AccAddress(bytes.Repeat([]byte{0x73}, 20))
	vals, err := simtestutil.CreateRandomValidatorSet()
	require.NoError(t, err)
	genesis, err := simtestutil.GenesisStateWithValSet(application.AppCodec(), application.DefaultGenesis(), vals, []authtypes.GenesisAccount{authtypes.NewBaseAccount(sender, key.PubKey(), 0, 0)}, banktypes.Balance{Address: sender.String(), Coins: sdk.NewCoins(sdk.NewCoin(Denom, sdkmath.NewInt(10000000)))})
	require.NoError(t, err)
	state, err := cmtjson.Marshal(genesis)
	require.NoError(t, err)
	_, err = application.InitChain(&abci.RequestInitChain{ChainId: ChainID, Time: f.commits[100].Time, AppStateBytes: state, ConsensusParams: simtestutil.DefaultConsensusParams})
	require.NoError(t, err)
	signed, err := simtestutil.GenSignedMockTx(rand.New(rand.NewSource(1)), application.TxConfig(), []sdk.Msg{banktypes.NewMsgSend(sender, recipient, sdk.NewCoins(sdk.NewInt64Coin(Denom, 7000000)))}, sdk.NewCoins(sdk.NewInt64Coin(Denom, 1)), 200000, ChainID, []uint64{0}, []uint64{0}, key)
	require.NoError(t, err)
	data, err := application.TxConfig().TxEncoder()(signed)
	require.NoError(t, err)
	executed, err := application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: 1, Time: f.commits[100].Time, NextValidatorsHash: vals.Hash(), Txs: [][]byte{data}})
	require.NoError(t, err)
	require.Len(t, executed.TxResults, 1)
	result := executed.TxResults[0]
	require.Zero(t, result.Code, result.Log)
	_, err = application.Commit()
	require.NoError(t, err)
	ctx := application.NewUncachedContext(false, cmtproto.Header{Height: 1})
	require.Equal(t, "7000000", application.BankKeeper.GetBalance(ctx, recipient, Denom).Amount.String())
	require.Equal(t, "2999999", application.BankKeeper.GetBalance(ctx, sender, Denom).Amount.String())
	// Replaying identical bytes is executed by the real ante-handler and fails
	// account-sequence validation. It cannot become a second successful payment.
	repeated, err := application.FinalizeBlock(&abci.RequestFinalizeBlock{Height: 2, Time: f.commits[101].Time, NextValidatorsHash: vals.Hash(), Txs: [][]byte{data}})
	require.NoError(t, err)
	require.NotZero(t, repeated.TxResults[0].Code)

	var raw txapi.TxRaw
	var body txapi.TxBody
	require.NoError(t, proto.Unmarshal(data, &raw))
	require.NoError(t, proto.Unmarshal(raw.BodyBytes, &body))
	f.intent.Sender = sender.String()
	f.intent.Vault = recipient.String()
	f.intent.AmountUWolo = "7000000"
	f.intent.Memo = body.Memo
	f.tx.Tx = cmt.Tx(data)
	f.tx.Hash = f.tx.Tx.Hash()
	f.tx.Proof = cmt.Txs{f.tx.Tx}.Proof(0)
	f.tx.TxResult = *result
	f.results.TxsResults = []*abci.ExecTxResult{result}
	f.observation.TxHash = strings.ToUpper(hex.EncodeToString(f.tx.Hash))
	f.commits[100].Header.DataHash = cmt.Txs{f.tx.Tx}.Hash()
	f.commits[101].Header.LastResultsHash = cmt.NewResults(f.results.TxsResults).Hash()
	validator := cmted.GenPrivKeyFromSecret([]byte("isolated-execution-validator"))
	verifiedVals := cmt.NewValidatorSet([]*cmt.Validator{cmt.NewValidator(validator.PubKey(), 10)})
	for height := int64(100); height <= 102; height++ {
		h := f.commits[height].Header
		h.ValidatorsHash = verifiedVals.Hash()
		h.NextValidatorsHash = verifiedVals.Hash()
		h.ProposerAddress = validator.PubKey().Address()
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
	bodyJSON, err := protojson.Marshal(&body)
	require.NoError(t, err)
	var bodyObject map[string]any
	require.NoError(t, json.Unmarshal(bodyJSON, &bodyObject))
	responseJSON, err := json.Marshal(result)
	require.NoError(t, err)
	var resultObject map[string]any
	require.NoError(t, json.Unmarshal(responseJSON, &resultObject))
	resultObject["height"] = "100"
	resultObject["txhash"] = f.observation.TxHash
	resultObject["timestamp"] = f.commits[100].Time.Format("2006-01-02T15:04:05.999999999Z07:00")
	resultObject["logs"] = []any{}
	// SDK protobuf zero-code omission is legitimate REST serialization.
	delete(resultObject, "code")
	f.rest = map[string]any{"tx": map[string]any{"body": bodyObject}, "tx_response": resultObject}
	trusted := trustedFixture(t, f, verifiedVals, fixtureAnchor(f))
	evidence, portable, err := trusted.ReadTransferProof(context.Background(), TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}, f.observation.TxHash)
	require.NoError(t, err)
	require.True(t, evidence.ConsensusAuthenticated())
	require.False(t, evidence.CreditAuthorized())
	verifier, err := NewProofVerifier(fixtureAnchor(f))
	require.NoError(t, err)
	verifier.now = func() time.Time { return f.now }
	authenticated, err := verifier.VerifyTransferProof(context.Background(), TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}, f.observation.TxHash, portable)
	require.NoError(t, err)
	require.Equal(t, data, authenticated.Observation().TxBytes)
	require.Equal(t, data, evidence.Observation().TxBytes)
	require.Equal(t, uint32(1), *evidence.Observation().TransferIndex, "actual SDK ante fee precedes MsgSend")
	deposit, depositProof, err := trusted.ReadDepositProof(context.Background(), f.intent, f.observation.TxHash)
	require.NoError(t, err)
	require.Equal(t, uint32(0), deposit.Receipt().TransferIndex, "canonical bank message identity is independent of ante fee events")
	verifiedDeposit, err := verifier.VerifyDepositProof(context.Background(), f.intent, f.observation.TxHash, depositProof)
	require.NoError(t, err)
	require.Equal(t, data, verifiedDeposit.Observation().TxBytes)
	require.False(t, verifiedDeposit.CreditAuthorized())

	if exportDir != "" {
		require.NoError(t, os.MkdirAll(exportDir, 0700))
		fixture := map[string]any{"fixture_only": true, "mainnet_authority": false, "intent": f.intent, "anchor": fixtureAnchor(f), "now": f.now, "deposit_proof": depositProof, "transfer_proof": portable, "deposit_observation": deposit.Observation(), "transfer_observation": evidence.Observation(), "deposit_receipt": deposit.Receipt(), "transfer_receipt": evidence.Receipt()}
		encoded, err := json.MarshalIndent(fixture, "", "  ")
		require.NoError(t, err)
		require.NoError(t, os.WriteFile(filepath.Join(exportDir, "isolated-sdk-proof.json"), encoded, 0600))
	}

}
