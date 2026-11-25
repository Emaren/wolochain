package keeper

import (
	"context"
	"errors"
	"strings"

	"cosmossdk.io/collections"
	errorsmod "cosmossdk.io/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/emaren/wolochain/x/wartrophy/types"
)

type msgServer struct {
	Keeper
}

// NewMsgServerImpl returns the wartrophy message server.
func NewMsgServerImpl(keeper Keeper) types.MsgServer {
	return &msgServer{Keeper: keeper}
}

var _ types.MsgServer = (*msgServer)(nil)

func (s msgServer) RegisterTrophy(ctx context.Context, msg *types.MsgRegisterTrophy) (*types.MsgRegisterTrophyResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	if err := types.ValidateTrophyID(msg.TrophyId); err != nil {
		return nil, err
	}
	if err := types.ValidateDisplayName(msg.DisplayName); err != nil {
		return nil, err
	}
	if err := types.ValidateMetadataURI(msg.MetadataUri, true); err != nil {
		return nil, err
	}
	if err := types.ValidateMetadataURI(msg.ImageUri, false); err != nil {
		return nil, err
	}
	if has, err := s.Trophies.Has(ctx, msg.TrophyId); err != nil {
		return nil, err
	} else if has {
		return nil, errorsmod.Wrap(types.ErrTrophyExists, msg.TrophyId)
	}

	height := sdk.UnwrapSDKContext(ctx).BlockHeight()
	trophy := types.Trophy{
		TrophyId:                msg.TrophyId,
		ClassId:                 types.WarTrophyClassID,
		DisplayName:             strings.TrimSpace(msg.DisplayName),
		Status:                  types.TrophyStatus_TROPHY_STATUS_DRAFT,
		MetadataUri:             strings.TrimSpace(msg.MetadataUri),
		ImageUri:                strings.TrimSpace(msg.ImageUri),
		TributePerDayUwolo:      msg.TributePerDayUwolo,
		BountyGrowthPerDayUwolo: msg.BountyGrowthPerDayUwolo,
		CreatedHeight:           height,
		UpdatedHeight:           height,
	}
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.registered", trophy, "", "")
	return &types.MsgRegisterTrophyResponse{}, nil
}

func (s msgServer) MintTrophy(ctx context.Context, msg *types.MsgMintTrophy) (*types.MsgMintTrophyResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	trophy, err := s.getTrophy(ctx, msg.TrophyId)
	if err != nil {
		return nil, err
	}
	if trophy.Minted {
		return nil, types.ErrTrophyAlreadyMinted
	}
	if trophy.Status != types.TrophyStatus_TROPHY_STATUS_DRAFT {
		return nil, types.ErrInvalidStatus
	}

	trophy.Minted = true
	trophy.Status = types.TrophyStatus_TROPHY_STATUS_ACTIVE
	trophy.UpdatedHeight = sdk.UnwrapSDKContext(ctx).BlockHeight()
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.minted", trophy, "", "")
	return &types.MsgMintTrophyResponse{}, nil
}

func (s msgServer) AssignTrophy(ctx context.Context, msg *types.MsgAssignTrophy) (*types.MsgAssignTrophyResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	if err := s.validateAddress(msg.Owner); err != nil {
		return nil, err
	}
	trophy, err := s.getTrophy(ctx, msg.TrophyId)
	if err != nil {
		return nil, err
	}
	if !trophy.Minted {
		return nil, types.ErrTrophyNotMinted
	}
	if trophy.Status != types.TrophyStatus_TROPHY_STATUS_ACTIVE {
		return nil, types.ErrInvalidStatus
	}
	if trophy.Owner != "" {
		return nil, types.ErrTrophyAlreadyOwned
	}

	trophy.Owner = msg.Owner
	trophy.UpdatedHeight = sdk.UnwrapSDKContext(ctx).BlockHeight()
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.assigned", trophy, "", msg.Owner)
	return &types.MsgAssignTrophyResponse{}, nil
}

func (s msgServer) ReassignTrophy(ctx context.Context, msg *types.MsgReassignTrophy) (*types.MsgReassignTrophyResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	if err := s.validateAddress(msg.NewOwner); err != nil {
		return nil, err
	}
	trophy, err := s.getTrophy(ctx, msg.TrophyId)
	if err != nil {
		return nil, err
	}
	if !trophy.Minted {
		return nil, types.ErrTrophyNotMinted
	}
	if trophy.Status != types.TrophyStatus_TROPHY_STATUS_ACTIVE {
		return nil, types.ErrInvalidStatus
	}
	if trophy.Owner == "" {
		return nil, types.ErrTrophyHasNoOwner
	}
	if trophy.Owner == msg.NewOwner {
		return nil, types.ErrSameOwner
	}

	previousOwner := trophy.Owner
	trophy.Owner = msg.NewOwner
	trophy.UpdatedHeight = sdk.UnwrapSDKContext(ctx).BlockHeight()
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.reassigned", trophy, previousOwner, msg.NewOwner)
	return &types.MsgReassignTrophyResponse{}, nil
}

