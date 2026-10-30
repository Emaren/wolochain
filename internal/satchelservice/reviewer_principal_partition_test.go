package satchelservice

// The HD rows below are explicitly synthetic, disposable ledger fixtures.
// Actual custody snapshots use SDK/Comet execution and real TEST signatures;
// neither fixture establishes production financial or owner-spend coverage.
import (
	"context"
	"crypto/ed25519"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"
)

func principalTestWager(t *testing.T, f *custodyAuthorityFixture, execution int64, available, reserved, version, journal string) (reviewerPrincipalWager, WagerReservation) {
	t.Helper()
	raw, _ := sampleHDOrigin(t)
	parsed, err := reviewerStrictJSON(raw)
	if err != nil {
		t.Fatal(err)
	}
	m := parsed.(map[string]any)
	n := strconv.FormatInt(execution, 10)
	m["executionId"], m["ticketId"], m["ownerUid"] = execution, execution, f.request.OwnerID
	m["operationId"], m["reservationId"] = "satchel:ticket:"+n, "satchel:reserve:"+n
	m["vault"], m["recipient"], m["amountUwolo"] = f.config.Vault, f.config.BettingEscrow, "7000000"
	m["memo"] = "AoE2HDBets bet ticket v1 · ticket " + n
	m["availableUwolo"], m["reservedUwolo"], m["ledgerVersion"], m["journalId"] = available, reserved, version, journal
	m["legs"].([]any)[0].(map[string]any)["amountWolo"] = int64(7)
	consent, err := reviewerCanonicalHash([]any{"aoe2war/satchel/hd-wager-consent/v1", m["consentId"], m["challengeText"], m["ownerSignatureJson"]})
	if err != nil {
		t.Fatal(err)
	}
	ledger, err := reviewerCanonicalHash([]any{"aoe2war/satchel/hd-wager-ledger/v1", int64(77), version, available, reserved, journal})
	if err != nil {
		t.Fatal(err)
	}
	reservation, err := reviewerCanonicalHash([]any{"aoe2war/satchel/hd-wager-reservation/v1", m, consent, ledger})
	if err != nil {
		t.Fatal(err)
	}
	raw, err = json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	w := reviewerPrincipalWager{ID: "satchel:reserve:" + n, Owner: "77", Execution: n, Amount: "7000000", Status: "reserved", Operation: "satchel:ticket:" + n,
		AuthOwner: "77", AuthOperation: "satchel:ticket:" + n, Snapshot: string(raw), ReservationDigest: reservation, LedgerRevision: ledger, ConsentDigest: consent}
	p := WagerReservation{Version: 1, OperationID: w.Operation, OwnerID: f.request.OwnerID, Vault: f.config.Vault, Recipient: f.config.BettingEscrow,
		AmountUWolo: w.Amount, Memo: m["memo"].(string), ReservationDigest: reservation, LedgerRevision: ledger, ConsentDigest: consent, FeeUWolo: f.config.FeesUWolo}
	return w, p
}

func principalTestRows(t *testing.T, f *custodyAuthorityFixture) (reviewerPrincipalRows, WagerReservation) {
	t.Helper()
	w, p := principalTestWager(t, f, 7, "93000000", "7000000", "2", "2")
	r := reviewerPrincipalRows{Owner: "77", UID: p.OwnerID, Wallet: testHTTPAddress(t, 100), Available: "93000000", Reserved: "7000000", Committed: "0", Withdrawing: "0", Version: "2", Wagers: []reviewerPrincipalWager{w},
		Journal: []reviewerPrincipalJournalRow{
			{ID: "1", Source: "satchel:credit:wolo-1:" + strings.Repeat("A", 64) + ":0", Event: "deposit_credit", Amount: "100000000", Available: "100000000", Reserved: "0", Committed: "0", Withdrawing: "0", Receipt: "1"},
			{ID: "2", Source: w.ID, Event: "wager_reserve", Amount: w.Amount, Available: "-" + w.Amount, Reserved: w.Amount, Committed: "0", Withdrawing: "0", Execution: w.Execution},
		}}
	principalTestGlobal(&r)
	return r, p
}
func principalTestGlobal(r *reviewerPrincipalRows) {
	r.Global = reviewerOwnerLedger{owners: "1", available: r.Available, reserved: r.Reserved, committed: r.Committed, withdrawing: r.Withdrawing, revisions: r.Version, entries: strconv.Itoa(len(r.Journal))}
}
func principalTestCopy(t *testing.T, r reviewerPrincipalRows) reviewerPrincipalRows {
	t.Helper()
	raw, err := json.Marshal(r)
	if err != nil {
		t.Fatal(err)
	}
	var out reviewerPrincipalRows
	if json.Unmarshal(raw, &out) != nil {
		t.Fatal("copy failed")
	}
	out.Global = r.Global
	return out
}

