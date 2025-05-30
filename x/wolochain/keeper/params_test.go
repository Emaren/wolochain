package keeper_test

import (
	"testing"

	"github.com/stretchr/testify/require"
	testkeeper "github.com/emaren/wolochain/testutil/keeper"
	"github.com/emaren/wolochain/x/wolochain/types"
)

func TestGetParams(t *testing.T) {
	k, ctx := testkeeper.WolochainKeeper(t)
	params := types.DefaultParams()

	k.SetParams(ctx, params)

	require.EqualValues(t, params, k.GetParams(ctx))
}