func (s msgServer) RetireTrophy(ctx context.Context, msg *types.MsgRetireTrophy) (*types.MsgRetireTrophyResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	trophy, err := s.getTrophy(ctx, msg.TrophyId)
	if err != nil {
		return nil, err
	}
	if trophy.Status == types.TrophyStatus_TROPHY_STATUS_RETIRED {
		return nil, types.ErrInvalidStatus
	}

	previousOwner := trophy.Owner
	trophy.Owner = ""
	trophy.Status = types.TrophyStatus_TROPHY_STATUS_RETIRED
	trophy.UpdatedHeight = sdk.UnwrapSDKContext(ctx).BlockHeight()
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.retired", trophy, previousOwner, "")
	return &types.MsgRetireTrophyResponse{}, nil
}

func (s msgServer) UpdateTrophyMetadata(ctx context.Context, msg *types.MsgUpdateTrophyMetadata) (*types.MsgUpdateTrophyMetadataResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	if err := types.ValidateDisplayName(msg.DisplayName); err != nil {
		return nil, err
	}
	if err := types.ValidateMetadataURI(msg.MetadataUri, true); err != nil {
		return nil, err
	}
	if err := types.ValidateMetadataURI(msg.ImageUri, false); err != nil {
		return nil, err
	}
	trophy, err := s.getTrophy(ctx, msg.TrophyId)
	if err != nil {
		return nil, err
	}

	trophy.DisplayName = strings.TrimSpace(msg.DisplayName)
	trophy.MetadataUri = strings.TrimSpace(msg.MetadataUri)
	trophy.ImageUri = strings.TrimSpace(msg.ImageUri)
	trophy.UpdatedHeight = sdk.UnwrapSDKContext(ctx).BlockHeight()
	if err := s.Trophies.Set(ctx, trophy.TrophyId, trophy); err != nil {
		return nil, err
	}
	emitEvent(ctx, "wartrophy.metadata_updated", trophy, trophy.Owner, trophy.Owner)
	return &types.MsgUpdateTrophyMetadataResponse{}, nil
}

func (s msgServer) SetTrophyAuthority(ctx context.Context, msg *types.MsgSetTrophyAuthority) (*types.MsgSetTrophyAuthorityResponse, error) {
	if err := s.validateAuthority(ctx, msg.Authority); err != nil {
		return nil, err
	}
	if err := s.validateAddress(msg.NewAuthority); err != nil {
		return nil, errorsmod.Wrap(types.ErrInvalidAuthority, err.Error())
	}
	if err := s.Authority.Set(ctx, msg.NewAuthority); err != nil {
		return nil, err
	}

	sdk.UnwrapSDKContext(ctx).EventManager().EmitEvent(
		sdk.NewEvent(
			"wartrophy.authority_updated",
			sdk.NewAttribute("previous_authority", msg.Authority),
			sdk.NewAttribute("authority", msg.NewAuthority),
		),
	)
	return &types.MsgSetTrophyAuthorityResponse{}, nil
}

func (s msgServer) getTrophy(ctx context.Context, trophyID string) (types.Trophy, error) {
	if err := types.ValidateTrophyID(trophyID); err != nil {
		return types.Trophy{}, err
	}
	trophy, err := s.Trophies.Get(ctx, trophyID)
	if errors.Is(err, collections.ErrNotFound) {
		return types.Trophy{}, errorsmod.Wrap(types.ErrTrophyNotFound, trophyID)
	}
	return trophy, err
}

func emitEvent(ctx context.Context, eventType string, trophy types.Trophy, previousOwner, owner string) {
	sdk.UnwrapSDKContext(ctx).EventManager().EmitEvent(
		sdk.NewEvent(
			eventType,
			sdk.NewAttribute("trophy_id", trophy.TrophyId),
			sdk.NewAttribute("class_id", trophy.ClassId),
			sdk.NewAttribute("status", trophy.Status.String()),
			sdk.NewAttribute("previous_owner", previousOwner),
			sdk.NewAttribute("owner", owner),
			sdk.NewAttribute("metadata_uri", trophy.MetadataUri),
		),
	)
}