func TestReviewerPrincipalPartitionActualSDKSnapshotDoesNotAuthorizeOrMutate(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	r, p := principalTestRows(t, f)
	before := readTestCustodyJournal(t, f.engine)
	j, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	got, err := verifyReviewerPrincipalRows(r, p, j, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	amount, err := got.PrincipalUWolo()
	if err != nil || amount != "7000000" || got.SpendingAuthorized() || !got.FreshAt(time.Now()) || got.FreshAt(time.Now().Add(3*time.Second)) ||
		got.CustodyJournalSHA256() != before.JournalDigest || got.ProposedFingerprint() != reviewerFingerprint(p) || !validReserveDigest(got.PartitionSHA256()) {
		t.Fatal("incorrect non-authorizing evidence", got, err)
	}
	if after := readTestCustodyJournal(t, f.engine); !reflect.DeepEqual(before, after) || f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("partition read executed or mutated custody")
	}
	var decoded VerifiedReviewerPrincipalPartition
	if json.Unmarshal([]byte(`{"valid":true,"principal":"7000000"}`), &decoded) != nil {
		t.Fatal("decode")
	}
	if _, err := decoded.PrincipalUWolo(); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("caller JSON minted opaque evidence")
	}
}

func TestReviewerPrincipalPartitionRejectsAllocationAndJournalSubstitution(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	base, p := principalTestRows(t, f)
	j, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"other_owner", "uid", "wallet", "held_amount", "missing_hold", "duplicate_hold", "unknown_current", "released_current", "wrong_auth_operation", "missing_authorization", "auth_owner", "journal_id", "journal_owner_totals", "orphan_journal", "missing_reserve_debit", "same_total_different_slice", "historical_committed", "withdraw_unpartitioned", "negative_delta", "overflow", "duplicate_source", "global_corrupt", "recorded_current", "missing_native_hold", "zero_snapshot"} {
		t.Run(name, func(t *testing.T) {
			r := principalTestCopy(t, base)
			native := j
			switch name {
			case "other_owner":
				r.Owner = "78"
			case "uid":
				r.UID = "other-owner"
			case "wallet":
				r.Wallet = testHTTPAddress(t, 105)
			case "held_amount":
				r.Wagers[0].Amount = "6000000"
			case "missing_hold":
				r.Wagers = nil
			case "duplicate_hold":
				r.Wagers = append(r.Wagers, r.Wagers[0])
			case "unknown_current":
				r.Wagers[0].Status = "unknown_hold"
			case "released_current":
				r.Wagers[0].Status = "released"
			case "wrong_auth_operation":
				r.Wagers[0].AuthOperation = "satchel:ticket:8"
			case "missing_authorization":
				r.Wagers[0].AuthOwner = ""
			case "auth_owner":
				r.Wagers[0].AuthOwner = "78"
			case "journal_id":
				r.Journal[1].ID = "3"
			case "journal_owner_totals":
				r.Available = "94000000"
			case "orphan_journal":
				r.Journal = append(r.Journal, reviewerPrincipalJournalRow{ID: "3", Source: "satchel:reserve:99", Event: "wager_reserve", Amount: "1", Available: "-1", Reserved: "1", Committed: "0", Withdrawing: "0", Execution: "99"})
			case "missing_reserve_debit":
				r.Journal = r.Journal[:1]
			case "same_total_different_slice":
				r.Wagers[0].ID = "satchel:reserve:8"
				r.Wagers[0].Operation = "satchel:ticket:8"
				r.Wagers[0].Execution = "8"
			case "historical_committed":
				r.Committed = "1"
			case "withdraw_unpartitioned":
				r.Withdrawing = "1"
			case "negative_delta":
				r.Journal[1].Available = "-0"
			case "overflow":
				r.Available = "9223372036854775808"
			case "duplicate_source":
				r.Journal = append(r.Journal, r.Journal[0])
				r.Journal[2].ID = "3"
			case "global_corrupt":
				r.Global.inconsistent = true
			case "recorded_current":
				native.effects = map[string]reviewerPrincipalEffect{p.OperationID: {Owner: p.OwnerID, Status: "REFUSED"}}
			case "missing_native_hold":
				native.effects = map[string]reviewerPrincipalEffect{"satchel:ticket:99": {Owner: p.OwnerID, Status: "CONFIRMED"}}
			case "zero_snapshot":
				native = ReviewerPrincipalJournalSnapshot{}
			}
			if _, err := verifyReviewerPrincipalRows(r, p, native, time.Now()); !errors.Is(err, ErrReviewerHeld) {
				t.Fatalf("%s accepted: %v", name, err)
			}
		})
	}
}

