package epochescrow

// Deterministic disposable signing keys below authenticate policy fixtures only.
// Journal fixtures deliberately construct the private preparation seal to test
// persistence. They are not native bank proofs or production custody evidence.
import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	secp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/emaren/wolochain/internal/satchel"
	bolt "go.etcd.io/bbolt"
)

func fixture(t *testing.T) (Policy, Request) {
	t.Helper()
	key := func(name string) *secp.PrivKey {
		return secp.GenPrivKeyFromSecret([]byte("disposable-epoch-v3-test-only/" + name))
	}
	pub := func(name string) string { return hex.EncodeToString(key(name).PubKey().Bytes()) }
	addr := func(name string) string {
		a, e := pubAddress(pub(name))
		if e != nil {
			t.Fatal(e)
		}
		return a
	}
	reviewer := ed25519.NewKeyFromSeed(bytes32(7))
	now := time.Now().Unix()
	p := Policy{Version: 3, EpochID: "test_epoch_20261026", HStar: 1, Vault: addr("vault"), Escrow: addr("escrow"), VaultPublicKeyHex: pub("vault"), EscrowPublicKeyHex: pub("escrow"), VaultKeyringLineageSHA256: strings.Repeat("1", 64), EscrowKeyringLineageSHA256: strings.Repeat("2", 64), VaultUID: 1001, EscrowUID: 1002, LegacyUIDs: []uint32{1003}, LegacyPublicKeySHA256: []string{strings.Repeat("3", 64)}, LegacyKeyringLineageSHA256: []string{strings.Repeat("4", 64)}, ReviewerPublicKeyHex: hex.EncodeToString(reviewer.Public().(ed25519.PublicKey)), FeeRecipient: addr("fees"), GasFeeUWolo: "2500", SourceCommit: strings.Repeat("a", 40), BinarySHA256: strings.Repeat("b", 64), ConfigSHA256: strings.Repeat("c", 64), TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("d", 64), PeriodSeconds: 3600, EvidenceReference: "disposable-native-root-test-only"}}
	r := Request{BankStateHeight: 10, BankCommitHeight: 11, BankCommitHash: strings.Repeat("E", 64), BankAppHash: strings.Repeat("F", 64), Protocol: Protocol, Command: ReturnCommand, ChainID: "wolo-1", Denom: "uwolo", EpochID: p.EpochID, OriginalOperationID: OriginalOperationID(p.EpochID, 1), OwnerUID: "owner", OwnerWallet: addr("owner"), OwnerPublicKeyHex: pub("owner"), OriginalMandateSHA256: strings.Repeat("5", 64), WagerID: 1, TicketID: 1, MarketID: 10, LegID: 1, FundingTxHash: strings.Repeat("A", 64), Sender: p.Escrow, Recipient: p.Vault, AmountUWolo: "196000000", PolicySHA256: PolicyDigest(p), SourceCommit: p.SourceCommit, BinarySHA256: p.BinarySHA256, ConfigSHA256: p.ConfigSHA256, ResolutionEvidenceSHA256: strings.Repeat("6", 64), Nonce: strings.Repeat("7", 64), ReviewerPermitID: "reviewer-permit-1", IssuedAt: now, ExpiresAt: now + 90}
	r.EntitlementID = EntitlementID(p.EpochID, r.MarketID, r.TicketID, r.LegID)
	r.OperationID = r.EntitlementID + ":return"
	r.Memo = ReturnMemo(p.EpochID, r.EntitlementID)
	r.Plan = Plan{p.EpochID, 10, "left", []Wager{{1, 10, 1, 1, "owner", "left", "100000000", strings.Repeat("A", 64), 0}, {2, 10, 2, 2, "owner", "right", "300000000", strings.Repeat("B", 64), 0}}}
	r.VaultReserve = Reserve{p.Vault, "100000000", "0", "2500", "1", strings.Repeat("8", 64), strings.Repeat("9", 64)}
	r.EscrowReserve = Reserve{p.Escrow, "400000000", "0", "2500", "1", strings.Repeat("8", 64), strings.Repeat("9", 64)}
	fixtureTickets(t, p, &r)
	resign(t, &r)
	if e := p.ValidateRequest(r, time.Unix(now, 0)); e != nil {
		t.Fatalf("fixture: %v", e)
	}
	return p, r
}
func bytes32(n byte) []byte {
	b := make([]byte, 32)
	for i := range b {
		b[i] = n
	}
	return b
}
func resign(t *testing.T, r *Request) {
	t.Helper()
	owner := secp.GenPrivKeyFromSecret([]byte("disposable-epoch-v3-test-only/owner"))
	sig, e := owner.Sign(RequestMessage(*r))
	if e != nil {
		t.Fatal(e)
	}
	r.OwnerSignature = base64.StdEncoding.EncodeToString(sig)
	r.ReviewerSignature = base64.StdEncoding.EncodeToString(ed25519.Sign(ed25519.NewKeyFromSeed(bytes32(7)), RequestMessage(*r)))
}

