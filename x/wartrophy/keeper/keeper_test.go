package keeper_test

import (
	"context"
	"testing"

	"cosmossdk.io/core/address"
	storetypes "cosmossdk.io/store/types"
	addresscodec "github.com/cosmos/cosmos-sdk/codec/address"
	"github.com/cosmos/cosmos-sdk/runtime"
	"github.com/cosmos/cosmos-sdk/testutil"
	sdk "github.com/cosmos/cosmos-sdk/types"
	moduletestutil "github.com/cosmos/cosmos-sdk/types/module/testutil"
	"github.com/stretchr/testify/require"

	"github.com/emaren/wolochain/x/wartrophy/keeper"
	wartrophymodule "github.com/emaren/wolochain/x/wartrophy/module"
	"github.com/emaren/wolochain/x/wartrophy/types"
)

const (
	testTrophyID    = "canada_champion_belt"
	testMetadata    = "https://aoe2war.com/api/trophies/canada_champion_belt/metadata"
	testImage       = "https://aoe2war.com/images/trophies/canada_champion_belt.png"
	updatedMetadata = "https://aoe2war.com/api/trophies/canada_champion_belt/metadata?v=2"
)

type fixture struct {
	ctx          context.Context
	sdkCtx       sdk.Context
	keeper       keeper.Keeper
	msgServer    types.MsgServer
	queryServer  types.QueryServer
	addressCodec address.Codec
	authority    string
	other        string
	holderA      string
	holderB      string
}

func initFixture(t *testing.T) *fixture {
	t.Helper()

	encoding := moduletestutil.MakeTestEncodingConfig(wartrophymodule.AppModule{})
	storeKey := storetypes.NewKVStoreKey(types.StoreKey)
	storeService := runtime.NewKVStoreService(storeKey)
	sdkCtx := testutil.DefaultContextWithDB(
		t,
		storeKey,
		storetypes.NewTransientStoreKey("transient_wartrophy_test"),
	).Ctx.WithBlockHeight(42)

	codec := addresscodec.NewBech32Codec(sdk.GetConfig().GetBech32AccountAddrPrefix())
	toAddress := func(seed byte) string {
		value, err := codec.BytesToString(bytesOf(seed))
		require.NoError(t, err)
		return value
	}

	authority := toAddress(1)
	k := keeper.NewKeeper(storeService, encoding.Codec, codec, bytesOf(1))
	require.NoError(t, k.InitGenesis(sdkCtx, *types.DefaultGenesis(authority)))

	return &fixture{
		ctx:          sdkCtx,
		sdkCtx:       sdkCtx,
		keeper:       k,
		msgServer:    keeper.NewMsgServerImpl(k),
		queryServer:  keeper.NewQueryServerImpl(k),
		addressCodec: codec,
		authority:    authority,
		other:        toAddress(2),
		holderA:      toAddress(3),
		holderB:      toAddress(4),
	}
}

func bytesOf(seed byte) []byte {
	value := make([]byte, 20)
	for i := range value {
		value[i] = seed
	}
	return value
}

func registerMsg(authority string) *types.MsgRegisterTrophy {
	return &types.MsgRegisterTrophy{
		Authority:               authority,
		TrophyId:                testTrophyID,
		DisplayName:             "Canada Champion Belt",
		MetadataUri:             testMetadata,
		ImageUri:                testImage,
		TributePerDayUwolo:      10_000_000,
		BountyGrowthPerDayUwolo: 10_000_000,
	}
}

func registerAndMint(t *testing.T, f *fixture) {
	t.Helper()
	_, err := f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.authority))
	require.NoError(t, err)
	_, err = f.msgServer.MintTrophy(f.ctx, &types.MsgMintTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
	})
	require.NoError(t, err)
}

func assign(t *testing.T, f *fixture, owner string) {
	t.Helper()
	_, err := f.msgServer.AssignTrophy(f.ctx, &types.MsgAssignTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
		Owner:     owner,
	})
	require.NoError(t, err)
}

func TestRegisterTrophyAuthorityOnly(t *testing.T) {
	f := initFixture(t)

	_, err := f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.other))
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.authority))
	require.NoError(t, err)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.Equal(t, types.WarTrophyClassID, stored.ClassId)
	require.Equal(t, types.TrophyStatus_TROPHY_STATUS_DRAFT, stored.Status)
	require.False(t, stored.Minted)
	require.Empty(t, stored.Owner)
	require.Equal(t, uint64(10_000_000), stored.TributePerDayUwolo)
	require.Equal(t, uint64(10_000_000), stored.BountyGrowthPerDayUwolo)

	events := f.sdkCtx.EventManager().Events()
	require.Equal(t, "wartrophy.registered", events[len(events)-1].Type)
}

func TestMintTrophyAuthorityOnly(t *testing.T) {
	f := initFixture(t)
	_, err := f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.authority))
	require.NoError(t, err)

	_, err = f.msgServer.MintTrophy(f.ctx, &types.MsgMintTrophy{
		Authority: f.other,
		TrophyId:  testTrophyID,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.MintTrophy(f.ctx, &types.MsgMintTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
	})
	require.NoError(t, err)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.True(t, stored.Minted)
	require.Equal(t, types.TrophyStatus_TROPHY_STATUS_ACTIVE, stored.Status)
}