func principalTestWithdrawal(t *testing.T, r *reviewerPrincipalRows, vault string) {
	t.Helper()
	request := engineTestWithdrawal(t) // Real disposable secp256k1 owner signature, historical consent.
	m := *request.OwnerMandate
	if request.OwnerID != r.UID {
		t.Fatal("fixture owner mismatch")
	}
	id := request.Approval.WithdrawalID
	reservation := hashJSON([]any{"aoe2war/satchel/hd-reservation/v1", id, int64(77), r.UID, request.Recipient, vault, request.AmountUWolo, request.Memo, "satchel:withdraw:reserve:" + id, OwnerMandateDigest(m)})
	raw, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	r.Withdrawals = []reviewerPrincipalWithdrawal{{ID: id, Owner: r.Owner, Wallet: request.Recipient, Amount: request.AmountUWolo, Status: "reserved", Challenge: m.Challenge.ID,
		AuthOwner: r.Owner, UID: r.UID, AuthWallet: request.Recipient, Vault: vault, AuthAmount: request.AmountUWolo, AuthChallenge: m.Challenge.ID, Mandate: string(raw), MandateDigest: OwnerMandateDigest(m), ReservationDigest: reservation, Memo: request.Memo}}
	r.Available, r.Withdrawing, r.Version = "92000000", "1000000", "3"
	r.Journal = append(r.Journal, reviewerPrincipalJournalRow{ID: "3", Source: "satchel:withdraw:reserve:" + id, Event: "withdraw_reserve", Amount: "1000000", Available: "-1000000", Reserved: "0", Committed: "0", Withdrawing: "1000000"})
	principalTestGlobal(r)
}