func fixtureTickets(t *testing.T, p Policy, r *Request) {
	t.Helper()
	byID := map[uint64]*OriginalTicket{}
	for _, w := range r.Plan.Wagers {
		ticket := byID[w.TicketID]
		if ticket == nil {
			ticket = &OriginalTicket{EpochID: p.EpochID, TicketID: w.TicketID, OwnerUID: w.OwnerUID, OwnerWallet: r.OwnerWallet, OwnerPublicKeyHex: r.OwnerPublicKeyHex, FundingTxHash: w.FundingTxHash, FundingMessageIndex: w.FundingMessageIndex}
			byID[w.TicketID] = ticket
		}
		ticket.Allocations = append(ticket.Allocations, TicketAllocation{w.MarketID, w.LegID, w.WagerID, w.Side, w.PrincipalUWolo})
	}
	r.Tickets = nil
	for _, ticket := range byID {
		var total uint64
		for _, leg := range ticket.Allocations {
			n, e := number(leg.AmountUWolo, false)
			if e != nil {
				t.Fatal(e)
			}
			total += n
		}
		ticket.OriginalFundingPrincipalUWolo = strconv.FormatUint(total, 10)
		sort.Slice(ticket.Allocations, func(i, j int) bool {
			a, b := ticket.Allocations[i], ticket.Allocations[j]
			return a.MarketID < b.MarketID || (a.MarketID == b.MarketID && a.LegID < b.LegID)
		})
		signFixtureTicket(t, p, ticket)
		r.Tickets = append(r.Tickets, *ticket)
	}
	sort.Slice(r.Tickets, func(i, j int) bool { return r.Tickets[i].TicketID < r.Tickets[j].TicketID })
	selectedFixtureMandate(p, r)
}

func signFixtureTicket(t *testing.T, p Policy, ticket *OriginalTicket) {
	t.Helper()
	owner := secp.GenPrivKeyFromSecret([]byte("disposable-epoch-v3-test-only/owner"))
	sig, e := owner.Sign(OriginalTicketMessage(p, *ticket))
	if e != nil {
		t.Fatal(e)
	}
	ticket.OwnerSignature = base64.StdEncoding.EncodeToString(sig)
}

func selectedFixtureMandate(p Policy, r *Request) {
	for _, ticket := range r.Tickets {
		if ticket.TicketID == r.TicketID {
			r.OriginalMandateSHA256 = OriginalTicketDigest(p, ticket)
		}
	}
}
func sealedFixture(p Policy, r Request) VerifiedPreparation {
	return VerifiedPreparation{p, freezeRequest(r), Fingerprint(r), time.Unix(r.ExpiresAt, 0), true}
}
func journalFixture(t *testing.T, p Policy) (*Journal, string) {
	t.Helper()
	dir, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	if e = os.Chmod(dir, 0700); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "epoch.db")
	j, e := OpenJournal(path, p)
	if e != nil {
		t.Fatal(e)
	}
	return j, path
}

