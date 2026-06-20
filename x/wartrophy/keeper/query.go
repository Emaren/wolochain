package keeper

import (
	"context"
	"errors"

	"cosmossdk.io/collections"
	errorsmod "cosmossdk.io/errors"
	"github.com/cosmos/cosmos-sdk/types/query"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/emaren/wolochain/x/wartrophy/types"
)

type queryServer struct {
	k Keeper
}

// NewQueryServerImpl returns the wartrophy query server.
func NewQueryServerImpl(keeper Keeper) types.QueryServer {
	return &queryServer{k: keeper}
}

var _ types.QueryServer = (*queryServer)(nil)

func (q queryServer) Trophy(ctx context.Context, req *types.QueryTrophyRequest) (*types.QueryTrophyResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "empty request")
	}
	trophy, err := q.k.Trophies.Get(ctx, req.TrophyId)
	if errors.Is(err, collections.ErrNotFound) {
		return nil, errorsmod.Wrap(types.ErrTrophyNotFound, req.TrophyId)
	}
	if err != nil {
		return nil, err
	}
	return &types.QueryTrophyResponse{Trophy: &trophy}, nil
}

func (q queryServer) Trophies(ctx context.Context, req *types.QueryTrophiesRequest) (*types.QueryTrophiesResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "empty request")
	}
	trophies, page, err := query.CollectionPaginate(
		ctx,
		q.k.Trophies,
		req.Pagination,
		func(_ string, trophy types.Trophy) (types.Trophy, error) {
			return trophy, nil
		},
	)
	if err != nil {
		return nil, err
	}
	return &types.QueryTrophiesResponse{Trophies: trophies, Pagination: page}, nil
}

func (q queryServer) TrophyOwner(ctx context.Context, req *types.QueryTrophyOwnerRequest) (*types.QueryTrophyOwnerResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "empty request")
	}
	trophy, err := q.k.Trophies.Get(ctx, req.TrophyId)
	if errors.Is(err, collections.ErrNotFound) {
		return nil, errorsmod.Wrap(types.ErrTrophyNotFound, req.TrophyId)
	}
	if err != nil {
		return nil, err
	}
	return &types.QueryTrophyOwnerResponse{
		TrophyId: trophy.TrophyId,
		Owner:    trophy.Owner,
		Status:   trophy.Status,
	}, nil
}

func (q queryServer) TrophiesByOwner(ctx context.Context, req *types.QueryTrophiesByOwnerRequest) (*types.QueryTrophiesByOwnerResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "empty request")
	}
	if err := q.k.validateAddress(req.Owner); err != nil {
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}
	trophies, page, err := query.CollectionFilteredPaginate(
		ctx,
		q.k.Trophies,
		req.Pagination,
		func(_ string, trophy types.Trophy) (bool, error) {
			return trophy.Owner == req.Owner && trophy.Status == types.TrophyStatus_TROPHY_STATUS_ACTIVE, nil
		},
		func(_ string, trophy types.Trophy) (types.Trophy, error) {
			return trophy, nil
		},
	)
	if err != nil {
		return nil, err
	}
	return &types.QueryTrophiesByOwnerResponse{Trophies: trophies, Pagination: page}, nil
}

func (q queryServer) TrophyAuthority(ctx context.Context, req *types.QueryTrophyAuthorityRequest) (*types.QueryTrophyAuthorityResponse, error) {
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "empty request")
	}
	authority, err := q.k.GetAuthority(ctx)
	if err != nil {
		return nil, err
	}
	return &types.QueryTrophyAuthorityResponse{Authority: authority}, nil
}
