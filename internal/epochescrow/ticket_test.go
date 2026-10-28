package epochescrow

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"strings"
	"testing"
	"time"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	bolt "go.etcd.io/bbolt"
)

// splitTicketFixture tests immutable accounting admission with private journal
// seals. Only the separate native SDK test authenticates physical bank proofs.
func splitTicketFixture(t *testing.T) (Policy, Request) {
	t.Helper()
	p, r := fixture(t)
	r.Plan.Wagers[0].PrincipalUWolo = "40000000"
	r.Plan.Wagers[1].PrincipalUWolo = "40000000"
	r.AmountUWolo = "78000000"
	fixtureTickets(t, p, &r)
	r.Tickets[0].OriginalFundingPrincipalUWolo = "100000000"
	r.Tickets[0].Allocations = append(r.Tickets[0].Allocations, TicketAllocation{11, 12, 3, "left", "60000000"})
	signFixtureTicket(t, p, &r.Tickets[0])
	selectedFixtureMandate(p, &r)
	resign(t, &r)
	if e := p.ValidateRequest(r, time.Now()); e != nil {
		t.Fatal(e)
	}
	return p, r
}

func secondSplitMarket(p Policy, r Request) Request {
	next := freezeRequest(r)
	next.MarketID, next.LegID, next.WagerID = 11, 12, 3
	next.Plan = Plan{p.EpochID, 11, "void", []Wager{{3, 11, 1, 12, r.OwnerUID, "left", "60000000", r.FundingTxHash, 0}}}
	next.Tickets = next.Tickets[:1]
	next.EntitlementID = EntitlementID(p.EpochID, next.MarketID, next.TicketID, next.LegID)
	next.OperationID = next.EntitlementID + ":return"
	next.Memo = ReturnMemo(p.EpochID, next.EntitlementID)
	next.AmountUWolo, next.Nonce = "60000000", strings.Repeat("e", 64)
	return next
}

func signWithFixtureKey(t *testing.T, p Policy, r *Request, key *secp.PrivKey) {
	t.Helper()
	for i := range r.Tickets {
		sig, e := key.Sign(OriginalTicketMessage(p, r.Tickets[i]))
		if e != nil {
			t.Fatal(e)
		}
		r.Tickets[i].OwnerSignature = base64.StdEncoding.EncodeToString(sig)
	}
	selectedFixtureMandate(p, r)
	sig, e := key.Sign(RequestMessage(*r))
	if e != nil {
		t.Fatal(e)
	}
	r.OwnerSignature = base64.StdEncoding.EncodeToString(sig)
	r.ReviewerSignature = base64.StdEncoding.EncodeToString(ed25519.Sign(ed25519.NewKeyFromSeed(bytes32(7)), RequestMessage(*r)))
}

func TestOneTicketCanPartitionSeveralLegsWithinOneMarket(t *testing.T) {
	p, r := splitTicketFixture(t)
	r.Tickets = r.Tickets[:1]
	r.Tickets[0].Allocations[1] = TicketAllocation{10, 12, 3, "right", "60000000"}
	r.Plan.Wagers[1] = Wager{3, 10, 1, 12, r.OwnerUID, "right", "60000000", r.FundingTxHash, 0}
	signFixtureTicket(t, p, &r.Tickets[0])
	selectedFixtureMandate(p, &r)
	resign(t, &r)
	if e := p.ValidateRequest(r, time.Now()); e != nil {
		t.Fatal("conserved repeated physical receipt refused", e)
	}
	bad := freezeRequest(r)
	bad.Plan.Wagers = bad.Plan.Wagers[:1]
	bad.AmountUWolo = "40000000"
	resign(t, &bad)
	if e := p.ValidateRequest(bad, time.Now()); e == nil || e.Error() != "ORIGINAL_TICKET_INVALID" {
		t.Fatal("omitted_current_market_leg reached partial market economics", e)
	}
}

func TestOriginalTicketCanonicalSigningAndWholePhysicalPrincipal(t *testing.T) {
	p, r := splitTicketFixture(t)
	ticket := r.Tickets[0]
	message := OriginalTicketMessage(p, ticket)
	digest := sha256.Sum256(message)
	if OriginalTicketDigest(p, ticket) != hex.EncodeToString(digest[:]) || r.OriginalMandateSHA256 != hex.EncodeToString(digest[:]) {
		t.Fatal("original mandate digest is not exact signing-byte SHA256")
	}
	ticket.OwnerSignature = "a different signature is excluded from original signing bytes"
	if string(message) != string(OriginalTicketMessage(p, ticket)) {
		t.Fatal("signature recursively changes original message")
	}
	otherPolicy := p
	otherPolicy.Vault = p.Escrow
	if string(message) == string(OriginalTicketMessage(otherPolicy, ticket)) {
		t.Fatal("original mandate did not bind native account pair")
	}
	if r.Tickets[0].OriginalFundingPrincipalUWolo == r.Plan.Wagers[0].PrincipalUWolo {
		t.Fatal("whole physical principal collapsed to the selected market leg")
	}
}

