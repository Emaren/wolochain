package epochescrow

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"strconv"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

// TicketAllocation is one immutable economic leg of an original physical
// funding transfer. Its wire fields match HD's existing admit_ticket contract.
type TicketAllocation struct {
	MarketID    uint64 `json:"market_id"`
	LegID       uint64 `json:"leg_id"`
	WagerID     uint64 `json:"wager_id"`
	Side        string `json:"side"`
	AmountUWolo string `json:"amount_uwolo"`
}

// OriginalTicket authenticates the complete conserved partition, including
// future markets, rather than treating each leg as another physical transfer.
// The signature proves a key's mandate; HD/reviewer ownership provenance and
// global receipt consumption remain separate requirements.
type OriginalTicket struct {
	EpochID                       string             `json:"epoch_id"`
	TicketID                      uint64             `json:"ticket_id"`
	OwnerUID                      string             `json:"owner_uid"`
	OwnerWallet                   string             `json:"owner_wallet"`
	OwnerPublicKeyHex             string             `json:"owner_public_key_hex"`
	FundingTxHash                 string             `json:"funding_tx_hash"`
	FundingMessageIndex           uint32             `json:"funding_message_index"`
	OriginalFundingPrincipalUWolo string             `json:"original_funding_principal_uwolo"`
	Allocations                   []TicketAllocation `json:"allocations"`
	OwnerSignature                string             `json:"owner_signature"`
}

// OriginalTicketMessage is the sole canonical original-mandate signing domain.
// It binds the exact native receipt, account pair, memo and complete allocation.
// No signing helper or custody key is provided by production source.
func OriginalTicketMessage(p Policy, t OriginalTicket) []byte {
	t.OwnerSignature = ""
	b, _ := json.Marshal([]any{Protocol, "original-ticket", "wolo-1", "uwolo", p.Vault, p.Escrow, FundingMemo(t.EpochID, t.TicketID), t})
	return b
}

func OriginalTicketDigest(p Policy, t OriginalTicket) string {
	digest := sha256.Sum256(OriginalTicketMessage(p, t))
	return hex.EncodeToString(digest[:])
}

func safeID(n uint64) bool { return n > 0 && n <= 9007199254740991 }