func TestReviewerPrincipalPartitionIncludesFullWithdrawalAndOtherWagerHolds(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	r, p := principalTestRows(t, f)
	principalTestWithdrawal(t, &r, p.Vault)
	j, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := verifyReviewerPrincipalRows(r, p, j, time.Now()); err != nil {
		t.Fatal("genuine historical owner withdrawal hold lost", err)
	}
	for _, name := range []string{"missing", "signature", "owner", "amount", "challenge", "no_native_sent", "missing_journal", "reserved_total"} {
		t.Run(name, func(t *testing.T) {
			changed := principalTestCopy(t, r)
			switch name {
			case "missing":
				changed.Withdrawals = nil
			case "signature":
				changed.Withdrawals[0].Mandate = strings.Replace(changed.Withdrawals[0].Mandate, `"signature":"`, `"signature":"A`, 1)
			case "owner":
				changed.Withdrawals[0].AuthOwner = "78"
			case "amount":
				changed.Withdrawals[0].Amount = "999999"
			case "challenge":
				changed.Withdrawals[0].Challenge = "12345678-1234-4123-8123-123456789abe"
			case "no_native_sent":
				changed.Withdrawals[0].Status = "sent"
				changed.Withdrawals[0].TxHash = strings.Repeat("B", 64)
				changed.Withdrawals[0].Height = "5"
			case "missing_journal":
				changed.Journal = changed.Journal[:2]
			case "reserved_total":
				changed.Reserved = "8000000"
			}
			if _, err := verifyReviewerPrincipalRows(changed, p, j, time.Now()); !errors.Is(err, ErrReviewerHeld) {
				t.Fatal("unpartitioned withdrawal accepted", name, err)
			}
		})
	}
}

func TestReviewerPrincipalPartitionActualSDKConfirmedOutflowMustBePosted(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	r, p := principalTestRows(t, f)
	grant := p
	grant.IssuedAt, grant.ExpiresAt = time.Now().Unix()-1, time.Now().Unix()+120
	grant.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(grant)))
	request := f.request
	request.Reservation = &grant
	f.chain.release()
	result, err := f.engine.Submit(t.Context(), request)
	if err != nil || result.Status != "ACCEPTED" {
		t.Fatal(result, err)
	}
	if _, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("actual global unresolved fence omitted", err)
	}
	confirmed, err := f.engine.Reconcile(t.Context(), request.OperationID)
	if err != nil || confirmed.Status != "CONFIRMED" {
		t.Fatal(confirmed, err)
	}
	j, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	next, np := principalTestWager(t, f, 8, "86000000", "14000000", "3", "3")
	r.Wagers[0].Status = "unknown_hold"
	r.Wagers = append(r.Wagers, next)
	r.Available, r.Reserved, r.Version = "86000000", "14000000", "3"
	r.Journal = append(r.Journal, reviewerPrincipalJournalRow{ID: "3", Source: next.ID, Event: "wager_reserve", Amount: next.Amount, Available: "-" + next.Amount, Reserved: next.Amount, Committed: "0", Withdrawing: "0", Execution: next.Execution})
	principalTestGlobal(&r)
	if _, err := verifyReviewerPrincipalRows(r, np, j, time.Now()); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("confirmed but unposted real SDK outflow was netted away", err)
	}
	r.Wagers[0].Status, r.Wagers[0].Ticket, r.Wagers[0].TxHash = "committed", "7", confirmed.TxHash
	r.Reserved, r.Committed, r.Version = "7000000", "7000000", "4"
	r.Journal = append(r.Journal, reviewerPrincipalJournalRow{ID: "4", Source: "satchel:commit:" + r.Wagers[0].ID, Event: "wager_commit", Amount: p.AmountUWolo, Available: "0", Reserved: "-" + p.AmountUWolo, Committed: p.AmountUWolo, Withdrawing: "0", Execution: "7"})
	principalTestGlobal(&r)
	got, err := verifyReviewerPrincipalRows(r, np, j, time.Now())
	if err != nil {
		t.Fatal("exact posted historical principal rejected", err)
	}
	if got.principal != np.AmountUWolo || got.SpendingAuthorized() || f.SDKSigns.Load() != 1 || f.chain.broadcasts != 1 {
		t.Fatal("read spent or minted financial coverage")
	}
	r.Wagers[0].TxHash = strings.Repeat("B", 64)
	if _, err := verifyReviewerPrincipalRows(r, np, j, time.Now()); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("wrong confirmed native hash accepted")
	}
	// Restart/expiry never removes the actual journaled outflow identity.
	path := f.config.StatePath
	policy := f.engine.policy
	if err := f.engine.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(path, policy, f.native)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	reopened.now = func() time.Time { return time.Now().Add(time.Hour) }
	old, err := reopened.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil || old.effects[p.OperationID].Status != "CONFIRMED" || old.effects[p.OperationID].OriginalFingerprint != reviewerFingerprint(p) {
		t.Fatal("expiry/restart lost historical principal", err)
	}
}

