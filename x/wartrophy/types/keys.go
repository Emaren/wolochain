package types

import "cosmossdk.io/collections"

const (
	// ModuleName defines the wartrophy module name.
	ModuleName = "wartrophy"

	// StoreKey defines the wartrophy KV store key.
	StoreKey = ModuleName

	// GovModuleName avoids importing x/gov solely for its module name.
	GovModuleName = "gov"

	// WarTrophyClassID is reserved for AoE2WAR Warbound trophies.
	WarTrophyClassID = "aoe2war-war-trophies"
)

var (
	AuthorityKey = collections.NewPrefix("authority")
	TrophiesKey  = collections.NewPrefix("trophies")
)