// validateTickets requires canonical complete certificates for exactly the
// tickets in this market, and authenticates each original owner's mandate.
func (p Policy) validateTickets(r Request) error {
	refuse := func() error {
		return blocked("ORIGINAL_TICKET_INVALID", "Original physical funding and its complete owner-authorized partition disagree.", "review-original-ticket-partition")
	}
	if len(r.Tickets) == 0 || len(r.Tickets) > len(r.Plan.Wagers) {
		return refuse()
	}
	tickets := map[uint64]OriginalTicket{}
	receipts, allocations, owners := map[string]bool{}, map[string]bool{}, map[string]string{}
	var previous uint64
	for _, ticket := range r.Tickets {
		n, e := number(ticket.OriginalFundingPrincipalUWolo, false)
		pub, pe := pubAddress(ticket.OwnerPublicKeyHex)
		if ticket.EpochID != p.EpochID || !safeID(ticket.TicketID) || ticket.TicketID <= previous || !uidPattern.MatchString(ticket.OwnerUID) || pe != nil || pub != ticket.OwnerWallet || !address(ticket.OwnerWallet) || ticket.OwnerWallet == p.Vault || ticket.OwnerWallet == p.Escrow || ticket.OwnerWallet == p.FeeRecipient || !txhash(ticket.FundingTxHash) || ticket.FundingMessageIndex != 0 || receipts[ticket.FundingTxHash] || e != nil || n > 10000000000 || n%1000000 != 0 || len(ticket.Allocations) == 0 || len(ticket.Allocations) > 16 {
			return refuse()
		}
		previous = ticket.TicketID
		identity := hash([]string{ticket.OwnerWallet, ticket.OwnerPublicKeyHex})
		if old, ok := owners[ticket.OwnerUID]; ok && old != identity {
			return refuse()
		}
		owners[ticket.OwnerUID] = identity
		var total uint64
		var prior TicketAllocation
		for i, leg := range ticket.Allocations {
			amount, e := number(leg.AmountUWolo, false)
			key := strconv.FormatUint(leg.MarketID, 10) + ":" + strconv.FormatUint(leg.WagerID, 10)
			if !safeID(leg.MarketID) || !safeID(leg.LegID) || !safeID(leg.WagerID) || (leg.Side != "left" && leg.Side != "right") || e != nil || amount > n || amount%1000000 != 0 || allocations[key] || (i > 0 && (leg.MarketID < prior.MarketID || (leg.MarketID == prior.MarketID && leg.LegID <= prior.LegID))) {
				return refuse()
			}
			allocations[key] = true
			prior = leg
			total += amount
		}
		if total != n {
			return refuse()
		}
		key, _ := hex.DecodeString(ticket.OwnerPublicKeyHex)
		sig, e := base64.StdEncoding.Strict().DecodeString(ticket.OwnerSignature)
		if e != nil || len(sig) != 64 || base64.StdEncoding.EncodeToString(sig) != ticket.OwnerSignature || !(&secp.PubKey{Key: key}).VerifySignature(OriginalTicketMessage(p, ticket), sig) {
			return refuse()
		}
		receipts[ticket.FundingTxHash] = true
		tickets[ticket.TicketID] = ticket
	}
	used, marketWagers := map[uint64]bool{}, map[uint64]bool{}
	for _, wager := range r.Plan.Wagers {
		ticket, ok := tickets[wager.TicketID]
		if !ok || ticket.OwnerUID != wager.OwnerUID || ticket.FundingTxHash != wager.FundingTxHash || ticket.FundingMessageIndex != wager.FundingMessageIndex {
			return refuse()
		}
		found := false
		for _, leg := range ticket.Allocations {
			if leg.MarketID == wager.MarketID && leg.LegID == wager.LegID && leg.WagerID == wager.WagerID && leg.Side == wager.Side && leg.AmountUWolo == wager.PrincipalUWolo {
				found = true
			}
		}
		if !found {
			return refuse()
		}
		used[wager.TicketID] = true
		marketWagers[wager.WagerID] = true
	}
	if len(used) != len(tickets) {
		return refuse()
	}
	for _, ticket := range r.Tickets {
		for _, leg := range ticket.Allocations {
			if leg.MarketID == r.MarketID && !marketWagers[leg.WagerID] {
				return refuse()
			}
		}
	}
	selected, ok := tickets[r.TicketID]
	if !ok || selected.OwnerUID != r.OwnerUID || selected.OwnerWallet != r.OwnerWallet || selected.OwnerPublicKeyHex != r.OwnerPublicKeyHex || selected.FundingTxHash != r.FundingTxHash || selected.FundingMessageIndex != r.FundingMessageIndex || OriginalTicketDigest(p, selected) != r.OriginalMandateSHA256 {
		return refuse()
	}
	return nil
}

// preparationPins is shared by atomic admission and history validation. It
// reserves every original allocation, including a market not yet settled.
func preparationPins(p Policy, r Request) map[string]string {
	pins := map[string]string{"market-plan:" + r.EpochID + ":" + strconv.FormatUint(r.MarketID, 10): hash(r.Plan)}
	for _, ticket := range r.Tickets {
		digest := OriginalTicketDigest(p, ticket)
		pins["funding:wolo-1:"+ticket.FundingTxHash+":0"] = digest
		pins["ticket:"+ticket.EpochID+":"+strconv.FormatUint(ticket.TicketID, 10)] = digest
		pins["owner:"+ticket.EpochID+":"+ticket.OwnerUID] = hash([]string{ticket.OwnerWallet, ticket.OwnerPublicKeyHex})
		for _, leg := range ticket.Allocations {
			pins["allocation:"+ticket.EpochID+":"+strconv.FormatUint(leg.MarketID, 10)+":"+strconv.FormatUint(leg.WagerID, 10)] = digest + ":" + strconv.FormatUint(leg.LegID, 10)
		}
	}
	return pins
}