func TestHD937MatchedOnlyEconomics(t *testing.T) {
	_, r := fixture(t)
	cases := []struct{ name, left, right, resolution, payout1, payout2, fee1 string }{{"imbalanced_loser_refund", "100000000", "300000000", "left", "196000000", "200000000", "4000000"}, {"winner_unmatched_principal", "300000000", "100000000", "left", "396000000", "0", "4000000"}, {"void", "100000000", "300000000", "void", "100000000", "300000000", "0"}, {"whole_wolo_fee_rounding", "13000000", "13000000", "left", "25000000", "0", "1000000"}, {"below_fee_rounding_boundary", "12000000", "12000000", "left", "24000000", "0", "0"}}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := r.Plan
			p.Wagers = append([]Wager(nil), p.Wagers...)
			p.Wagers[0].PrincipalUWolo = tc.left
			p.Wagers[1].PrincipalUWolo = tc.right
			p.Resolution = tc.resolution
			out, e := PlanSettlement(p)
			if e != nil || out[0].PayoutUWolo != tc.payout1 || out[1].PayoutUWolo != tc.payout2 || out[0].FeeUWolo != tc.fee1 || out[1].FeeUWolo != "0" {
				t.Fatalf("unexpected native economics: %+v %v", out, e)
			}
		})
	}
	p := r.Plan
	p.Wagers = p.Wagers[:1]
	out, e := PlanSettlement(p)
	if e != nil || out[0].PayoutUWolo != "100000000" || out[0].FeeUWolo != "0" {
		t.Fatal(out, e)
	}
}
func TestPlanRejectsMalformedEconomics(t *testing.T) {
	_, r := fixture(t)
	for _, mutation := range []func(*Plan){func(p *Plan) { p.Wagers[1].MarketID++ }, func(p *Plan) { p.Wagers[1].FundingMessageIndex = 1 }, func(p *Plan) { p.Wagers[0].PrincipalUWolo = "100000001" }, func(p *Plan) { p.Wagers[0], p.Wagers[1] = p.Wagers[1], p.Wagers[0] }} {
		p := r.Plan
		p.Wagers = append([]Wager(nil), p.Wagers...)
		mutation(&p)
		if _, e := PlanSettlement(p); e == nil {
			t.Fatal("accepted malformed economic plan")
		}
	}
}
func TestStrictEpochOwnerFeeAndLegacyDomain(t *testing.T) {
	p, r := fixture(t)
	cases := map[string]func(*Request){"wrong_chain": func(r *Request) { r.ChainID = "wolo-2" }, "wrong_epoch": func(r *Request) { r.EpochID = "other_epoch_20261026" }, "wrong_owner": func(r *Request) { r.OwnerUID = "other" }, "wrong_sender": func(r *Request) { r.Sender = p.Vault }, "wrong_leg": func(r *Request) { r.LegID++ }, "wrong_ordinal": func(r *Request) { r.FundingMessageIndex = 1 }, "old_claim": func(r *Request) { r.OperationID = "satchel:claim-return:889" }, "old_memo": func(r *Request) { r.Memo = "aoe2war/satchel/claim-return/v1/8477" }, "legacy8092": func(r *Request) { r.Command = "/settlement/v1/runs" }, "flat_fee_on_unmatched": func(r *Request) { r.AmountUWolo = "192000000" }, "stale": func(r *Request) { r.ExpiresAt = r.IssuedAt }, "missing_mandate": func(r *Request) { r.OriginalMandateSHA256 = "" }, "policy_drift": func(r *Request) { r.PolicySHA256 = strings.Repeat("f", 64) }, "old_signature": func(r *Request) { r.Protocol = "aoe2war/satchel/claim-return-approval/v2" }}
	for name, mutation := range cases {
		t.Run(name, func(t *testing.T) {
			copy := freezeRequest(r)
			mutation(&copy)
			resign(t, &copy)
			if e := p.ValidateRequest(copy, time.Now()); e == nil {
				t.Fatal("accepted conflicting v3 identity")
			}
		})
	}
	fee := freezeRequest(r)
	fee.Command = FeeCommand
	fee.OperationID = fee.EntitlementID + ":fee"
	fee.Recipient = p.FeeRecipient
	fee.Memo = "aoe2war/satchel/epoch-v3/" + p.EpochID + "/fee/" + fee.EntitlementID
	fee.AmountUWolo = "4000000"
	resign(t, &fee)
	if e := p.ValidateRequest(fee, time.Now()); e != nil {
		t.Fatal(e)
	}
	fee.Recipient = p.Vault
	resign(t, &fee)
	if e := p.ValidateRequest(fee, time.Now()); e == nil {
		t.Fatal("fee recipient collision")
	}
}
func TestPolicyRejectsLegacyAuthorityAndSharedRuntime(t *testing.T) {
	p, _ := fixture(t)
	cases := []func(*Policy){func(p *Policy) { p.EscrowUID = p.VaultUID }, func(p *Policy) { p.EscrowKeyringLineageSHA256 = p.VaultKeyringLineageSHA256 }, func(p *Policy) { p.EscrowPublicKeyHex = p.VaultPublicKeyHex }, func(p *Policy) { p.LegacyUIDs = []uint32{p.EscrowUID} }, func(p *Policy) {
		key, _ := hex.DecodeString(p.EscrowPublicKeyHex)
		sum := sha256.Sum256(key)
		p.LegacyPublicKeySHA256 = []string{hex.EncodeToString(sum[:])}
	}, func(p *Policy) { p.LegacyKeyringLineageSHA256 = []string{p.EscrowKeyringLineageSHA256} }}
	for _, mutate := range cases {
		copy := p
		mutate(&copy)
		if e := copy.Validate(); e == nil {
			t.Fatal("accepted legacy/shared authority")
		}
	}
}
func TestMissingNativeProofCannotPrepareOrObserve(t *testing.T) {
	p, r := fixture(t)
	if _, e := VerifyPreparation(context.Background(), p, r, Proofs{}); e == nil {
		t.Fatal("missing native proof accepted")
	}
	if _, e := ObserveReturn(context.Background(), p, r, strings.Repeat("C", 64), satchel.PortableProof{}); e == nil {
		t.Fatal("synthetic return accepted")
	}
	j, _ := journalFixture(t, p)
	defer j.Close()
	if _, e := j.Prepare(context.Background(), VerifiedPreparation{}); e == nil {
		t.Fatal("zero native seal accepted")
	}
}
func TestAccountLocalReserveCannotNetOtherAccount(t *testing.T) {
	p, r := fixture(t)
	if !reserveCovers(r.VaultReserve, p.Vault, "99999999999999", 0) {
		t.Fatal("fixture vault")
	}
	if reserveCovers(r.EscrowReserve, p.Escrow, "400000000", 196002500) {
		t.Fatal("escrow deficit covered by unrelated vault surplus")
	}
	if !reserveCovers(r.EscrowReserve, p.Escrow, "596005001", 196002500) {
		t.Fatal("exact reserve boundary refused")
	}
	r.EscrowReserve.GasReserveUWolo = "0"
	if reserveCovers(r.EscrowReserve, p.Escrow, "99999999999999", 1) {
		t.Fatal("zero gas reserve")
	}
}
func TestJournalPermanentDecisionAndUnknownSurviveRestart(t *testing.T) {
	p, r := fixture(t)
	j, path := journalFixture(t, p)
	v := sealedFixture(p, r)
	first, e := j.Prepare(context.Background(), v)
	if e != nil {
		t.Fatal(e)
	}
	again, e := j.Prepare(context.Background(), v)
	if e != nil || again.Fingerprint != first.Fingerprint {
		t.Fatal(again, e)
	}
	if _, e = j.Execute(context.Background(), r.OperationID, Fingerprint(r)); e == nil {
		t.Fatal("unprovisioned executor authorized")
	} else {
		var b *Blocker
		if !errors.As(e, &b) || b.Code != "NEW_ESCROW_SIGNER_ABSENT" {
			t.Fatal(e)
		}
	}
	unknown, e := j.Quarantine(r.OperationID, Fingerprint(r))
	if e != nil || unknown.Status != UnknownNoReplay {
		t.Fatal(unknown, e)
	}
	if e = j.Close(); e != nil {
		t.Fatal(e)
	}
	j, e = OpenJournal(path, p)
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	d, e := j.Lookup(r.OperationID, Fingerprint(r))
	if e != nil || d.Status != UnknownNoReplay {
		t.Fatal(d, e)
	}
	if _, e = j.Execute(context.Background(), r.OperationID, Fingerprint(r)); e == nil {
		t.Fatal("unknown replayed")
	}
	j.now = func() time.Time { return time.Unix(r.ExpiresAt+1, 0) }
	if d, e = j.Lookup(r.OperationID, Fingerprint(r)); e != nil || d.Status != UnknownNoReplay {
		t.Fatal("expired lookup lost hold", e)
	}
}
func TestJournalConcurrentDuplicateAndChangedPayload(t *testing.T) {
	p, r := fixture(t)
	j, _ := journalFixture(t, p)
	defer j.Close()
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); _, e := j.Prepare(context.Background(), sealedFixture(p, r)); errs <- e }()
	}
	wg.Wait()
	close(errs)
	for e := range errs {
		if e != nil {
			t.Fatal(e)
		}
	}
	changed := freezeRequest(r)
	changed.Nonce = strings.Repeat("e", 64)
	resign(t, &changed)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, changed)); e == nil {
		t.Fatal("changed immutable request accepted")
	}
	_ = j.db.View(func(tx *bolt.Tx) error {
		if tx.Bucket(events).Stats().KeyN != 1 || tx.Bucket(records).Stats().KeyN != 1 {
			t.Fatal("duplicate decision/event")
		}
		return nil
	})
}
func TestJournalNonceReuseAndMarketEquivocation(t *testing.T) {
	p, r := fixture(t)
	j, _ := journalFixture(t, p)
	defer j.Close()
	if _, e := j.Prepare(context.Background(), sealedFixture(p, r)); e != nil {
		t.Fatal(e)
	}
	next := freezeRequest(r)
	w := next.Plan.Wagers[1]
	next.WagerID = w.WagerID
	next.TicketID = w.TicketID
	next.LegID = w.LegID
	next.OriginalOperationID = OriginalOperationID(p.EpochID, w.TicketID)
	next.FundingTxHash = w.FundingTxHash
	next.EntitlementID = EntitlementID(p.EpochID, w.MarketID, w.TicketID, w.LegID)
	next.OperationID = next.EntitlementID + ":return"
	next.Memo = ReturnMemo(p.EpochID, next.EntitlementID)
	next.AmountUWolo = "200000000"
	selectedFixtureMandate(p, &next)
	resign(t, &next)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, next)); e == nil {
		t.Fatal("nonce reused")
	}
	next.Nonce = strings.Repeat("e", 64)
	resign(t, &next)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, next)); e != nil {
		t.Fatal("independent entitlement refused", e)
	}
	changed := freezeRequest(r)
	changed.Plan.Resolution = "void"
	changed.AmountUWolo = "100000000"
	changed.Nonce = strings.Repeat("f", 64)
	resign(t, &changed)
	if _, e := j.Prepare(context.Background(), sealedFixture(p, changed)); e == nil {
		t.Fatal("market equivocation accepted")
	}
}
func TestJournalDetectsEventAndIndexTruncation(t *testing.T) {
	for _, name := range []string{"events", "nonce", "signature"} {
		t.Run(name, func(t *testing.T) {
			p, r := fixture(t)
			j, path := journalFixture(t, p)
			if _, e := j.Prepare(context.Background(), sealedFixture(p, r)); e != nil {
				t.Fatal(e)
			}
			e := j.db.Update(func(tx *bolt.Tx) error {
				switch name {
				case "events":
					k, _ := tx.Bucket(events).Cursor().First()
					return tx.Bucket(events).Delete(k)
				case "nonce":
					return tx.Bucket(nonces).Delete([]byte(r.Nonce))
				default:
					d, e := readDecision(tx, r.OperationID)
					if e != nil {
						return e
					}
					d.Request.OwnerSignature = strings.Repeat("A", 88)
					b, _ := json.Marshal(d)
					return tx.Bucket(records).Put([]byte(r.OperationID), b)
				}
			})
			if e != nil {
				t.Fatal(e)
			}
			j.Close()
			if reopened, e := OpenJournal(path, p); e == nil {
				reopened.Close()
				t.Fatal("corrupt history reopened")
			}
		})
	}
}

