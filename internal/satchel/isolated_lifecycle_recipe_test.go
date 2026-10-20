package satchel

// An opt-in, test-only recipe lets the real PostgreSQL integration fixture bind
// its already allocated canonical ticket and claim IDs to actual SDK MsgSends.
// It accepts role names, never external addresses, and cannot provision a key,
// broadcast to a node, create bank funds or weaken a production verifier.
import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/stretchr/testify/require"
)

type sdkLifecycleRecipe struct {
	Version  int                      `json:"version"`
	Scenario string                   `json:"scenario"`
	Now      string                   `json:"now,omitempty"`
	Steps    []sdkLifecycleRecipeStep `json:"steps"`
}
type sdkLifecycleRecipeStep struct {
	Name          string `json:"name"`
	SenderRole    string `json:"sender_role"`
	RecipientRole string `json:"recipient_role"`
	AmountUWolo   string `json:"amount_uwolo"`
	Memo          string `json:"memo"`
}

func validLifecycleRecipe(recipe sdkLifecycleRecipe) bool {
	if recipe.Version != 1 || !regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`).MatchString(recipe.Scenario) || len(recipe.Steps) < 1 || len(recipe.Steps) > 64 {
		return false
	}
	if recipe.Now != "" {
		if _, e := time.Parse(time.RFC3339Nano, recipe.Now); e != nil {
			return false
		}
	}
	roles := map[string]bool{"owner": true, "vault": true, "escrow": true, "opponent": true}
	names := map[string]bool{}
	for _, step := range recipe.Steps {
		amount, e := strconv.ParseInt(step.AmountUWolo, 10, 64)
		if !regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`).MatchString(step.Name) || names[step.Name] || !roles[step.SenderRole] || !roles[step.RecipientRole] || step.SenderRole == step.RecipientRole ||
			e != nil || amount < 1 || amount > 1000000000 || strconv.FormatInt(amount, 10) != step.AmountUWolo || len(step.Memo) < 1 || len(step.Memo) > 256 || !utf8.ValidString(step.Memo) || strings.ContainsAny(step.Memo, "\x00\r\n") {
			return false
		}
		names[step.Name] = true
	}
	return true
}
func readLifecycleRecipe(t *testing.T, path string) sdkLifecycleRecipe {
	t.Helper()
	require.True(t, filepath.IsAbs(path))
	info, e := os.Lstat(path)
	require.NoError(t, e)
	require.True(t, info.Mode().IsRegular())
	require.LessOrEqual(t, info.Size(), int64(64<<10))
	file, e := os.Open(path)
	require.NoError(t, e)
	defer file.Close()
	opened, e := file.Stat()
	require.NoError(t, e)
	require.True(t, os.SameFile(info, opened))
	raw, e := io.ReadAll(io.LimitReader(file, (64<<10)+1))
	require.NoError(t, e)
	require.LessOrEqual(t, len(raw), 64<<10)
	require.True(t, chainjson.ValidFolded(raw))
	var recipe sdkLifecycleRecipe
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	require.NoError(t, decoder.Decode(&recipe))
	require.True(t, validLifecycleRecipe(recipe))
	return recipe
}

func TestTwelveCanonicalTicketRecipeConservesPrincipalAndMatchedFees(t *testing.T) {
	r := twelveCanonicalTicketRecipe()
	balances := map[string]int64{"owner": 100000001, "vault": 100, "escrow": 100, "opponent": 100000004}
	wagers, unmatched, wins, losses := 0, 0, 0, 0
	for _, step := range r.Steps {
		amount, e := strconv.ParseInt(step.AmountUWolo, 10, 64)
		require.NoError(t, e)
		balances[step.SenderRole] -= amount + 1
		balances[step.RecipientRole] += amount
		if strings.HasPrefix(step.Name, "wager_") {
			wagers++
			require.Equal(t, int64(25000000), amount)
		}
		if strings.HasPrefix(step.Name, "full_unmatched_refund_") {
			unmatched++
			require.Equal(t, int64(25000000), amount)
		}
		if strings.HasPrefix(step.Name, "matched_owner_payout_") {
			wins++
			require.Equal(t, int64(49000000), amount)
		}
		if strings.HasPrefix(step.Name, "matched_opponent_payout_") {
			losses++
			require.Equal(t, int64(49000000), amount)
		}
	}
	require.Equal(t, 12, wagers)
	require.Equal(t, 8, unmatched)
	require.Equal(t, 2, wins)
	require.Equal(t, 2, losses)
	require.Equal(t, map[string]int64{"owner": 98000000, "vault": 87, "escrow": 4000088, "opponent": 98000000}, balances)
	// Owner/escrow operating buffers pay ante gas; matched economic fees stay
	// in escrow and are not claimed as the owner's custody balance.
	require.Equal(t, int64(4000000), balances["escrow"]-(100-int64(unmatched+wins+losses)))
}

