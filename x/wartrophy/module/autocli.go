package wartrophy

import (
	autocliv1 "cosmossdk.io/api/cosmos/autocli/v1"

	"github.com/emaren/wolochain/x/wartrophy/types"
)

// AutoCLIOptions defines wartrophy tx and query commands.
func (AppModule) AutoCLIOptions() *autocliv1.ModuleOptions {
	return &autocliv1.ModuleOptions{
		Query: &autocliv1.ServiceCommandDescriptor{
			Service: types.Query_serviceDesc.ServiceName,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "Trophy",
					Use:       "trophy [trophy-id]",
					Short:     "Query one Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
					},
				},
				{
					RpcMethod: "Trophies",
					Use:       "trophies",
					Short:     "List Warbound trophies",
				},
				{
					RpcMethod: "TrophyOwner",
					Use:       "owner [trophy-id]",
					Short:     "Query the current trophy owner",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
					},
				},
				{
					RpcMethod: "TrophiesByOwner",
					Use:       "owner-trophies [owner]",
					Short:     "List active trophies assigned to an owner",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "owner"},
					},
				},
				{
					RpcMethod: "TrophyAuthority",
					Use:       "authority",
					Short:     "Query the Trophy Authority",
				},
			},
		},
		Tx: &autocliv1.ServiceCommandDescriptor{
			Service:              types.Msg_serviceDesc.ServiceName,
			EnhanceCustomCommand: true,
			RpcCommandOptions: []*autocliv1.RpcCommandOptions{
				{
					RpcMethod: "RegisterTrophy",
					Use:       "register [trophy-id] [display-name] [metadata-uri] [image-uri] [tribute-per-day-uwolo] [bounty-growth-per-day-uwolo]",
					Short:     "Register a draft Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
						{ProtoField: "display_name"},
						{ProtoField: "metadata_uri"},
						{ProtoField: "image_uri"},
						{ProtoField: "tribute_per_day_uwolo"},
						{ProtoField: "bounty_growth_per_day_uwolo"},
					},
				},
				{
					RpcMethod: "MintTrophy",
					Use:       "mint [trophy-id]",
					Short:     "Activate a registered Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
					},
				},
				{
					RpcMethod: "AssignTrophy",
					Use:       "assign [trophy-id] [owner]",
					Short:     "Assign a vacant Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
						{ProtoField: "owner"},
					},
				},
				{
					RpcMethod: "ReassignTrophy",
					Use:       "reassign [trophy-id] [new-owner]",
					Short:     "Reassign a held Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
						{ProtoField: "new_owner"},
					},
				},
				{
					RpcMethod: "RetireTrophy",
					Use:       "retire [trophy-id]",
					Short:     "Permanently retire a Warbound trophy",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
					},
				},
				{
					RpcMethod: "UpdateTrophyMetadata",
					Use:       "update-metadata [trophy-id] [display-name] [metadata-uri] [image-uri]",
					Short:     "Update Warbound trophy metadata",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "trophy_id"},
						{ProtoField: "display_name"},
						{ProtoField: "metadata_uri"},
						{ProtoField: "image_uri"},
					},
				},
				{
					RpcMethod: "SetTrophyAuthority",
					Use:       "set-authority [new-authority]",
					Short:     "Rotate the Trophy Authority",
					PositionalArgs: []*autocliv1.PositionalArgDescriptor{
						{ProtoField: "new_authority"},
					},
				},
			},
		},
	}
}
