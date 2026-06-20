package keeper

import (
	"context"

	"github.com/emaren/wolochain/x/wartrophy/types"
)

// InitGenesis initializes wartrophy state.
func (k Keeper) InitGenesis(ctx context.Context, genesis types.GenesisState) error {
	authority := genesis.Authority
	if authority == "" {
		authority = k.defaultAuthority
	}
	if err := k.Authority.Set(ctx, authority); err != nil {
		return err
	}
	for _, trophy := range genesis.Trophies {
		if err := k.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
			return err
		}
	}
	return nil
}

// ExportGenesis exports wartrophy state.
func (k Keeper) ExportGenesis(ctx context.Context) (*types.GenesisState, error) {
	authority, err := k.GetAuthority(ctx)
	if err != nil {
		return nil, err
	}

	genesis := types.DefaultGenesis(authority)
	if err := k.Trophies.Walk(ctx, nil, func(_ string, trophy types.Trophy) (bool, error) {
		genesis.Trophies = append(genesis.Trophies, trophy)
		return false, nil
	}); err != nil {
		return nil, err
	}
	return genesis, nil
}
