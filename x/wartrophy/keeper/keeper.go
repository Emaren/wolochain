package keeper

import (
	"context"
	"errors"
	"fmt"

	"cosmossdk.io/collections"
	"cosmossdk.io/core/address"
	corestore "cosmossdk.io/core/store"
	"github.com/cosmos/cosmos-sdk/codec"

	"github.com/emaren/wolochain/x/wartrophy/types"
)

// Keeper owns the authoritative Warbound trophy entitlement state.
type Keeper struct {
	storeService     corestore.KVStoreService
	cdc              codec.Codec
	addressCodec     address.Codec
	defaultAuthority string

	Schema    collections.Schema
	Authority collections.Item[string]
	Trophies  collections.Map[string, types.Trophy]
}

// NewKeeper constructs a wartrophy keeper.
func NewKeeper(
	storeService corestore.KVStoreService,
	cdc codec.Codec,
	addressCodec address.Codec,
	defaultAuthority []byte,
) Keeper {
	authority, err := addressCodec.BytesToString(defaultAuthority)
	if err != nil {
		panic(fmt.Sprintf("invalid wartrophy authority: %v", err))
	}

	sb := collections.NewSchemaBuilder(storeService)
	k := Keeper{
		storeService:     storeService,
		cdc:              cdc,
		addressCodec:     addressCodec,
		defaultAuthority: authority,
		Authority: collections.NewItem(
			sb,
			types.AuthorityKey,
			"authority",
			collections.StringValue,
		),
		Trophies: collections.NewMap(
			sb,
			types.TrophiesKey,
			"trophies",
			collections.StringKey,
			codec.CollValue[types.Trophy](cdc),
		),
	}

	k.Schema, err = sb.Build()
	if err != nil {
		panic(err)
	}
	return k
}

// GetAuthority returns the current authority, falling back to the app-config
// authority before upgrade initialization has written module state.
func (k Keeper) GetAuthority(ctx context.Context) (string, error) {
	authority, err := k.Authority.Get(ctx)
	if err == nil {
		return authority, nil
	}
	if errors.Is(err, collections.ErrNotFound) {
		return k.defaultAuthority, nil
	}
	return "", err
}

// DefaultAuthority returns the authority configured in app wiring.
func (k Keeper) DefaultAuthority() string {
	return k.defaultAuthority
}

func (k Keeper) validateAuthority(ctx context.Context, signer string) error {
	authority, err := k.GetAuthority(ctx)
	if err != nil {
		return err
	}
	if signer != authority {
		return types.ErrUnauthorized
	}
	return nil
}

func (k Keeper) validateAddress(value string) error {
	if _, err := k.addressCodec.StringToBytes(value); err != nil {
		return err
	}
	return nil
}
