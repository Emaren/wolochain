package keeper

import (
	"github.com/emaren/wolochain/x/wolochain/types"
)

var _ types.QueryServer = Keeper{}
