package warboundtrophyv1_test

import (
	"testing"

	"cosmossdk.io/log"
	"cosmossdk.io/store/metrics"
	"cosmossdk.io/store/rootmulti"
	storetypes "cosmossdk.io/store/types"
	upgradetypes "cosmossdk.io/x/upgrade/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/stretchr/testify/require"

	warboundtrophyv1 "github.com/emaren/wolochain/app/upgrades/warbound_trophy_v1"
	wartrophytypes "github.com/emaren/wolochain/x/wartrophy/types"
)

func TestStoreUpgradesAddOnlyWarTrophy(t *testing.T) {
	require.Equal(t, []string{wartrophytypes.StoreKey}, warboundtrophyv1.StoreUpgrades.Added)
	require.Empty(t, warboundtrophyv1.StoreUpgrades.Deleted)
	require.Empty(t, warboundtrophyv1.StoreUpgrades.Renamed)
}

func TestUpgradeStoreLoaderPreservesExistingStores(t *testing.T) {
	const upgradeHeight int64 = 2

	db := dbm.NewMemDB()
	bankKey := storetypes.NewKVStoreKey("bank")
	stakingKey := storetypes.NewKVStoreKey("staking")
	trophyKey := storetypes.NewKVStoreKey(wartrophytypes.StoreKey)

	oldStore := rootmulti.NewStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	oldStore.MountStoreWithDB(bankKey, storetypes.StoreTypeIAVL, nil)
	oldStore.MountStoreWithDB(stakingKey, storetypes.StoreTypeIAVL, nil)
	require.NoError(t, oldStore.LoadLatestVersion())

	oldStore.GetKVStore(bankKey).Set([]byte("balance"), []byte("100000000uwolo"))
	oldStore.GetKVStore(stakingKey).Set([]byte("validator"), []byte("bonded"))
	require.Equal(t, int64(1), oldStore.Commit().Version)

	upgradedStore := rootmulti.NewStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	upgradedStore.MountStoreWithDB(bankKey, storetypes.StoreTypeIAVL, nil)
	upgradedStore.MountStoreWithDB(stakingKey, storetypes.StoreTypeIAVL, nil)
	upgradedStore.MountStoreWithDB(trophyKey, storetypes.StoreTypeIAVL, nil)

	loader := upgradetypes.UpgradeStoreLoader(
		upgradeHeight,
		&warboundtrophyv1.StoreUpgrades,
	)
	require.NoError(t, loader(upgradedStore))

	require.Equal(t, []byte("100000000uwolo"), upgradedStore.GetKVStore(bankKey).Get([]byte("balance")))
	require.Equal(t, []byte("bonded"), upgradedStore.GetKVStore(stakingKey).Get([]byte("validator")))
	require.NotNil(t, upgradedStore.GetKVStore(trophyKey))

	upgradedStore.GetKVStore(trophyKey).Set([]byte("authority"), []byte("wolo1authority"))
	require.Equal(t, upgradeHeight, upgradedStore.Commit().Version)

	reloadedStore := rootmulti.NewStore(db, log.NewNopLogger(), metrics.NewNoOpMetrics())
	reloadedStore.MountStoreWithDB(bankKey, storetypes.StoreTypeIAVL, nil)
	reloadedStore.MountStoreWithDB(stakingKey, storetypes.StoreTypeIAVL, nil)
	reloadedStore.MountStoreWithDB(trophyKey, storetypes.StoreTypeIAVL, nil)
	require.NoError(t, reloadedStore.LoadLatestVersion())

	require.Equal(t, []byte("100000000uwolo"), reloadedStore.GetKVStore(bankKey).Get([]byte("balance")))
	require.Equal(t, []byte("bonded"), reloadedStore.GetKVStore(stakingKey).Get([]byte("validator")))
	require.Equal(t, []byte("wolo1authority"), reloadedStore.GetKVStore(trophyKey).Get([]byte("authority")))
}
