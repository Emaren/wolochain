package types

import "fmt"

// DefaultGenesis returns an empty wartrophy genesis state.
func DefaultGenesis(authority string) *GenesisState {
	return &GenesisState{Authority: authority}
}

// Validate performs basic genesis validation.
func (gs GenesisState) Validate() error {
	if gs.Authority == "" {
		return ErrInvalidAuthority
	}
	if err := ValidateAddress(gs.Authority); err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidAuthority, err)
	}

	seen := make(map[string]struct{}, len(gs.Trophies))
	for _, trophy := range gs.Trophies {
		if _, ok := seen[trophy.TrophyId]; ok {
			return fmt.Errorf("%w: %s", ErrTrophyExists, trophy.TrophyId)
		}
		seen[trophy.TrophyId] = struct{}{}
		if err := ValidateStoredTrophy(trophy); err != nil {
			return fmt.Errorf("trophy %q: %w", trophy.TrophyId, err)
		}
	}
	return nil
}
