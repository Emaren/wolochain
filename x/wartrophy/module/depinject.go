package wartrophy

import (
	"cosmossdk.io/core/address"
	"cosmossdk.io/core/appmodule"
	"cosmossdk.io/core/store"
	"cosmossdk.io/depinject"
	"cosmossdk.io/depinject/appconfig"
	"github.com/cosmos/cosmos-sdk/codec"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"

	"github.com/emaren/wolochain/x/wartrophy/keeper"
	"github.com/emaren/wolochain/x/wartrophy/types"
)

var _ depinject.OnePerModuleType = AppModule{}

// IsOnePerModuleType implements depinject.OnePerModuleType.
func (AppModule) IsOnePerModuleType() {}

func init() {
	appconfig.Register(
		&types.Module{},
		appconfig.Provide(ProvideModule),
	)
}

// ModuleInputs are wartrophy depinject inputs.
type ModuleInputs struct {
	depinject.In

	Config       *types.Module
	StoreService store.KVStoreService
	Cdc          codec.Codec
	AddressCodec address.Codec
}

// ModuleOutputs are wartrophy depinject outputs.
type ModuleOutputs struct {
	depinject.Out

	WarTrophyKeeper keeper.Keeper
	Module          appmodule.AppModule
}

// ProvideModule constructs the wartrophy keeper and app module.
func ProvideModule(in ModuleInputs) ModuleOutputs {
	authority := authtypes.NewModuleAddress(types.GovModuleName)
	if in.Config.Authority != "" {
		authority = authtypes.NewModuleAddressOrBech32Address(in.Config.Authority)
	}

	k := keeper.NewKeeper(in.StoreService, in.Cdc, in.AddressCodec, authority)
	m := NewAppModule(in.Cdc, k)
	return ModuleOutputs{WarTrophyKeeper: k, Module: m}
}
