package types

import errorsmod "cosmossdk.io/errors"

var (
	ErrUnauthorized        = errorsmod.Register(ModuleName, 1100, "unauthorized trophy authority")
	ErrInvalidTrophyID     = errorsmod.Register(ModuleName, 1101, "invalid trophy id")
	ErrTrophyNotFound      = errorsmod.Register(ModuleName, 1102, "trophy not found")
	ErrTrophyExists        = errorsmod.Register(ModuleName, 1103, "trophy already exists")
	ErrInvalidStatus       = errorsmod.Register(ModuleName, 1104, "invalid trophy status")
	ErrTrophyNotMinted     = errorsmod.Register(ModuleName, 1105, "trophy is not minted")
	ErrTrophyAlreadyMinted = errorsmod.Register(ModuleName, 1106, "trophy is already minted")
	ErrTrophyAlreadyOwned  = errorsmod.Register(ModuleName, 1107, "trophy already has an owner")
	ErrTrophyHasNoOwner    = errorsmod.Register(ModuleName, 1108, "trophy has no owner")
	ErrSameOwner           = errorsmod.Register(ModuleName, 1109, "new owner matches current owner")
	ErrInvalidMetadata     = errorsmod.Register(ModuleName, 1110, "invalid trophy metadata")
	ErrInvalidAuthority    = errorsmod.Register(ModuleName, 1111, "invalid trophy authority")
)