func TestOriginalTicketRejectsIncompleteAndConflictingPartitions(t *testing.T) {
	p, r := splitTicketFixture(t)
	cases := map[string]func(*Request){
		"oversplit":              func(r *Request) { r.Tickets[0].Allocations[1].AmountUWolo = "61000000" },
		"undersplit":             func(r *Request) { r.Tickets[0].Allocations[1].AmountUWolo = "59000000" },
		"fractional":             func(r *Request) { r.Tickets[0].Allocations[1].AmountUWolo = "60000001" },
		"noncanonical_amount":    func(r *Request) { r.Tickets[0].Allocations[1].AmountUWolo = "060000000" },
		"wrong_epoch":            func(r *Request) { r.Tickets[0].EpochID = "other_epoch_20261026" },
		"wrong_ordinal":          func(r *Request) { r.Tickets[0].FundingMessageIndex = 1 },
		"duplicate_receipt":      func(r *Request) { r.Tickets[1].FundingTxHash = r.Tickets[0].FundingTxHash },
		"duplicate_future_wager": func(r *Request) { r.Tickets[1].Allocations = []TicketAllocation{{11, 13, 3, "right", "40000000"}} },
		"duplicate_leg":          func(r *Request) { r.Tickets[0].Allocations[1] = r.Tickets[0].Allocations[0] },
		"unsorted_tickets":       func(r *Request) { r.Tickets[0], r.Tickets[1] = r.Tickets[1], r.Tickets[0] },
		"unsorted_legs": func(r *Request) {
			r.Tickets[0].Allocations[0], r.Tickets[0].Allocations[1] = r.Tickets[0].Allocations[1], r.Tickets[0].Allocations[0]
		},
		"unsafe_id":                          func(r *Request) { r.Tickets[0].Allocations[1].MarketID = 9007199254740992 },
		"wrong_owner":                        func(r *Request) { r.Tickets[0].OwnerUID = "other-owner" },
		"wrong_mandate":                      func(r *Request) { r.OriginalMandateSHA256 = strings.Repeat("a", 64) },
		"missing_signature":                  func(r *Request) { r.Tickets[1].OwnerSignature = "" },
		"changed_future_leg_after_signature": func(r *Request) { r.Tickets[0].Allocations[1].Side = "right" },
		"missing_ticket":                     func(r *Request) { r.Tickets = r.Tickets[:1] },
		"omitted_current_leg":                func(r *Request) { r.Plan.Wagers = r.Plan.Wagers[:1] },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			bad := freezeRequest(r)
			mutate(&bad)
			// Renew only the current owner/reviewer request signature. A changed
			// original partition must retain its independently valid mandate.
			resign(t, &bad)
			if e := p.ValidateRequest(bad, time.Now()); e == nil {
				t.Fatal("accepted altered or unauthenticated original partition")
			}
		})
	}
}

func TestOneTicketSharesReceiptAcrossMarketsAndRetainsUncertainty(t *testing.T) {
	p, r := splitTicketFixture(t)
	j, path := journalFixture(t, p)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, r)); e != nil {
		t.Fatal(e)
	}
	if _, e := j.Quarantine(r.OperationID, Fingerprint(r)); e != nil {
		t.Fatal(e)
	}
	if e := j.Close(); e != nil {
		t.Fatal(e)
	}
	j, e := OpenJournal(path, p)
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	next := secondSplitMarket(p, r)
	resign(t, &next)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, next)); e != nil {
		t.Fatal("conserved second market refused", e)
	}
	if _, e := j.Prepare(context.Background(), sealedFixture(p, next)); e != nil {
		t.Fatal("identical second-market lookup lost idempotence", e)
	}
	if d, e := j.Lookup(r.OperationID, Fingerprint(r)); e != nil || d.Status != UnknownNoReplay {
		t.Fatal("later market released original uncertainty", d, e)
	}
	if _, e := j.Execute(context.Background(), r.OperationID, Fingerprint(r)); e == nil || e.Error() != "UNCERTAIN_BROADCAST" {
		t.Fatal("original uncertain effect became executable", e)
	}
	_ = j.db.View(func(tx *bolt.Tx) error {
		if tx.Bucket(records).Stats().KeyN != 2 || string(tx.Bucket(metadata).Get([]byte("funding:wolo-1:"+r.FundingTxHash+":0"))) != r.OriginalMandateSHA256 {
			t.Fatal("multiple market legs duplicated original receipt authority")
		}
		return nil
	})
}

