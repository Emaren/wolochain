package app

import (
	"fmt"

	upgradetypes "cosmossdk.io/x/upgrade/types"

	warboundtrophyv1 "github.com/emaren/wolochain/app/upgrades/warbound_trophy_v1"
)

func (app *App) setupUpgradeHandlers() error {
	app.UpgradeKeeper.SetUpgradeHandler(
		warboundtrophyv1.UpgradeName,
		warboundtrophyv1.CreateUpgradeHandler(app.ModuleManager, app.Configurator()),
	)

	upgradeInfo, err := app.UpgradeKeeper.ReadUpgradeInfoFromDisk()
	if err != nil {
		return fmt.Errorf("read upgrade info: %w", err)
	}

	if upgradeInfo.Name == warboundtrophyv1.UpgradeName &&
		!app.UpgradeKeeper.IsSkipHeight(upgradeInfo.Height) {
		app.SetStoreLoader(
			upgradetypes.UpgradeStoreLoader(
				upgradeInfo.Height,
				&warboundtrophyv1.StoreUpgrades,
			),
		)
	}

	return nil
}
