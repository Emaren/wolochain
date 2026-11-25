package wartrophy

import (
	"encoding/json"
	"fmt"

	"cosmossdk.io/core/appmodule"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	"github.com/grpc-ecosystem/grpc-gateway/runtime"
	"google.golang.org/grpc"

	"github.com/emaren/wolochain/x/wartrophy/keeper"
	"github.com/emaren/wolochain/x/wartrophy/types"
)

var (
	_ module.AppModuleBasic = (*AppModule)(nil)
	_ module.AppModule      = (*AppModule)(nil)
	_ module.HasGenesis     = (*AppModule)(nil)
	_ appmodule.AppModule   = (*AppModule)(nil)
)

// AppModule implements x/wartrophy.
type AppModule struct {
	cdc    codec.Codec
	keeper keeper.Keeper
}

// NewAppModule constructs x/wartrophy.
func NewAppModule(cdc codec.Codec, keeper keeper.Keeper) AppModule {
	return AppModule{cdc: cdc, keeper: keeper}
}

// IsAppModule implements appmodule.AppModule.
func (AppModule) IsAppModule() {}

// Name returns the module name.
func (AppModule) Name() string { return types.ModuleName }

// RegisterLegacyAminoCodec is retained for legacy module compatibility.
func (AppModule) RegisterLegacyAminoCodec(*codec.LegacyAmino) {}

// RegisterGRPCGatewayRoutes registers REST query routes.
func (AppModule) RegisterGRPCGatewayRoutes(clientCtx client.Context, mux *runtime.ServeMux) {
	if err := types.RegisterQueryHandlerClient(clientCtx.CmdContext, mux, types.NewQueryClient(clientCtx)); err != nil {
		panic(err)
	}
}

// RegisterInterfaces registers wartrophy message interfaces.
func (AppModule) RegisterInterfaces(registrar codectypes.InterfaceRegistry) {
	types.RegisterInterfaces(registrar)
}

// RegisterServices registers message and query services.
func (am AppModule) RegisterServices(registrar grpc.ServiceRegistrar) error {
	types.RegisterMsgServer(registrar, keeper.NewMsgServerImpl(am.keeper))
	types.RegisterQueryServer(registrar, keeper.NewQueryServerImpl(am.keeper))
	return nil
}

// DefaultGenesis returns an empty wartrophy genesis state.
func (am AppModule) DefaultGenesis(codec.JSONCodec) json.RawMessage {
	return am.cdc.MustMarshalJSON(types.DefaultGenesis(am.keeper.DefaultAuthority()))
}

// ValidateGenesis validates wartrophy genesis.
func (am AppModule) ValidateGenesis(_ codec.JSONCodec, _ client.TxEncodingConfig, bz json.RawMessage) error {
	var genesis types.GenesisState
	if err := am.cdc.UnmarshalJSON(bz, &genesis); err != nil {
		return fmt.Errorf("failed to unmarshal %s genesis state: %w", types.ModuleName, err)
	}
	return genesis.Validate()
}

// InitGenesis initializes wartrophy state.
func (am AppModule) InitGenesis(ctx sdk.Context, _ codec.JSONCodec, bz json.RawMessage) {
	var genesis types.GenesisState
	if err := am.cdc.UnmarshalJSON(bz, &genesis); err != nil {
		panic(fmt.Errorf("failed to unmarshal %s genesis state: %w", types.ModuleName, err))
	}
	if err := am.keeper.InitGenesis(ctx, genesis); err != nil {
		panic(fmt.Errorf("failed to initialize %s genesis state: %w", types.ModuleName, err))
	}
}

// ExportGenesis exports wartrophy state.
func (am AppModule) ExportGenesis(ctx sdk.Context, _ codec.JSONCodec) json.RawMessage {
	genesis, err := am.keeper.ExportGenesis(ctx)
	if err != nil {
		panic(fmt.Errorf("failed to export %s genesis state: %w", types.ModuleName, err))
	}
	return am.cdc.MustMarshalJSON(genesis)
}

// ConsensusVersion returns the initial wartrophy consensus version.
func (AppModule) ConsensusVersion() uint64 { return 1 }
