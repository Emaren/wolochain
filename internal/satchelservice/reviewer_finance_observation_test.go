package satchelservice

import (
	"context"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	_ "github.com/lib/pq"
)

func TestReviewerOwnerLiabilitiesIncludeAllBucketsAndRejectOverflow(t *testing.T) {
	r := reviewerOwnerLedger{owners: "2", available: "88000000", reserved: "12000000", committed: "9000000", withdrawing: "3000000", revisions: "6", entries: "6"}
	if total, err := r.total(); err != nil || total != "112000000" {
		t.Fatalf("omitted encumbered liabilities: %s %v", total, err)
	}
	for _, name := range []string{"negative", "noncanonical", "overflow", "offset_owner_corruption", "wrong_vault", "missing"} {
		t.Run(name, func(t *testing.T) {
			bad := r
			switch name {
			case "negative":
				bad.available = "-1"
			case "noncanonical":
				bad.reserved = "012000000"
			case "overflow":
				bad.available = "9223372036854775807"
			case "offset_owner_corruption":
				bad.inconsistent = true
			case "wrong_vault":
				bad.wrongVault = true
			case "missing":
				bad.owners = ""
			}
			if _, err := bad.total(); !errors.Is(err, ReviewerFinanceLedgerMismatch) || !errors.Is(err, ErrReviewerHeld) {
				t.Fatalf("unsafe liability observation: %v", err)
			}
		})
	}
}

type counterfeitReviewerBank struct{ calls int }

func (b *counterfeitReviewerBank) ReadBankProof(context.Context, string, int64) (satchel.AuthenticatedBankEvidence, satchel.BankProof, error) {
	b.calls++
	var forged satchel.AuthenticatedBankEvidence
	// Even plausible serialized fields cannot mint the bank package's opaque
	// authenticated evidence. This is deliberately not a success test double.
	_ = json.Unmarshal([]byte(`{"height":9,"balance":"999999999999","address":"claimed-vault"}`), &forged)
	return forged, satchel.BankProof{}, nil
}

func TestReviewerFinanceRejectsForgedBankBeforeDatabaseRead(t *testing.T) {
	bank := &counterfeitReviewerBank{}
	s := &ReviewerFinanceSource{pg: &ReviewerReadOnlyPGSource{vault: testHTTPAddress(t, 101)}, bank: bank, now: time.Now}
	if _, err := s.ObserveFinance(context.Background(), 9); !errors.Is(err, ReviewerFinanceBankInvalid) {
		t.Fatalf("forged bank evidence passed: %v", err)
	}
	if bank.calls != 1 {
		t.Fatal("did not exercise bank verification boundary")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	for _, c := range []context.Context{nil, ctx} {
		if _, err := s.ObserveFinance(c, 9); !errors.Is(err, ReviewerFinanceUnavailable) {
			t.Fatalf("invalid context read: %v", err)
		}
	}
	if bank.calls != 1 {
		t.Fatal("canceled read reached source")
	}
}

func reviewerFinanceNativeBank(t *testing.T) (*satchel.TrustedReader, string, int64) {
	t.Helper()
	config, fixture := isolatedBackendConfig(t)
	chain := newNativeHTTPChainWithBalance(t, fixture.signer, 110000000)
	chain.commit(t, nil)
	chain.commit(t, nil)
	primary, witness := chain.serve(t, false), chain.serve(t, true)
	reader, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL}, satchel.TrustAnchor{
		Height: 1, Hash: hex.EncodeToString(chain.commits[1].Header.Hash()), PeriodSeconds: 3600,
		EvidenceReference: "isolated-reviewer-finance-sdk-test-validator-only",
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(reader.Close)
	return reader, config.Vault, chain.head - 1
}

// The probe retains the real reader's opaque evidence, never constructs it.
type reviewerFinanceBankProbe struct {
	reader reviewerBankReader
	bank   satchel.AuthenticatedBankEvidence
	after  func()
}

func (p *reviewerFinanceBankProbe) ReadBankProof(ctx context.Context, vault string, height int64) (satchel.AuthenticatedBankEvidence, satchel.BankProof, error) {
	bank, proof, err := p.reader.ReadBankProof(ctx, vault, height)
	p.bank = bank
	if p.after != nil {
		p.after()
	}
	return bank, proof, err
}

func TestReviewerFinanceChecksNativeBankAtQueryCompletion(t *testing.T) {
	reader, vault, height := reviewerFinanceNativeBank(t)
	for _, name := range []string{"fresh", "stale", "future", "canceled"} {
		t.Run(name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			probe := &reviewerFinanceBankProbe{reader: reader}
			if name == "canceled" {
				probe.after = cancel
			}
			var initial time.Time
			clock := func() time.Time {
				now := time.Now()
				if name == "stale" {
					now = now.Add(time.Minute)
				} else if name == "future" {
					now = now.Add(-time.Second)
				}
				if initial.IsZero() {
					initial = now
				}
				return now
			}
			// No database is configured: fresh genuine bank evidence must reach
			// the separate ledger boundary; bad clocks/cancellation must not.
			source := &ReviewerFinanceSource{pg: &ReviewerReadOnlyPGSource{vault: vault}, bank: probe, now: clock}
			_, err := source.ObserveFinance(ctx, height)
			if name == "fresh" {
				if !errors.Is(err, ReviewerFinanceUnavailable) || probe.bank.FreshAt(initial) || !probe.bank.FreshAt(time.Now()) {
					t.Fatalf("authentic bank query was not checked at completion: %v", err)
				}
			} else if !errors.Is(err, ReviewerFinanceBankInvalid) {
				t.Fatalf("invalid completion admitted to ledger boundary: %v", err)
			}
		})
	}
}

