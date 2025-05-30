package wolochain_test

import (
	"testing"

	keepertest "github.com/emaren/wolochain/testutil/keeper"
	"github.com/emaren/wolochain/testutil/nullify"
	"github.com/emaren/wolochain/x/wolochain"
	"github.com/emaren/wolochain/x/wolochain/types"
	"github.com/stretchr/testify/require"
)

func TestGenesis(t *testing.T) {
	genesisState := types.GenesisState{
		Params:	types.DefaultParams(),
		
		// this line is used by starport scaffolding # genesis/test/state
	}

	k, ctx := keepertest.WolochainKeeper(t)
	wolochain.InitGenesis(ctx, *k, genesisState)
	got := wolochain.ExportGenesis(ctx, *k)
	require.NotNil(t, got)

	nullify.Fill(&genesisState)
	nullify.Fill(got)

	

	// this line is used by starport scaffolding # genesis/test/assert
}