func TestAssignAndReassignTrophyAuthorityOnly(t *testing.T) {
	f := initFixture(t)
	registerAndMint(t, f)

	_, err := f.msgServer.AssignTrophy(f.ctx, &types.MsgAssignTrophy{
		Authority: f.other,
		TrophyId:  testTrophyID,
		Owner:     f.holderA,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	assign(t, f, f.holderA)

	_, err = f.msgServer.ReassignTrophy(f.ctx, &types.MsgReassignTrophy{
		Authority: f.other,
		TrophyId:  testTrophyID,
		NewOwner:  f.holderB,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.ReassignTrophy(f.ctx, &types.MsgReassignTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
		NewOwner:  f.holderB,
	})
	require.NoError(t, err)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.Equal(t, f.holderB, stored.Owner)
}

func TestHolderHasNoManualTransferPath(t *testing.T) {
	f := initFixture(t)
	registerAndMint(t, f)
	assign(t, f, f.holderA)

	// A holder attempting to use the only ownership-changing message as its
	// signer is rejected because the signer must be the Trophy Authority.
	_, err := f.msgServer.ReassignTrophy(f.ctx, &types.MsgReassignTrophy{
		Authority: f.holderA,
		TrophyId:  testTrophyID,
		NewOwner:  f.holderB,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.Equal(t, f.holderA, stored.Owner)
}

func TestRetiredTrophyCannotBeReassigned(t *testing.T) {
	f := initFixture(t)
	registerAndMint(t, f)
	assign(t, f, f.holderA)

	_, err := f.msgServer.RetireTrophy(f.ctx, &types.MsgRetireTrophy{
		Authority: f.other,
		TrophyId:  testTrophyID,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.RetireTrophy(f.ctx, &types.MsgRetireTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
	})
	require.NoError(t, err)

	_, err = f.msgServer.ReassignTrophy(f.ctx, &types.MsgReassignTrophy{
		Authority: f.authority,
		TrophyId:  testTrophyID,
		NewOwner:  f.holderB,
	})
	require.ErrorIs(t, err, types.ErrInvalidStatus)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.Equal(t, types.TrophyStatus_TROPHY_STATUS_RETIRED, stored.Status)
	require.Empty(t, stored.Owner)
}

func TestOwnerQueries(t *testing.T) {
	f := initFixture(t)
	registerAndMint(t, f)
	assign(t, f, f.holderA)

	owner, err := f.queryServer.TrophyOwner(f.ctx, &types.QueryTrophyOwnerRequest{
		TrophyId: testTrophyID,
	})
	require.NoError(t, err)
	require.Equal(t, f.holderA, owner.Owner)
	require.Equal(t, types.TrophyStatus_TROPHY_STATUS_ACTIVE, owner.Status)

	one, err := f.queryServer.Trophy(f.ctx, &types.QueryTrophyRequest{
		TrophyId: testTrophyID,
	})
	require.NoError(t, err)
	require.Equal(t, f.holderA, one.Trophy.Owner)

	all, err := f.queryServer.Trophies(f.ctx, &types.QueryTrophiesRequest{})
	require.NoError(t, err)
	require.Len(t, all.Trophies, 1)

	owned, err := f.queryServer.TrophiesByOwner(f.ctx, &types.QueryTrophiesByOwnerRequest{
		Owner: f.holderA,
	})
	require.NoError(t, err)
	require.Len(t, owned.Trophies, 1)
	require.Equal(t, testTrophyID, owned.Trophies[0].TrophyId)

	empty, err := f.queryServer.TrophiesByOwner(f.ctx, &types.QueryTrophiesByOwnerRequest{
		Owner: f.holderB,
	})
	require.NoError(t, err)
	require.Empty(t, empty.Trophies)
}

func TestMetadataUpdateAuthorityOnly(t *testing.T) {
	f := initFixture(t)
	registerAndMint(t, f)

	update := &types.MsgUpdateTrophyMetadata{
		Authority:   f.other,
		TrophyId:    testTrophyID,
		DisplayName: "Canada Champion Belt II",
		MetadataUri: updatedMetadata,
		ImageUri:    testImage,
	}
	_, err := f.msgServer.UpdateTrophyMetadata(f.ctx, update)
	require.ErrorIs(t, err, types.ErrUnauthorized)

	update.Authority = f.authority
	_, err = f.msgServer.UpdateTrophyMetadata(f.ctx, update)
	require.NoError(t, err)

	stored, err := f.keeper.Trophies.Get(f.ctx, testTrophyID)
	require.NoError(t, err)
	require.Equal(t, "Canada Champion Belt II", stored.DisplayName)
	require.Equal(t, updatedMetadata, stored.MetadataUri)
}

func TestAuthorityRotation(t *testing.T) {
	f := initFixture(t)

	_, err := f.msgServer.SetTrophyAuthority(f.ctx, &types.MsgSetTrophyAuthority{
		Authority:    f.other,
		NewAuthority: f.holderA,
	})
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.SetTrophyAuthority(f.ctx, &types.MsgSetTrophyAuthority{
		Authority:    f.authority,
		NewAuthority: f.other,
	})
	require.NoError(t, err)

	response, err := f.queryServer.TrophyAuthority(f.ctx, &types.QueryTrophyAuthorityRequest{})
	require.NoError(t, err)
	require.Equal(t, f.other, response.Authority)

	_, err = f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.authority))
	require.ErrorIs(t, err, types.ErrUnauthorized)

	_, err = f.msgServer.RegisterTrophy(f.ctx, registerMsg(f.other))
	require.NoError(t, err)
}
