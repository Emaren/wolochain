package warboundtrophyv1

import (
	"context"

	storetypes "cosmossdk.io/store/types"
	upgradetypes "cosmossdk.io/x/upgrade/types"
	"github.com/cosmos/cosmos-sdk/types/module"

	wartrophytypes "github.com/emaren/wolochain/x/wartrophy/types"
)

const (
	// UpgradeName is the governance software-upgrade plan name.
	UpgradeName = "warbound-trophy-v1"
)

// StoreUpgrades adds only the new x/wartrophy KV store. No existing store is
// renamed or deleted by this upgrade.
var StoreUpgrades = storetypes.StoreUpgrades{
	Added: []string{wartrophytypes.StoreKey},
}

// CreateUpgradeHandler returns the migration handler for warbound-trophy-v1.
//
// Because wartrophy is absent from the pre-upgrade version map,
// RunMigrations initializes its default genesis state and records consensus
// version 1. Existing modules remain at their recorded versions and therefore
// do not run unrelated migrations.
func CreateUpgradeHandler(
	manager *module.Manager,
	configurator module.Configurator,
) upgradetypes.UpgradeHandler {
	return func(
		ctx context.Context,
		_ upgradetypes.Plan,
		fromVM module.VersionMap,
	) (module.VersionMap, error) {
		return manager.RunMigrations(ctx, configurator, fromVM)
	}
}