// Canonical matched economics are whole-WOLO: 25+25 pays 49 and retains
// one WOLO, exactly 2%. Eight 25-WOLO unmatched refunds, two owner wins and
// two owner losses leave the original owner 98 WOLO and four fees in escrow.
func twelveCanonicalTicketRecipe() sdkLifecycleRecipe {
	r := sdkLifecycleRecipe{Version: 1, Scenario: "twelve_canonical_tickets"}
	add := func(name, from, to, amount, memo string) {
		r.Steps = append(r.Steps, sdkLifecycleRecipeStep{name, from, to, amount, memo})
	}
	add("deposit", "owner", "vault", "100000000", "aoe2war/satchel/v1/lifecycle-owner/abcdefghijklmnop")
	for ticket := 1; ticket <= 12; ticket++ {
		n := strconv.Itoa(ticket)
		memo := "AoE2HDBets bet ticket v1 · ticket " + n
		add("wager_"+n, "vault", "escrow", "25000000", memo)
		if ticket <= 8 {
			add("full_unmatched_refund_"+n, "escrow", "vault", "25000000", "aoe2war/satchel/claim-return/v1/"+strconv.Itoa(100+ticket))
			continue
		}
		add("counterparty_funding_"+n, "opponent", "escrow", "25000000", "AoE2HDBets bet ticket v1 · ticket "+strconv.Itoa(100+ticket))
		if ticket <= 10 {
			add("matched_owner_payout_"+n, "escrow", "vault", "49000000", "aoe2war/satchel/claim-return/v1/"+strconv.Itoa(100+ticket))
		} else {
			add("matched_opponent_payout_"+n, "escrow", "opponent", "49000000", "isolated-canonical-opponent-claim-"+n)
		}
	}
	add("withdrawal", "vault", "owner", "98000000", "aoe2war/satchel/withdraw/v1/00000000-0000-4000-8000-000000000001")
	return r
}

func TestLifecycleRecipeRejectsUnboundedOrAmbiguousInputs(t *testing.T) {
	good := twelveCanonicalTicketRecipe()
	require.True(t, validLifecycleRecipe(good))
	require.Len(t, good.Steps, 30)
	for _, mutation := range []string{"version", "scenario", "duplicate", "external", "same_role", "zero", "fraction", "leading_zero", "oversize", "many_steps", "bad_memo"} {
		t.Run(mutation, func(t *testing.T) {
			r := good
			r.Steps = append([]sdkLifecycleRecipeStep(nil), good.Steps...)
			switch mutation {
			case "version":
				r.Version = 2
			case "scenario":
				r.Scenario = "../external"
			case "duplicate":
				r.Steps[1].Name = r.Steps[0].Name
			case "external":
				r.Steps[0].RecipientRole = "wolo1attacker"
			case "same_role":
				r.Steps[0].RecipientRole = r.Steps[0].SenderRole
			case "zero":
				r.Steps[0].AmountUWolo = "0"
			case "fraction":
				r.Steps[0].AmountUWolo = "1.1"
			case "leading_zero":
				r.Steps[0].AmountUWolo = "0100000000"
			case "oversize":
				r.Steps[0].AmountUWolo = "1000000001"
			case "many_steps":
				r.Steps = make([]sdkLifecycleRecipeStep, 65)
			case "bad_memo":
				r.Steps[0].Memo = "foo\nbar"
			}
			require.False(t, validLifecycleRecipe(r))
		})
	}
}