func TestReviewerFinanceCannotTurnPartialObservationIntoCompleteCensus(t *testing.T) {
	s := &ReviewerFinanceSource{}
	census, err := s.AuthenticatedFeeCensus(context.Background(), reviewerTestWager())
	if !errors.Is(err, ReviewerFinanceCoverageUnknown) || !errors.Is(err, ErrReviewerHeld) || census.PendingOperationsComplete {
		t.Fatal("unknown global coverage became approval")
	}
	var observation ReviewerFinanceObservation
	if observation.SpendingAuthorized() || observation.Bank().FreshAt(time.Now()) {
		t.Fatal("zero observation granted authority")
	}
	if _, err := observation.KnownOwnerLiabilitiesUWolo(); err == nil {
		t.Fatal("missing ledger became zero liabilities")
	}
	missing := observation.MissingCoverage()
	if len(missing) != 4 {
		t.Fatal("forgot historical/external/unknown fee coverage")
	}
	missing[0] = "complete"
	if observation.MissingCoverage()[0] == "complete" {
		t.Fatal("caller rewrote missing coverage")
	}
	if _, err := NewReviewerFinanceSource(nil, nil, nil); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("unconfigured finance source accepted")
	}
}

// Run only against the explicitly named disposable local CI database, never
// an application connection. It exercises actual PostgreSQL roles, column
// grants, NUMERIC arithmetic, READ ONLY transactions and per-owner SQL joins.
func TestReviewerFinancePostgresIndependentReadOnlyLedger(t *testing.T) {
	dsn := os.Getenv("SATCHEL_REVIEWER_TEST_PG_DSN")
	if dsn == "" {
		t.Skip("isolated PostgreSQL fixture not configured")
	}
	u, err := url.Parse(dsn)
	if err != nil || (u.Hostname() != "127.0.0.1" && u.Hostname() != "localhost") || u.Path != "/satchel_reviewer_test" {
		t.Fatal("fixture requires disposable localhost /satchel_reviewer_test database")
	}
	admin, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = admin.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	fixture := `
CREATE ROLE satchel_reviewer_finance_it LOGIN PASSWORD 'isolated-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.war_satchel_funded_balances(owner_user_id integer PRIMARY KEY, available_uwolo bigint NOT NULL, reserved_uwolo bigint NOT NULL, committed_uwolo bigint NOT NULL, withdrawal_pending_uwolo bigint NOT NULL, version bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_journal(owner_user_id integer NOT NULL,delta_available_uwolo bigint NOT NULL,delta_reserved_uwolo bigint NOT NULL,delta_committed_uwolo bigint NOT NULL,delta_withdrawal_pending_uwolo bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_receipts(vault_address text NOT NULL,chain_id text NOT NULL,canonical_height bigint NOT NULL,amount_uwolo bigint NOT NULL);
GRANT SELECT ON ALL TABLES IN SCHEMA public TO satchel_reviewer_finance_it;
INSERT INTO public.war_satchel_funded_balances VALUES(1,88000000,12000000,9000000,3000000,3),(2,5000000,0,0,0,1);
INSERT INTO public.war_satchel_funded_journal VALUES(1,112000000,0,0,0),(1,-12000000,12000000,0,0),(1,-9000000,0,9000000,0),(1,-3000000,0,0,3000000),(2,5000000,0,0,0);
`
	if _, err = admin.ExecContext(ctx, fixture); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(`DROP TABLE public.war_satchel_funded_receipts,public.war_satchel_funded_journal,public.war_satchel_funded_balances; DROP ROLE satchel_reviewer_finance_it`)
	})
	u.User = url.UserPassword("satchel_reviewer_finance_it", "isolated-test-only")
	db, err := sql.Open("postgres", u.String())
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	bank, vault, height := reviewerFinanceNativeBank(t)
	s, err := NewReviewerReadOnlyPGSource(db, "satchel_reviewer_finance_it", "2500", vault, testHTTPAddress(t, 102))
	if err != nil {
		t.Fatal(err)
	}
	read := func(want string) {
		t.Helper()
		row, e := s.readOwnerLedger(ctx)
		if e != nil {
			t.Fatal(e)
		}
		total, e := row.total()
		if e != nil || total != want {
			t.Fatalf("actual PG total=%s error=%v want=%s", total, e, want)
		}
	}
	read("117000000")
	finance := &ReviewerFinanceSource{pg: s, bank: bank, now: time.Now}
	observation, err := finance.ObserveFinance(ctx, height)
	if err != nil || !observation.FreshAt(time.Now()) || observation.Bank().CommitHeight() != height+1 || observation.Bank().BalanceUWolo() != "110000000" {
		t.Fatalf("actual SDK bank and PostgreSQL observation failed: %v", err)
	}
	if total, err := observation.KnownOwnerLiabilitiesUWolo(); err != nil || total != "117000000" || observation.SpendingAuthorized() {
		t.Fatalf("partial observation changed ledger or spending authority: %s %v", total, err)
	}
	clockCalls := 0
	finance.now = func() time.Time {
		clockCalls++
		if clockCalls > 1 {
			return time.Now().Add(-time.Hour)
		}
		return time.Now()
	}
	if _, err := finance.ObserveFinance(ctx, height); err != nil {
		t.Fatalf("clock rollback lost the monotonic completion floor: %v", err)
	}
	// A bank observation can expire while the independent ledger is read.
	clockCalls = 0
	finance.now = func() time.Time {
		clockCalls++
		if clockCalls >= 3 {
			return time.Now().Add(time.Minute)
		}
		return time.Now()
	}
	if _, err := finance.ObserveFinance(ctx, height); !errors.Is(err, ReviewerFinanceStale) {
		t.Fatalf("bank expiry during ledger read accepted: %v", err)
	}
	finance.now = time.Now
	s.now = func() time.Time { return time.Now().Add(time.Second) }
	if _, err := finance.ObserveFinance(ctx, height); !errors.Is(err, ReviewerFinanceStale) {
		t.Fatalf("future ledger timestamp accepted: %v", err)
	}
	s.now = time.Now
	canceled, cancelObservation := context.WithCancel(ctx)
	s.now = func() time.Time { cancelObservation(); return time.Now() }
	if _, err := finance.ObserveFinance(canceled, height); !errors.Is(err, ReviewerFinanceStale) {
		t.Fatalf("cancellation after ledger read accepted: %v", err)
	}
	cancelObservation()
	s.now = time.Now
	if _, err = admin.ExecContext(ctx, `GRANT CREATE ON SCHEMA public TO satchel_reviewer_finance_it`); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceRoleDenied) {
		t.Fatalf("DDL-capable reviewer accepted: %v", err)
	}
	if _, err = admin.ExecContext(ctx, `REVOKE CREATE ON SCHEMA public FROM satchel_reviewer_finance_it`); err != nil {
		t.Fatal(err)
	}
	read("117000000")
	// A SELECT-only RLS principal can otherwise see a reconciled subset (or
	// zero rows) and silently omit a customer's obligations.
	if _, err = admin.ExecContext(ctx, `ALTER TABLE public.war_satchel_funded_balances ENABLE ROW LEVEL SECURITY; ALTER TABLE public.war_satchel_funded_journal ENABLE ROW LEVEL SECURITY`); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceRoleDenied) {
		t.Fatalf("RLS-hidden liabilities accepted: %v", err)
	}
	if _, err = admin.ExecContext(ctx, `ALTER TABLE public.war_satchel_funded_balances DISABLE ROW LEVEL SECURITY; ALTER TABLE public.war_satchel_funded_journal DISABLE ROW LEVEL SECURITY`); err != nil {
		t.Fatal(err)
	}
	read("117000000")
	// Same global sum, wrong owners: an aggregate-only reconciliation misses it.
	if _, err = admin.ExecContext(ctx, `UPDATE public.war_satchel_funded_balances SET available_uwolo=available_uwolo+CASE owner_user_id WHEN 1 THEN 1 ELSE -1 END`); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceLedgerMismatch) {
		t.Fatalf("offsetting owner corruption accepted: %v", err)
	}
	if _, err = admin.ExecContext(ctx, `UPDATE public.war_satchel_funded_balances SET available_uwolo=available_uwolo+CASE owner_user_id WHEN 1 THEN -1 ELSE 1 END`); err != nil {
		t.Fatal(err)
	}
	read("117000000")
	if _, err = admin.ExecContext(ctx, `GRANT UPDATE(available_uwolo) ON public.war_satchel_funded_balances TO satchel_reviewer_finance_it`); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceRoleDenied) {
		t.Fatalf("column-writable reviewer accepted: %v", err)
	}
	if _, err = admin.ExecContext(ctx, `REVOKE UPDATE(available_uwolo) ON public.war_satchel_funded_balances FROM satchel_reviewer_finance_it`); err != nil {
		t.Fatal(err)
	}
	read("117000000")
	if _, err = admin.ExecContext(ctx, `INSERT INTO public.war_satchel_funded_journal VALUES(3,1,0,0,0)`); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceLedgerMismatch) {
		t.Fatalf("orphan owner obligation omitted: %v", err)
	}
	if _, err = admin.ExecContext(ctx, `DELETE FROM public.war_satchel_funded_journal WHERE owner_user_id=3`); err != nil {
		t.Fatal(err)
	}
	if _, err = admin.ExecContext(ctx, `INSERT INTO public.war_satchel_funded_receipts VALUES($1,'wolo-1',9,1000000)`, testHTTPAddress(t, 103)); err != nil {
		t.Fatal(err)
	}
	if _, err = s.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceLedgerMismatch) {
		t.Fatalf("other-vault liabilities trusted: %v", err)
	}
	// A privileged connection cannot hide behind SET ROLE.
	privileged := *s
	privileged.db = admin
	if _, err = privileged.readOwnerLedger(ctx); !errors.Is(err, ReviewerFinanceRoleDenied) {
		t.Fatalf("operator login accepted as independent reviewer: %v", err)
	}
}

func TestReviewerFinanceQueryUsesExactReadonlyContract(t *testing.T) {
	for _, fragment := range []string{"FULL JOIN journal", "GROUP BY owner_user_id", "sum(delta_available_uwolo::numeric)", "vault_address <> $1", "committed_uwolo::numeric"} {
		if !strings.Contains(reviewerPGFinanceQuery, fragment) {
			t.Fatalf("lost query bound %s", fragment)
		}
	}
}
