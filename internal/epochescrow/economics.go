package epochescrow

import (
	"errors"
	"math"
	"sort"
	"strconv"
)

type Outcome struct {
	Wager          Wager
	MatchedUWolo   string
	UnmatchedUWolo string
	PayoutUWolo    string
	FeeUWolo       string
}

// PlanSettlement reproduces HD bde1a408 betWagerSettlement's integer-WOLO
// matching, largest-remainder allocation and positive Math.round fee rule.
// Resolution and original funding still require independent authentication.
func PlanSettlement(p Plan) ([]Outcome, error) {
	invalid := func() ([]Outcome, error) { return nil, errors.New("epoch_settlement_economics_invalid") }
	if !epochPattern.MatchString(p.EpochID) || p.MarketID == 0 || len(p.Wagers) == 0 || len(p.Wagers) > 1000 || (p.Resolution != "left" && p.Resolution != "right" && p.Resolution != "void") {
		return invalid()
	}
	seenID, seenLeg, seenFunding := map[uint64]bool{}, map[string]bool{}, map[string]bool{}
	totals := map[string]uint64{"left": 0, "right": 0}
	amounts := map[uint64]uint64{}
	var previous uint64
	for _, w := range p.Wagers {
		n, e := number(w.PrincipalUWolo, false)
		leg := OriginalOperationID(p.EpochID, w.TicketID) + ":" + strconv.FormatUint(w.LegID, 10)
		if e != nil || n%1000000 != 0 || n > 10000000000 || w.WagerID == 0 || w.WagerID <= previous || w.MarketID != p.MarketID || w.TicketID == 0 || w.TicketID > 9007199254740991 || w.LegID == 0 || w.LegID > 9007199254740991 || w.WagerID > 9007199254740991 || w.MarketID > 9007199254740991 || !uidPattern.MatchString(w.OwnerUID) || (w.Side != "left" && w.Side != "right") || !txhash(w.FundingTxHash) || w.FundingMessageIndex != 0 || seenID[w.WagerID] || seenLeg[leg] || seenFunding[w.FundingTxHash] {
			return invalid()
		}
		previous = w.WagerID
		seenID[w.WagerID] = true
		seenLeg[leg] = true
		seenFunding[w.FundingTxHash] = true
		amounts[w.WagerID] = n / 1000000
		totals[w.Side] += n / 1000000
	}
	// HD #937 currently refuses duplicate original physical funding in one market.
	// Cross-market split funding needs a future globally conserved ticket partition;
	// this candidate never claims to authenticate that missing authority.
	matched := totals["left"]
	if totals["right"] < matched {
		matched = totals["right"]
	}
	if p.Resolution != "void" && totals[p.Resolution] == 0 {
		return invalid()
	}
	exposures := map[uint64]uint64{}
	for _, side := range []string{"left", "right"} {
		rows := []allocation{}
		for _, w := range p.Wagers {
			if w.Side == side {
				rows = append(rows, allocation{id: w.WagerID, stake: amounts[w.WagerID]})
			}
		}
		for id, n := range allocate(rows, matched) {
			exposures[id] = n
		}
	}
	var fee uint64
	if p.Resolution != "void" {
		fee = (matched*2*200 + 5000) / 10000
	}
	winners := []allocation{}
	for _, w := range p.Wagers {
		if w.Side == p.Resolution && exposures[w.WagerID] > 0 {
			winners = append(winners, allocation{id: w.WagerID, stake: exposures[w.WagerID]})
		}
	}
	fees := allocate(winners, fee)
	out := make([]Outcome, 0, len(p.Wagers))
	var principal, returned, charged uint64
	for _, w := range p.Wagers {
		amount, match := amounts[w.WagerID], exposures[w.WagerID]
		unmatched := amount - match
		payout, f := unmatched, uint64(0)
		if p.Resolution == "void" {
			payout = amount
		} else if w.Side == p.Resolution {
			f = fees[w.WagerID]
			payout = unmatched + match*2 - f
		}
		str := func(n uint64) string { return strconv.FormatUint(n*1000000, 10) }
		out = append(out, Outcome{w, str(match), str(unmatched), str(payout), str(f)})
		principal += amount
		returned += payout
		charged += f
	}
	if returned+charged != principal {
		return invalid()
	}
	return out, nil
}

type allocation struct {
	id, stake, base uint64
	remainder       float64
}

func allocate(rows []allocation, total uint64) map[uint64]uint64 {
	out := map[uint64]uint64{}
	var stakes uint64
	for _, r := range rows {
		stakes += r.stake
	}
	if total > stakes {
		total = stakes
	}
	if total == 0 || stakes == 0 {
		return out
	}
	var used uint64
	for i := range rows {
		// Match HD's JavaScript Number remainder ordering exactly, including
		// unequal IEEE-754 fractions for mathematically equal remainders.
		exact := float64(total) * float64(rows[i].stake) / float64(stakes)
		rows[i].base = uint64(math.Floor(exact))
		rows[i].remainder = exact - float64(rows[i].base)
		used += rows[i].base
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].remainder != rows[j].remainder {
			return rows[i].remainder > rows[j].remainder
		}
		if rows[i].stake != rows[j].stake {
			return rows[i].stake > rows[j].stake
		}
		return rows[i].id < rows[j].id
	})
	for i := range rows {
		if used < total {
			rows[i].base++
			used++
		}
		out[rows[i].id] = rows[i].base
	}
	return out
}
