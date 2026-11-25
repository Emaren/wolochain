package app_test

import (
	"encoding/json"
	"testing"

	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	upgradetypes "cosmossdk.io/x/upgrade/types"
	abci "github.com/cometbft/cometbft/abci/types"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	simtestutil "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"

	"github.com/emaren/wolochain/app"
	warboundtrophyv1 "github.com/emaren/wolochain/app/upgrades/warbound_trophy_v1"
	wartrophykeeper "github.com/emaren/wolochain/x/wartrophy/keeper"
	wartrophytypes "github.com/emaren/wolochain/x/wartrophy/types"
)

func TestWarboundTrophyUpgradeHandlerInitializesNewModuleOnce(t *testing.T) {
	application, account := initUpgradeTestApp(t)
	ctx := application.NewUncachedContext(false, cmtproto.Header{Height: 2})

	beforeBalance := application.BankKeeper.GetAllBalances(ctx, account)
	beforeSupply := application.BankKeeper.GetSupply(ctx, "uwolo")

	versionMap, err := application.UpgradeKeeper.GetModuleVersionMap(ctx)
	require.NoError(t, err)
	delete(versionMap, wartrophytypes.ModuleName)
	require.NoError(t, application.WarTrophyKeeper.Authority.Remove(ctx))

	handler := warboundtrophyv1.CreateUpgradeHandler(
		application.ModuleManager,
		application.Configurator(),
	)

	updatedMap, err := handler(
		ctx,
		warboundPlan(2),
		versionMap,
	)
	require.NoError(t, err)
	require.Equal(t, uint64(1), updatedMap[wartrophytypes.ModuleName])

	queryServer := wartrophykeeper.NewQueryServerImpl(application.WarTrophyKeeper)
	authority, err := queryServer.TrophyAuthority(
		ctx,
		&wartrophytypes.QueryTrophyAuthorityRequest{},
	)
	require.NoError(t, err)
	require.NotEmpty(t, authority.Authority)

	afterFirstBalance := application.BankKeeper.GetAllBalances(ctx, account)
	afterFirstSupply := application.BankKeeper.GetSupply(ctx, "uwolo")
	require.Equal(t, beforeBalance, afterFirstBalance)
	require.Equal(t, beforeSupply, afterFirstSupply)

	secondMap, err := handler(
		ctx,
		warboundPlan(2),
		updatedMap,
	)
	require.NoError(t, err)
	require.Equal(t, updatedMap, secondMap)

	afterSecondBalance := application.BankKeeper.GetAllBalances(ctx, account)
	afterSecondSupply := application.BankKeeper.GetSupply(ctx, "uwolo")
	require.Equal(t, beforeBalance, afterSecondBalance)
	require.Equal(t, beforeSupply, afterSecondSupply)

	authorityAfterSecondRun, err := queryServer.TrophyAuthority(
		ctx,
		&wartrophytypes.QueryTrophyAuthorityRequest{},
	)
	require.NoError(t, err)
	require.Equal(t, authority.Authority, authorityAfterSecondRun.Authority)
}

func initUpgradeTestApp(t *testing.T) (*app.App, sdk.AccAddress) {
	t.Helper()

	appOptions := viper.New()
	appOptions.Set(flags.FlagHome, t.TempDir())
	application := app.New(
		log.NewNopLogger(),
		dbm.NewMemDB(),
		nil,
		true,
		appOptions,
		baseapp.SetChainID("wartrophy-upgrade-test"),
	)

	validatorSet, err := simtestutil.CreateRandomValidatorSet()
	require.NoError(t, err)

	privateKey := secp256k1.GenPrivKey()
	account := sdk.AccAddress(privateKey.PubKey().Address())
	baseAccount := authtypes.NewBaseAccount(account, privateKey.PubKey(), 0, 0)
	balance := banktypes.Balance{
		Address: account.String(),
		Coins: sdk.NewCoins(
			sdk.NewCoin("uwolo", sdkmath.NewInt(1_000_000_000)),
		),
	}

	genesisState, err := simtestutil.GenesisStateWithValSet(
		application.AppCodec(),
		application.DefaultGenesis(),
		validatorSet,
		[]authtypes.GenesisAccount{baseAccount},
		balance,
	)
	require.NoError(t, err)

	appState, err := cmtjson.Marshal(genesisState)
	require.NoError(t, err)

	_, err = application.InitChain(&abci.RequestInitChain{
		ChainId:         "wartrophy-upgrade-test",
		AppStateBytes:   appState,
		ConsensusParams: simtestutil.DefaultConsensusParams,
	})
	require.NoError(t, err)

	_, err = application.FinalizeBlock(&abci.RequestFinalizeBlock{
		Height:             1,
		NextValidatorsHash: validatorSet.Hash(),
	})
	require.NoError(t, err)

	exported, err := application.ExportAppStateAndValidators(false, nil, nil)
	require.NoError(t, err)
	var exportedState map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(exported.AppState, &exportedState))
	require.Contains(t, exportedState, wartrophytypes.ModuleName)

	_, err = application.Commit()
	require.NoError(t, err)

	return application, account
}

func warboundPlan(height int64) upgradetypes.Plan {
	return upgradetypes.Plan{
		Name:   warboundtrophyv1.UpgradeName,
		Height: height,
	}
}
