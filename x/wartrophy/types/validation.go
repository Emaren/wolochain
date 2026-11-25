package types

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

var trophyIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9_]{2,99}$`)

// ValidateTrophyID validates stable, URL-safe trophy identifiers.
func ValidateTrophyID(trophyID string) error {
	if !trophyIDPattern.MatchString(trophyID) {
		return fmt.Errorf("%w: must match %s", ErrInvalidTrophyID, trophyIDPattern.String())
	}
	return nil
}

// ValidateDisplayName validates a human-readable trophy name.
func ValidateDisplayName(displayName string) error {
	displayName = strings.TrimSpace(displayName)
	if displayName == "" || len(displayName) > 160 {
		return fmt.Errorf("%w: display name must contain 1-160 characters", ErrInvalidMetadata)
	}
	return nil
}

// ValidateMetadataURI validates an HTTP(S) or IPFS metadata/image URI.
func ValidateMetadataURI(value string, required bool) error {
	value = strings.TrimSpace(value)
	if value == "" {
		if required {
			return fmt.Errorf("%w: metadata URI is required", ErrInvalidMetadata)
		}
		return nil
	}
	if len(value) > 500 {
		return fmt.Errorf("%w: URI exceeds 500 characters", ErrInvalidMetadata)
	}

	parsed, err := url.ParseRequestURI(value)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidMetadata, err)
	}
	switch parsed.Scheme {
	case "https", "http":
		if parsed.Host == "" {
			return fmt.Errorf("%w: HTTP URI must include a host", ErrInvalidMetadata)
		}
	case "ipfs":
		if parsed.Opaque == "" && parsed.Host == "" && parsed.Path == "" {
			return fmt.Errorf("%w: IPFS URI must include a path", ErrInvalidMetadata)
		}
	default:
		return fmt.Errorf("%w: unsupported URI scheme %q", ErrInvalidMetadata, parsed.Scheme)
	}
	return nil
}

// ValidateAddress validates a bech32 account address.
func ValidateAddress(value string) error {
	if _, err := sdk.AccAddressFromBech32(value); err != nil {
		return err
	}
	return nil
}

// ValidateStoredTrophy validates a trophy loaded from genesis.
func ValidateStoredTrophy(trophy Trophy) error {
	if err := ValidateTrophyID(trophy.TrophyId); err != nil {
		return err
	}
	if trophy.ClassId != WarTrophyClassID {
		return fmt.Errorf("%w: class id must be %q", ErrInvalidMetadata, WarTrophyClassID)
	}
	if err := ValidateDisplayName(trophy.DisplayName); err != nil {
		return err
	}
	if err := ValidateMetadataURI(trophy.MetadataUri, true); err != nil {
		return err
	}
	if err := ValidateMetadataURI(trophy.ImageUri, false); err != nil {
		return err
	}
	switch trophy.Status {
	case TrophyStatus_TROPHY_STATUS_DRAFT:
		if trophy.Minted {
			return fmt.Errorf("%w: draft trophy cannot be minted", ErrInvalidStatus)
		}
	case TrophyStatus_TROPHY_STATUS_ACTIVE:
		if !trophy.Minted {
			return fmt.Errorf("%w: active trophy must be minted", ErrInvalidStatus)
		}
	case TrophyStatus_TROPHY_STATUS_RETIRED:
		if trophy.Owner != "" {
			return fmt.Errorf("%w: retired trophy cannot have an owner", ErrInvalidStatus)
		}
	default:
		return ErrInvalidStatus
	}
	if trophy.Owner != "" {
		if err := ValidateAddress(trophy.Owner); err != nil {
			return err
		}
	}
	return nil
}