func TestExpiredOriginalReturnRemainsObservableWithoutExecutionAuthority(t *testing.T) {
	p, r := fixture(t)
	r.IssuedAt = time.Now().Unix() - 200
	r.ExpiresAt = r.IssuedAt + 90
	resign(t, &r)
	if p.ValidateRequest(r, time.Now()) == nil {
		t.Fatal("expired execution request accepted")
	}
	// The immutable historical authorization is still verified; failure comes
	// from absent native evidence rather than expiry of original spending power.
	_, err := ObserveReturn(context.Background(), p, r, strings.Repeat("C", 64), satchel.PortableProof{})
	if err == nil || err.Error() != "epoch_return_observation_refused" {
		t.Fatalf("expired original could not reach read-only native verification: %v", err)
	}
	r.OwnerUID = "different"
	if _, err = ObserveReturn(context.Background(), p, r, strings.Repeat("C", 64), satchel.PortableProof{}); err == nil || err.Error() != "ORIGINAL_TICKET_INVALID" {
		t.Fatal("historical observer lost original ownership", err)
	}
}
func TestJournalRechecksNativeExpiryInsideWriteTransaction(t *testing.T) {
	for _, validCalls := range []int{2, 4} {
		t.Run(fmt.Sprintf("expire_after_%d_checks", validCalls), func(t *testing.T) {
			p, r := fixture(t)
			j, _ := journalFixture(t, p)
			defer j.Close()
			v := sealedFixture(p, r)
			calls := 0
			j.now = func() time.Time {
				calls++
				if calls <= validCalls {
					return time.Unix(r.IssuedAt, 0)
				}
				return time.Unix(r.ExpiresAt+1, 0)
			}
			if _, err := j.Prepare(context.Background(), v); err == nil {
				t.Fatal("proof expired during admission")
			}
			_ = j.db.View(func(tx *bolt.Tx) error {
				if tx.Bucket(records).Stats().KeyN != 0 || tx.Bucket(events).Stats().KeyN != 0 || tx.Bucket(nonces).Stats().KeyN != 0 {
					t.Fatal("expired admission left partial mutation")
				}
				return nil
			})
		})
	}
}