type principalChangingReader struct {
	engine *Engine
	after  func(int, *ReviewerPrincipalJournalSnapshot)
	reads  int
}

func (r *principalChangingReader) ReadReviewerPrincipalJournal(ctx context.Context, owner string) (ReviewerPrincipalJournalSnapshot, error) {
	j, err := r.engine.ReadReviewerPrincipalJournal(ctx, owner)
	r.reads++
	if r.after != nil {
		r.after(r.reads, &j)
	}
	return j, err
}

func TestReviewerFinancePostgresPrincipalPartitionRequiresActualReadonlyOwnerSlice(t *testing.T) {
	dsn := os.Getenv("SATCHEL_REVIEWER_TEST_PG_DSN")
	if dsn == "" {
		t.Skip("isolated PostgreSQL fixture not configured")
	}
	u, err := url.Parse(dsn)
	if err != nil || (u.Hostname() != "127.0.0.1" && u.Hostname() != "localhost") || u.Path != "/satchel_reviewer_test" {
		t.Fatal("explicit disposable localhost /satchel_reviewer_test required")
	}
	admin, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()
	const role = "satchel_reviewer_principal_it"
	ddl := `CREATE ROLE satchel_reviewer_principal_it LOGIN PASSWORD 'isolated-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id integer PRIMARY KEY,uid text UNIQUE NOT NULL,wallet_address text);
CREATE TABLE public.war_satchel_funded_balances(owner_user_id integer PRIMARY KEY,available_uwolo bigint NOT NULL,reserved_uwolo bigint NOT NULL,committed_uwolo bigint NOT NULL,withdrawal_pending_uwolo bigint NOT NULL,version bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_journal(id bigint PRIMARY KEY,owner_user_id integer NOT NULL,source_key text UNIQUE NOT NULL,event_kind text NOT NULL,amount_uwolo bigint NOT NULL,delta_available_uwolo bigint NOT NULL,delta_reserved_uwolo bigint NOT NULL,delta_committed_uwolo bigint NOT NULL,delta_withdrawal_pending_uwolo bigint NOT NULL,execution_id integer,receipt_id bigint,claim_return_id bigint);
CREATE TABLE public.war_satchel_funded_receipts(vault_address text NOT NULL,chain_id text NOT NULL,canonical_height bigint NOT NULL,amount_uwolo bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_reservations(id text PRIMARY KEY,owner_user_id integer NOT NULL,execution_id integer UNIQUE NOT NULL,amount_uwolo bigint NOT NULL,status text NOT NULL,ticket_request_id text UNIQUE NOT NULL,ticket_id integer,tx_hash text);
CREATE TABLE public.war_satchel_wager_authorizations(operation_id text PRIMARY KEY,reservation_id text UNIQUE NOT NULL,owner_user_id integer NOT NULL,snapshot_json jsonb NOT NULL,reservation_digest text NOT NULL,ledger_revision text NOT NULL,consent_digest text NOT NULL);
CREATE TABLE public.war_satchel_funded_withdrawals(id uuid PRIMARY KEY,owner_user_id integer NOT NULL,owner_wallet_address text NOT NULL,amount_uwolo bigint NOT NULL,status text NOT NULL,tx_hash text,confirmed_height bigint,authorizing_challenge_id uuid NOT NULL);
CREATE TABLE public.war_satchel_withdrawal_authorizations(withdrawal_id uuid PRIMARY KEY,owner_user_id integer NOT NULL,owner_uid text NOT NULL,wallet_address text NOT NULL,vault_address text NOT NULL,amount_uwolo bigint NOT NULL,challenge_id uuid NOT NULL,owner_mandate_json jsonb NOT NULL,owner_mandate_digest text NOT NULL,reservation_digest text NOT NULL,memo text NOT NULL);
GRANT SELECT ON public.users,public.war_satchel_funded_balances,public.war_satchel_funded_journal,public.war_satchel_funded_receipts,public.war_satchel_funded_reservations,public.war_satchel_wager_authorizations,public.war_satchel_funded_withdrawals,public.war_satchel_withdrawal_authorizations TO satchel_reviewer_principal_it;`
	if _, err := admin.ExecContext(t.Context(), ddl); err != nil {
		t.Fatal(err)
	}
	defer func() {
		_, _ = admin.Exec(`DROP TABLE public.war_satchel_withdrawal_authorizations,public.war_satchel_funded_withdrawals,public.war_satchel_wager_authorizations,public.war_satchel_funded_reservations,public.war_satchel_funded_receipts,public.war_satchel_funded_journal,public.war_satchel_funded_balances,public.users;DROP ROLE satchel_reviewer_principal_it`)
	}()
	f := newCustodyAuthorityFixture(t)
	rows, p := principalTestRows(t, f)
	w := rows.Wagers[0]
	exec := func(query string, args ...any) {
		t.Helper()
		if _, err := admin.ExecContext(t.Context(), query, args...); err != nil {
			t.Fatal(err)
		}
	}
	exec(`INSERT INTO public.users VALUES(77,$1,$2)`, p.OwnerID, rows.Wallet)
	exec(`INSERT INTO public.war_satchel_funded_balances VALUES(77,93000000,7000000,0,0,2)`)
	exec(`INSERT INTO public.war_satchel_funded_journal VALUES(1,77,$1,'deposit_credit',100000000,100000000,0,0,0,NULL,1,NULL),(2,77,$2,'wager_reserve',7000000,-7000000,7000000,0,0,7,NULL,NULL)`, rows.Journal[0].Source, w.ID)
	exec(`INSERT INTO public.war_satchel_funded_reservations VALUES($1,77,7,7000000,'reserved',$2,NULL,NULL)`, w.ID, w.Operation)
	exec(`INSERT INTO public.war_satchel_wager_authorizations VALUES($1,$2,77,$3::jsonb,$4,$5,$6)`, w.Operation, w.ID, w.Snapshot, w.ReservationDigest, w.LedgerRevision, w.ConsentDigest)
	u.User = url.UserPassword(role, "isolated-test-only")
	db, err := sql.Open("postgres", u.String())
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	for _, name := range []string{"positive", "canary_policy", "admin_role", "column_write", "rls", "wrong_owner", "unknown_current", "journal_changed", "missing_hold", "wrong_policy", "wrong_key", "missing_snapshot", "source_owner", "source_vault", "stale_snapshot", "future_snapshot", "snapshot_change", "ledger_changed_during_io", "cancelled"} {
		t.Run(name, func(t *testing.T) {
			connection := db
			policy := f.engine.policy
			proposal := p
			reader := &principalChangingReader{engine: f.engine}
			cleanup := func() {}
			switch name {
			case "admin_role":
				connection = admin
			case "column_write":
				exec(`GRANT UPDATE(amount_uwolo) ON public.war_satchel_funded_reservations TO satchel_reviewer_principal_it`)
				cleanup = func() {
					exec(`REVOKE UPDATE(amount_uwolo) ON public.war_satchel_funded_reservations FROM satchel_reviewer_principal_it`)
				}
			case "rls":
				exec(`ALTER TABLE public.war_satchel_funded_reservations ENABLE ROW LEVEL SECURITY`)
				cleanup = func() { exec(`ALTER TABLE public.war_satchel_funded_reservations DISABLE ROW LEVEL SECURITY`) }
			case "wrong_owner":
				proposal.OwnerID = "different-owner"
			case "unknown_current":
				exec(`UPDATE public.war_satchel_funded_reservations SET status='unknown_hold'`)
				cleanup = func() { exec(`UPDATE public.war_satchel_funded_reservations SET status='reserved'`) }
			case "journal_changed":
				exec(`UPDATE public.war_satchel_funded_journal SET delta_reserved_uwolo=6000000 WHERE id=2`)
				cleanup = func() { exec(`UPDATE public.war_satchel_funded_journal SET delta_reserved_uwolo=7000000 WHERE id=2`) }
			case "missing_hold":
				exec(`DELETE FROM public.war_satchel_funded_reservations`)
				cleanup = func() {
					exec(`INSERT INTO public.war_satchel_funded_reservations VALUES($1,77,7,7000000,'reserved',$2,NULL,NULL)`, w.ID, w.Operation)
				}
			case "wrong_policy":
				policy.MaxAmountUWolo--
			case "wrong_key":
				policy.WagerApprovalKey = ed25519.NewKeyFromSeed([]byte(strings.Repeat("z", 32))).Public().(ed25519.PublicKey)
			case "missing_snapshot":
				reader.after = func(_ int, j *ReviewerPrincipalJournalSnapshot) { *j = ReviewerPrincipalJournalSnapshot{} }
			case "source_owner":
				reader.after = func(_ int, j *ReviewerPrincipalJournalSnapshot) { j.owner = "another-owner" }
			case "source_vault":
				reader.after = func(_ int, j *ReviewerPrincipalJournalSnapshot) { j.vault = f.config.BettingEscrow }
			case "stale_snapshot":
				reader.after = func(_ int, j *ReviewerPrincipalJournalSnapshot) { j.observed = time.Now().Add(-3 * time.Second) }
			case "future_snapshot":
				reader.after = func(_ int, j *ReviewerPrincipalJournalSnapshot) { j.observed = time.Now().Add(time.Second) }
			case "snapshot_change":
				reader.after = func(n int, j *ReviewerPrincipalJournalSnapshot) {
					if n == 2 {
						j.digest = strings.Repeat("d", 64)
					}
				}
			case "ledger_changed_during_io":
				reader.after = func(n int, _ *ReviewerPrincipalJournalSnapshot) {
					if n == 2 {
						exec(`UPDATE public.war_satchel_funded_balances SET available_uwolo=94000000;UPDATE public.war_satchel_funded_journal SET amount_uwolo=101000000,delta_available_uwolo=101000000 WHERE id=1`)
					}
				}
				cleanup = func() {
					exec(`UPDATE public.war_satchel_funded_balances SET available_uwolo=93000000;UPDATE public.war_satchel_funded_journal SET amount_uwolo=100000000,delta_available_uwolo=100000000 WHERE id=1`)
				}
			}
			defer cleanup()
			pg, err := NewReviewerReadOnlyPGSource(connection, role, f.config.FeesUWolo, f.config.Vault, f.config.BettingEscrow)
			if err != nil {
				t.Fatal(err)
			}
			source, err := NewReviewerPrincipalPartitionSource(pg, reader, policy)
			if name == "canary_policy" {
				// The canary issuer's ceiling is independently enforced by its
				// own approval policy; this source pins the actual custody root.
				policy.MaxAmountUWolo = 1000000
				source, err = NewReviewerPrincipalPartitionSourceWithPolicyDigest(pg, reader, hashJSON(f.engine.policy))
				if err == nil && source.policy == hashJSON(policy) {
					t.Fatal("canary policy replaced the enrolled custody root")
				}
			}
			if err != nil {
				t.Fatal(err)
			}
			ctx := t.Context()
			if name == "cancelled" {
				c, cancel := context.WithCancel(ctx)
				cancel()
				ctx = c
			}
			got, err := source.ReadWagerPrincipalPartition(ctx, proposal)
			if name == "positive" || name == "canary_policy" {
				if err != nil || !got.FreshAt(time.Now()) || got.SpendingAuthorized() {
					t.Fatal("actual read-only PG partition rejected", got, err)
				}
			} else if !errors.Is(err, ErrReviewerHeld) {
				t.Fatal("untrusted PG/native partition accepted", name, err)
			}
		})
	}
	if f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("SQL evidence read caused execution")
	}
}
