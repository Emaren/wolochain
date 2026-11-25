package satchelservice

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

type principalBindingTestReader struct {
	inner  ReviewerPrincipalPartitionReader
	reads  int
	before func(int) error
}

func (r *principalBindingTestReader) ReadWagerPrincipalPartition(ctx context.Context, p WagerReservation) (VerifiedReviewerPrincipalPartition, error) {
	r.reads++
	if r.before != nil {
		if err := r.before(r.reads); err != nil {
			return VerifiedReviewerPrincipalPartition{}, err
		}
	}
	return r.inner.ReadWagerPrincipalPartition(ctx, p)
}

func TestReviewerPrincipalBindingActualNativeRootAndExactOriginalRequired(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	rows, p := principalTestRows(t, f)
	journal, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	// Controlled HD rows here test the pure binding contract. Actual PG access
	// and protected-role admission are exercised by the optional test below.
	partition, err := verifyReviewerPrincipalRows(rows, p, journal, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	binding, err := PrepareReviewerPrincipalSpendBinding(partition, p, time.Now())
	if err != nil || binding.SpendingAuthorized() || binding.PrincipalUWolo != p.AmountUWolo {
		t.Fatal(binding, err)
	}
	for _, name := range []string{"operation", "owner", "principal", "fee", "reservation", "ledger_revision", "consent", "memo", "vault", "already_signed", "zero_partition", "stale_partition", "future_partition", "invalid_digest"} {
		t.Run(name, func(t *testing.T) {
			proposed, proof := p, partition
			switch name {
			case "operation":
				proposed.OperationID = "satchel:ticket:8"
			case "owner":
				proposed.OwnerID = "another-owner"
			case "principal":
				proposed.AmountUWolo = "6000000"
			case "fee":
				proposed.FeeUWolo = "2501"
			case "reservation":
				proposed.ReservationDigest = strings.Repeat("c", 64)
			case "ledger_revision":
				proposed.LedgerRevision = strings.Repeat("c", 64)
			case "consent":
				proposed.ConsentDigest = strings.Repeat("c", 64)
			case "memo":
				proposed.Memo = "AoE2HDBets bet ticket v1 · ticket 8"
			case "vault":
				proposed.Vault = f.config.BettingEscrow
			case "already_signed":
				proposed.Signature = "caller"
				proposed.IssuedAt = 1
				proposed.ExpiresAt = 2
			case "zero_partition":
				proof = VerifiedReviewerPrincipalPartition{}
			case "stale_partition":
				proof.observed = time.Now().Add(-3 * time.Second)
			case "future_partition":
				proof.observed = time.Now().Add(time.Second)
			case "invalid_digest":
				proof.partitionDigest = strings.Repeat("0", 64)
			}
			if got, err := PrepareReviewerPrincipalSpendBinding(proof, proposed, time.Now()); got != (ReviewerPrincipalSpendBinding{}) || !errors.Is(err, ErrReviewerHeld) {
				t.Fatal("different original minted a binding", name, got, err)
			}
		})
	}
	var fromJSON VerifiedReviewerPrincipalPartition
	if json.Unmarshal([]byte(`{"valid":true,"principal":"7000000","partitionDigest":"caller"}`), &fromJSON) != nil {
		t.Fatal("decode")
	}
	if _, err := PrepareReviewerPrincipalSpendBinding(fromJSON, p, time.Now()); !errors.Is(err, ErrReviewerHeld) {
		t.Fatal("request JSON minted a verified binding")
	}
}

func TestReviewerPrincipalBindingDualReviewCensusRetainsFullLiabilities(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	rows, p := principalTestRows(t, f)
	journal, err := f.engine.ReadReviewerPrincipalJournal(t.Context(), p.OwnerID)
	if err != nil {
		t.Fatal(err)
	}
	partition, err := verifyReviewerPrincipalRows(rows, p, journal, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	issuer, err := OpenReviewerIssuer(filepath.Join(t.TempDir(), "binding-issuer.db"), &fakeReviewerEvidence{original: p}, engineTestWagerApprovalKey(), f.engine.policy)
	if err != nil {
		t.Fatal(err)
	}
	defer issuer.Close()
	issued, err := issuer.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	custody, err := f.engine.ReviewerFeeCheckpoint([]string{p.OperationID})
	if err != nil {
		t.Fatal(err)
	}
	bank, _, err := f.reader.ReadCurrentBankProof(t.Context(), p.Vault)
	if err != nil {
		t.Fatal(err)
	}
	observation := ReviewerFinanceObservation{bank: bank, ledger: rows.Global}
	observation.ledger.observedAt = time.Now()
	cfg := censusFixtureConfig(t, f)
	cfg.PrincipalPartitions = &ReviewerPrincipalPartitionSource{} // Non-nil trusted reader; pure validator does no I/O.
	source := &ReviewerReserveCensusSource{config: cfg, required: append([]string{}, reviewerRequiredReserveProducers...)}
	sort.Strings(source.required)
	fees, err := MergeReviewerPendingFees(p, issued, custody, cfg.FeeSources, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	original := censusFixtureBundle(t, f, p, observation, issued, custody, fees)
	binding, err := PrepareReviewerPrincipalSpendBinding(partition, p, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	original.Body.PrincipalSpend = &binding
	censusSignFixtureBundle(f, &original)
	positive, err := source.verifyCoverage(original, p, observation, issued, custody, fees, time.Now(), partition)
	if err != nil || positive.AllOwnerLiabilitiesUWolo != "101000000" {
		t.Fatal("principal evidence reduced debt or failed canonical binding", positive, err)
	}
	budget, err := AssessReviewerFeeBudget(positive, p)
	if err != nil || budget.SpendingAuthorized || budget.BankAuthenticated || budget.OwnerLedgerAuthenticated {
		t.Fatal("binding conferred spending/coverage authority", budget, err)
	}
	for _, name := range []string{"missing", "protocol", "kind", "chain", "denom", "vault", "operation", "owner", "principal", "fingerprint", "reservation", "ledger_revision", "consent", "version", "partition", "owner_ledger", "custody_journal", "missing_opaque", "zero_opaque", "stale_opaque", "legacy_rejects_binding", "signature_does_not_cover_binding"} {
		t.Run(name, func(t *testing.T) {
			bundle := original
			value := binding
			bundle.Body.PrincipalSpend = &value
			copySource := *source
			copySource.config = source.config
			proofs := []VerifiedReviewerPrincipalPartition{partition}
			switch name {
			case "missing":
				bundle.Body.PrincipalSpend = nil
			case "protocol":
				value.Protocol = 2
			case "kind":
				value.Kind = "principal_release"
			case "chain":
				value.ChainID = "other-1"
			case "denom":
				value.Denom = "wolo"
			case "vault":
				value.Vault = f.config.BettingEscrow
			case "operation":
				value.OperationID = "satchel:ticket:8"
			case "owner":
				value.OwnerID = "other-owner"
			case "principal":
				value.PrincipalUWolo = "6000000"
			case "fingerprint":
				value.ProposedFingerprint = strings.Repeat("c", 64)
			case "reservation":
				value.ReservationDigest = strings.Repeat("c", 64)
			case "ledger_revision":
				value.LedgerRevision = strings.Repeat("c", 64)
			case "consent":
				value.ConsentDigest = strings.Repeat("c", 64)
			case "version":
				value.LedgerVersion = "3"
			case "partition":
				value.PartitionSHA256 = strings.Repeat("c", 64)
			case "owner_ledger":
				value.OwnerLedgerSHA256 = strings.Repeat("c", 64)
			case "custody_journal":
				value.CustodyJournalSHA256 = strings.Repeat("c", 64)
			case "missing_opaque":
				proofs = nil
			case "zero_opaque":
				proofs[0] = VerifiedReviewerPrincipalPartition{}
			case "stale_opaque":
				proofs[0].observed = time.Now().Add(-3 * time.Second)
			case "legacy_rejects_binding":
				copySource.config.PrincipalPartitions = nil
			case "signature_does_not_cover_binding":
				bundle.Body.PrincipalSpend = nil
				censusSignFixtureBundle(f, &bundle)
				bundle.Body.PrincipalSpend = &value
			}
			if name != "signature_does_not_cover_binding" {
				censusSignFixtureBundle(f, &bundle)
			}
			if _, err := copySource.verifyCoverage(bundle, p, observation, issued, custody, fees, time.Now(), proofs...); !errors.Is(err, ErrReviewerHeld) {
				t.Fatal("signed body substituted original principal evidence", name, err)
			}
		})
	}
	legacy := *source
	legacy.config.PrincipalPartitions = nil
	without := original
	without.Body.PrincipalSpend = nil
	censusSignFixtureBundle(f, &without)
	if _, err := legacy.verifyCoverage(without, p, observation, issued, custody, fees, time.Now()); err != nil {
		t.Fatal("legacy fee census requires no fabricated principal", err)
	}
	if ReviewerReserveCensusBodyDigest(without.Body) == ReviewerReserveCensusBodyDigest(original.Body) {
		t.Fatal("dual-review inventory digest omitted typed principal binding")
	}
	if f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("non-spending binding executed custody")
	}
}

type principalBindingCensusObserver struct {
	*ReviewerReserveCensusSource
	results []ReviewerFeeCensus
}

func (s *principalBindingCensusObserver) AuthenticatedFeeCensus(ctx context.Context, p WagerReservation) (ReviewerFeeCensus, error) {
	census, err := s.ReviewerReserveCensusSource.AuthenticatedFeeCensus(ctx, p)
	if err == nil {
		s.results = append(s.results, census)
	}
	return census, err
}

func TestReviewerFinancePostgresPrincipalBindingUsesLivePartitionAndPrivateIssuerContext(t *testing.T) {
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
	const role = "satchel_reviewer_binding_it"
	ddl := `CREATE ROLE satchel_reviewer_binding_it LOGIN PASSWORD 'isolated-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.users(id integer PRIMARY KEY,uid text UNIQUE NOT NULL,wallet_address text);
CREATE TABLE public.war_satchel_funded_balances(owner_user_id integer PRIMARY KEY,available_uwolo bigint NOT NULL,reserved_uwolo bigint NOT NULL,committed_uwolo bigint NOT NULL,withdrawal_pending_uwolo bigint NOT NULL,version bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_journal(id bigint PRIMARY KEY,owner_user_id integer NOT NULL,source_key text UNIQUE NOT NULL,event_kind text NOT NULL,amount_uwolo bigint NOT NULL,delta_available_uwolo bigint NOT NULL,delta_reserved_uwolo bigint NOT NULL,delta_committed_uwolo bigint NOT NULL,delta_withdrawal_pending_uwolo bigint NOT NULL,execution_id integer,receipt_id bigint,claim_return_id bigint);
CREATE TABLE public.war_satchel_funded_receipts(vault_address text NOT NULL,chain_id text NOT NULL,canonical_height bigint NOT NULL,amount_uwolo bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_reservations(id text PRIMARY KEY,owner_user_id integer NOT NULL,execution_id integer UNIQUE NOT NULL,amount_uwolo bigint NOT NULL,status text NOT NULL,ticket_request_id text UNIQUE NOT NULL,ticket_id integer,tx_hash text);
CREATE TABLE public.war_satchel_wager_authorizations(operation_id text PRIMARY KEY,reservation_id text UNIQUE NOT NULL,owner_user_id integer NOT NULL,snapshot_json jsonb NOT NULL,reservation_digest text NOT NULL,ledger_revision text NOT NULL,consent_digest text NOT NULL);
CREATE TABLE public.war_satchel_funded_withdrawals(id uuid PRIMARY KEY,owner_user_id integer NOT NULL,owner_wallet_address text NOT NULL,amount_uwolo bigint NOT NULL,status text NOT NULL,tx_hash text,confirmed_height bigint,authorizing_challenge_id uuid NOT NULL);
CREATE TABLE public.war_satchel_withdrawal_authorizations(withdrawal_id uuid PRIMARY KEY,owner_user_id integer NOT NULL,owner_uid text NOT NULL,wallet_address text NOT NULL,vault_address text NOT NULL,amount_uwolo bigint NOT NULL,challenge_id uuid NOT NULL,owner_mandate_json jsonb NOT NULL,owner_mandate_digest text NOT NULL,reservation_digest text NOT NULL,memo text NOT NULL);
GRANT SELECT ON public.users,public.war_satchel_funded_balances,public.war_satchel_funded_journal,public.war_satchel_funded_receipts,public.war_satchel_funded_reservations,public.war_satchel_wager_authorizations,public.war_satchel_funded_withdrawals,public.war_satchel_withdrawal_authorizations TO satchel_reviewer_binding_it;`
	if _, err := admin.ExecContext(t.Context(), ddl); err != nil {
		t.Fatal(err)
	}
	defer func() {
		_, _ = admin.Exec(`DROP TABLE public.war_satchel_withdrawal_authorizations,public.war_satchel_funded_withdrawals,public.war_satchel_wager_authorizations,public.war_satchel_funded_reservations,public.war_satchel_funded_receipts,public.war_satchel_funded_journal,public.war_satchel_funded_balances,public.users;DROP ROLE satchel_reviewer_binding_it`)
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
	pg, err := NewReviewerReadOnlyPGSource(db, role, f.config.FeesUWolo, f.config.Vault, f.config.BettingEscrow)
	if err != nil {
		t.Fatal(err)
	}
	httpCfg := testHTTPConfig(t)
	httpCfg.Accepting = false
	httpCfg.Health.VaultAddress = f.config.Vault
	client, _ := principalTransportTestClient(t, testHTTPHandler(t, f.engine, httpCfg), f.config.Vault, hashJSON(f.engine.policy))
	partitions, err := NewReviewerPrincipalPartitionSourceWithPolicyDigest(pg, client, hashJSON(f.engine.policy))
	if err != nil {
		t.Fatal(err)
	}
	before := readTestCustodyJournal(t, f.engine)
	for _, name := range []string{"positive", "missing", "wrong_partition", "wrong_reservation", "wrong_owner", "wrong_version", "unsigned_binding", "reader_unavailable", "changed_during_completion", "legacy_rejects_binding"} {
		t.Run(name, func(t *testing.T) {
			f.refreshReview(t)
			cfg := censusFixtureConfig(t, f)
			reader := &principalBindingTestReader{inner: partitions}
			cfg.PrincipalPartitions = reader
			if name == "legacy_rejects_binding" {
				cfg.PrincipalPartitions = nil
			}
			if name == "reader_unavailable" {
				reader.before = func(int) error { return ErrReviewerHeld }
			}
			if name == "changed_during_completion" {
				reader.before = func(n int) error {
					if n == 2 {
						exec(`UPDATE public.war_satchel_funded_reservations SET status='unknown_hold'`)
					}
					return nil
				}
				defer exec(`UPDATE public.war_satchel_funded_reservations SET status='reserved'`)
			}
			// Original/owner/Watcher and external producer inventories are
			// explicitly synthetic TEST authorities. PG role/complete partition,
			// native bank, fee journals, service transport and dual signatures are real.
			base, err := NewReviewerFinanceSource(&fakeReviewerEvidence{original: p}, pg, f.reader)
			if err != nil {
				t.Fatal(err)
			}
			coverage := &censusCoverageTestReader{}
			coverage.prepare = func(ctx context.Context) ([]byte, error) {
				issued, err := reviewerIssuedFeesFromContext(ctx)
				if err != nil {
					return nil, err
				}
				custody, err := f.engine.ReviewerFeeCheckpoint([]string{p.OperationID})
				if err != nil {
					return nil, err
				}
				bank, _, err := f.reader.ReadCurrentBankProof(ctx, p.Vault)
				if err != nil {
					return nil, err
				}
				ledger, err := pg.readOwnerLedger(ctx)
				if err != nil {
					return nil, err
				}
				fees, err := MergeReviewerPendingFees(p, issued, custody, cfg.FeeSources, time.Now())
				if err != nil {
					return nil, err
				}
				bundle := censusFixtureBundle(t, f, p, ReviewerFinanceObservation{bank: bank, ledger: ledger}, issued, custody, fees)
				partition, err := partitions.ReadWagerPrincipalPartition(ctx, p)
				if err != nil {
					return nil, err
				}
				binding, err := PrepareReviewerPrincipalSpendBinding(partition, p, time.Now())
				if err != nil {
					return nil, err
				}
				bundle.Body.PrincipalSpend = &binding
				switch name {
				case "missing":
					bundle.Body.PrincipalSpend = nil
				case "wrong_partition":
					binding.PartitionSHA256 = strings.Repeat("c", 64)
				case "wrong_reservation":
					binding.ReservationDigest = strings.Repeat("c", 64)
				case "wrong_owner":
					binding.OwnerID = "other-owner"
				case "wrong_version":
					binding.LedgerVersion = "3"
				}
				if name != "unsigned_binding" {
					censusSignFixtureBundle(f, &bundle)
				}
				return json.Marshal(bundle)
			}
			source, err := NewReviewerReserveCensusSource(base, &censusCustodyTestReader{engine: f.engine}, coverage, cfg)
			if err != nil {
				t.Fatal(err)
			}
			observed := &principalBindingCensusObserver{ReviewerReserveCensusSource: source}
			issuer, err := OpenReviewerIssuer(filepath.Join(t.TempDir(), "binding-issuer.db"), observed, engineTestWagerApprovalKey(), f.engine.policy)
			if err != nil {
				t.Fatal(err)
			}
			defer issuer.Close()
			reply := issuer.ReviewOne(t.Context(), p.OperationID)
			if name == "positive" {
				if reply.Status != "SIGNED" || reply.Approval == nil || reader.reads != 4 || len(observed.results) != 2 {
					t.Fatal("actual PG/native/dual-review binding did not issue exact original", reply, reader.reads, len(observed.results))
				}
				for _, census := range observed.results {
					budget, err := AssessReviewerFeeBudget(census, p)
					if err != nil || census.AllOwnerLiabilitiesUWolo != "101000000" || budget.SpendingAuthorized || budget.OwnerLedgerAuthenticated || budget.BankAuthenticated {
						t.Fatal("binding discharged liability or minted spending", census, budget, err)
					}
				}
				if f.engine.policy.VerifyWager(TransferRequest{OperationID: p.OperationID, Kind: "wager", ChainID: "wolo-1", Denom: "uwolo", OwnerID: p.OwnerID, Sender: p.Vault, Recipient: p.Recipient, AmountUWolo: p.AmountUWolo, Memo: p.Memo, Reservation: reply.Approval}) != nil {
					t.Fatal("issued approval did not bind actual original")
				}
			} else {
				if reply.Status != "PENDING" || reply.Approval != nil {
					t.Fatal("unbound principal reached issuer", name, reply)
				}
				if name == "legacy_rejects_binding" {
					if reader.reads != 0 {
						t.Fatal("legacy path acquired a principal reader")
					}
				} else if reader.reads == 0 {
					t.Fatal("negative failed before reaching actual principal binding", name)
				}
				if name == "changed_during_completion" && reader.reads != 2 {
					t.Fatal("completion change did not reach second actual partition read", reader.reads)
				}
			}
		})
	}
	if after := readTestCustodyJournal(t, f.engine); after.JournalDigest != before.JournalDigest || f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("binding path executed custody or changed its journal")
	}
}