func TestJournalPinsCompleteTicketBeforeFutureMarket(t *testing.T) {
	for _, name := range []string{"receipt_changed_partition", "ticket_changed_receipt", "future_wager_reassigned", "owner_wallet_reassigned"} {
		t.Run(name, func(t *testing.T) {
			p, r := splitTicketFixture(t)
			j, _ := journalFixture(t, p)
			defer j.Close()
			if _, e := j.Prepare(context.Background(), sealedFixture(p, r)); e != nil {
				t.Fatal(e)
			}
			bad := secondSplitMarket(p, r)
			switch name {
			case "receipt_changed_partition":
				bad.Tickets[0].Allocations[1].Side, bad.Plan.Wagers[0].Side = "right", "right"
			case "ticket_changed_receipt":
				bad.Tickets[0].FundingTxHash, bad.Plan.Wagers[0].FundingTxHash, bad.FundingTxHash = strings.Repeat("C", 64), strings.Repeat("C", 64), strings.Repeat("C", 64)
			case "future_wager_reassigned":
				bad.Tickets[0].TicketID, bad.Plan.Wagers[0].TicketID, bad.TicketID = 4, 4, 4
				bad.Tickets[0].FundingTxHash, bad.Plan.Wagers[0].FundingTxHash, bad.FundingTxHash = strings.Repeat("C", 64), strings.Repeat("C", 64), strings.Repeat("C", 64)
				bad.Tickets[0].OriginalFundingPrincipalUWolo = "60000000"
				bad.Tickets[0].Allocations = []TicketAllocation{{11, 12, 3, "left", "60000000"}}
			case "owner_wallet_reassigned":
				// A separately signed new receipt cannot remap an existing HD UID.
				key := secp.GenPrivKeyFromSecret([]byte("disposable-epoch-v3-test-only/different-owner"))
				bad.OwnerPublicKeyHex = hex.EncodeToString(key.PubKey().Bytes())
				bad.OwnerWallet, _ = pubAddress(bad.OwnerPublicKeyHex)
				bad.Tickets[0].OwnerWallet, bad.Tickets[0].OwnerPublicKeyHex = bad.OwnerWallet, bad.OwnerPublicKeyHex
				bad.Tickets[0].TicketID, bad.Plan.Wagers[0].TicketID, bad.TicketID = 4, 4, 4
				bad.Tickets[0].FundingTxHash, bad.Plan.Wagers[0].FundingTxHash, bad.FundingTxHash = strings.Repeat("D", 64), strings.Repeat("D", 64), strings.Repeat("D", 64)
				bad.Tickets[0].Allocations = []TicketAllocation{{11, 14, 4, "left", "100000000"}}
				bad.Plan.Wagers[0].WagerID, bad.WagerID, bad.Plan.Wagers[0].LegID, bad.LegID = 4, 4, 14, 14
				bad.Plan.Wagers[0].PrincipalUWolo, bad.AmountUWolo = "100000000", "100000000"
			}
			bad.OriginalOperationID = OriginalOperationID(p.EpochID, bad.TicketID)
			bad.EntitlementID = EntitlementID(p.EpochID, bad.MarketID, bad.TicketID, bad.LegID)
			bad.OperationID, bad.Memo = bad.EntitlementID+":return", ReturnMemo(p.EpochID, bad.EntitlementID)
			if name == "owner_wallet_reassigned" {
				key := secp.GenPrivKeyFromSecret([]byte("disposable-epoch-v3-test-only/different-owner"))
				signWithFixtureKey(t, p, &bad, key)
			} else {
				signFixtureTicket(t, p, &bad.Tickets[0])
				selectedFixtureMandate(p, &bad)
				resign(t, &bad)
			}
			if e := p.ValidateRequest(bad, time.Now()); e != nil {
				t.Fatal("test must reach durable collision rather than malformed request", e)
			}
			if _, e := j.Prepare(context.Background(), sealedFixture(p, bad)); e == nil || e.Error() != "RETURN_ENTITLEMENT_COLLISION" {
				t.Fatal("immutable global ticket identity was reassigned", e)
			}
			_ = j.db.View(func(tx *bolt.Tx) error {
				if tx.Bucket(records).Stats().KeyN != 1 || tx.Bucket(nonces).Stats().KeyN != 1 {
					t.Fatal("ticket collision left partial admission")
				}
				return nil
			})
		})
	}
}

func TestJournalDetectsOriginalTicketPinTruncation(t *testing.T) {
	for _, prefix := range []string{"funding:", "ticket:", "allocation:", "owner:"} {
		t.Run(prefix, func(t *testing.T) {
			p, r := splitTicketFixture(t)
			j, path := journalFixture(t, p)
			if _, e := j.Prepare(context.Background(), sealedFixture(p, r)); e != nil {
				t.Fatal(e)
			}
			if e := j.db.Update(func(tx *bolt.Tx) error {
				for key := range preparationPins(p, r) {
					if strings.HasPrefix(key, prefix) {
						return tx.Bucket(metadata).Delete([]byte(key))
					}
				}
				return nil
			}); e != nil {
				t.Fatal(e)
			}
			if e := j.Close(); e != nil {
				t.Fatal(e)
			}
			if reopened, e := OpenJournal(path, p); e == nil {
				reopened.Close()
				t.Fatal("truncated original-ticket index reopened")
			}
		})
	}
}