func TestJournalCapacityHoldRollsBackAndRetainsReadableHistory(t *testing.T) {
	p, r := fixture(t)
	r.Plan.Wagers = nil
	for i := uint64(1); i <= 1000; i++ {
		side := "left"
		if i%2 == 0 {
			side = "right"
		}
		// Keep 1,000 economic legs while exercising the conserved-ticket contract.
		// Sixteen legs per original receipt bound repeated signature work under race.
		ticketID := 1 + (i-1)/16
		r.Plan.Wagers = append(r.Plan.Wagers, Wager{i, 10, ticketID, i, "owner", side, "1000000", fmt.Sprintf("%064X", ticketID), 0})
	}
	fixtureTickets(t, p, &r)
	if len(r.Tickets) != 63 {
		t.Fatal("capacity fixture lost its conserved physical-ticket grouping")
	}
	outcomes, e := PlanSettlement(r.Plan)
	if e != nil {
		t.Fatal(e)
	}
	j, _ := journalFixture(t, p)
	defer j.Close()
	// This test uses private synthetic journal seals, not native proofs. Race
	// instrumentation can take longer than their90s fixture permit; keep its
	// injected unit-test clock fixed while testing the byte/event envelope.
	// Production and the fresh native SDK harness always retain real time.
	j.now = func() time.Time { return time.Unix(r.IssuedAt, 0) }
	var first, last Request
	var admitted int
	capacity := false
	for i := 0; i < len(outcomes); i += 2 {
		w := outcomes[i].Wager
		next := freezeRequest(r)
		next.WagerID = w.WagerID
		next.TicketID = w.TicketID
		next.LegID = w.LegID
		next.OriginalOperationID = OriginalOperationID(p.EpochID, w.TicketID)
		next.FundingTxHash = w.FundingTxHash
		next.EntitlementID = EntitlementID(p.EpochID, w.MarketID, w.TicketID, w.LegID)
		next.OperationID = next.EntitlementID + ":return"
		next.Memo = ReturnMemo(p.EpochID, next.EntitlementID)
		next.AmountUWolo = outcomes[i].PayoutUWolo
		next.Nonce = hash([]any{"capacity-test", i})
		selectedFixtureMandate(p, &next)
		resign(t, &next)
		if _, e = j.Prepare(context.Background(), sealedFixture(p, next)); e != nil {
			if e.Error() != "epoch_journal_capacity_hold" {
				t.Fatal(e)
			}
			capacity = true
			break
		}
		if admitted == 0 {
			first = next
		}
		last = next
		admitted++
	}
	if !capacity || admitted == 0 {
		t.Fatal("capacity boundary not exercised", admitted)
	}
	if _, e = j.Lookup(first.OperationID, Fingerprint(first)); e != nil {
		t.Fatal("capacity hold damaged prior decisions", e)
	}
	if d, err := j.Quarantine(last.OperationID, Fingerprint(last)); err != nil || d.Status != UnknownNoReplay {
		t.Fatal("capacity consumed reserved uncertainty space", err)
	}
	if d, err := j.Lookup(first.OperationID, Fingerprint(first)); err != nil || d.Status != PreparedUnsigned {
		t.Fatal("capacity quarantine damaged another decision", err)
	}
	_ = j.db.View(func(tx *bolt.Tx) error {
		if tx.Bucket(records).Stats().KeyN != admitted || tx.Bucket(events).Stats().KeyN != admitted+1 || tx.Bucket(nonces).Stats().KeyN != admitted {
			t.Fatal("capacity rejection left partial mutations")
		}
		return nil
	})
}

func TestHDIEEE754RemainderOrderingIsPreserved(t *testing.T) {
	_, r := fixture(t)
	p := r.Plan
	p.Wagers = nil
	for i, amount := range []string{"2000000", "8000000", "2000000", "4000000"} {
		side := "left"
		if i == 3 {
			side = "right"
		}
		id := uint64(i + 1)
		p.Wagers = append(p.Wagers, Wager{id, 10, id, id, "owner", side, amount, fmt.Sprintf("%064X", id), 0})
	}
	out, err := PlanSettlement(p)
	if err != nil {
		t.Fatal(err)
	}
	// Exact HD Number arithmetic: 2/3 > (8/3 - 2), so both two-WOLO rows
	// receive the remainder before the eight-WOLO row despite the ideal tie.
	for i, want := range []string{"1000000", "2000000", "1000000", "4000000"} {
		if out[i].MatchedUWolo != want {
			t.Fatalf("HD remainder drift: %+v", out)
		}
	}
}
