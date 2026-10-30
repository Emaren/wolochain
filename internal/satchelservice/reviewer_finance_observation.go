package satchelservice

// Actual independently queried bank and HD funded-ledger observations. This
// collector does not turn the incomplete issue #5 producer/liability inventory
// into a global solvency certificate. In particular, historical escrow funds
// are never substituted for the separate custody vault's authenticated assets.
import (
	"context"
	"database/sql"
	"errors"
	"math"
	"strconv"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

type ReviewerFinanceFailure string

const (
	ReviewerFinanceUnavailable     ReviewerFinanceFailure = "reviewer_finance_source_unavailable"
	ReviewerFinanceRoleDenied      ReviewerFinanceFailure = "reviewer_finance_readonly_identity_denied"
	ReviewerFinanceLedgerMismatch  ReviewerFinanceFailure = "reviewer_finance_owner_ledger_inconsistent"
	ReviewerFinanceStale           ReviewerFinanceFailure = "reviewer_finance_observation_stale"
	ReviewerFinanceBankInvalid     ReviewerFinanceFailure = "reviewer_finance_bank_unverifiable"
	ReviewerFinanceCoverageUnknown ReviewerFinanceFailure = "reviewer_finance_global_coverage_unknown"
)

func (e ReviewerFinanceFailure) Error() string        { return string(e) }
func (e ReviewerFinanceFailure) Is(target error) bool { return target == ErrReviewerHeld }

// Every component is NUMERIC before addition: PostgreSQL BIGINT arithmetic
// must not wrap or overflow before the bounded Go validation. Reconciliation
// is per owner, so offsetting corruption between owners cannot cancel out.
// FULL JOIN also catches orphan journal rows. The committed bucket is validated
// historical spend after funding left the vault; current vault liabilities are
// available, reserved (including UNKNOWN sends), and withdrawal-pending funds.
// Separate escrow obligations still require the independent global census.
const reviewerPGFinanceQuery = `
WITH journal AS (
 SELECT owner_user_id, count(*)::numeric AS entries,
        sum(delta_available_uwolo::numeric) AS available,
        sum(delta_reserved_uwolo::numeric) AS reserved,
        sum(delta_committed_uwolo::numeric) AS committed,
        sum(delta_withdrawal_pending_uwolo::numeric) AS withdrawing
 FROM public.war_satchel_funded_journal GROUP BY owner_user_id
), owners AS (
 SELECT b.owner_user_id, b.available_uwolo::numeric AS available,
        b.reserved_uwolo::numeric AS reserved,
        b.committed_uwolo::numeric AS committed,
        b.withdrawal_pending_uwolo::numeric AS withdrawing,
        b.version::numeric AS revision, j.entries,
        b.owner_user_id IS NULL OR b.owner_user_id < 1 OR
        b.available_uwolo < 0 OR b.reserved_uwolo < 0 OR
        b.committed_uwolo < 0 OR b.withdrawal_pending_uwolo < 0 OR b.version < 0 OR
        b.available_uwolo::numeric <> COALESCE(j.available,0) OR
        b.reserved_uwolo::numeric <> COALESCE(j.reserved,0) OR
        b.committed_uwolo::numeric <> COALESCE(j.committed,0) OR
        b.withdrawal_pending_uwolo::numeric <> COALESCE(j.withdrawing,0) AS inconsistent
 FROM public.war_satchel_funded_balances b FULL JOIN journal j USING(owner_user_id)
)
SELECT count(*)::text, COALESCE(sum(available),0)::text,
       COALESCE(sum(reserved),0)::text, COALESCE(sum(committed),0)::text,
       COALESCE(sum(withdrawing),0)::text, COALESCE(sum(revision),0)::text,
       COALESCE(sum(entries),0)::text, COALESCE(bool_or(inconsistent),false),
       EXISTS (SELECT 1 FROM public.war_satchel_funded_receipts
               WHERE vault_address <> $1 OR chain_id <> 'wolo-1'
                  OR canonical_height <= 0 OR amount_uwolo <= 0)
FROM owners
`

// This is independent of the application's credential. Check column-level
// grants too: has_table_privilege alone misses an UPDATE(column) grant.
const reviewerPGFinanceIdentityQuery = `
SELECT session_user, current_user, current_setting('transaction_read_only'),
 COALESCE((SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolreplication
           FROM pg_catalog.pg_roles WHERE rolname=current_user),true) OR
 EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=
  (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)) OR
 pg_catalog.has_database_privilege(current_user,current_database(),'CREATE') OR
 pg_catalog.has_schema_privilege(current_user,'public','CREATE') OR
 (SELECT count(*) <> 3 FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relname IN
   ('war_satchel_funded_balances','war_satchel_funded_journal','war_satchel_funded_receipts')
   AND c.relkind='r' AND c.relpersistence='p' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity),
 EXISTS (
 SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND (
  has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') OR
  has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')))
`

type reviewerOwnerLedger struct {
	owners, available, reserved, committed, withdrawing, revisions, entries string
	inconsistent, wrongVault                                                bool
	observedAt                                                              time.Time
}

func (r reviewerOwnerLedger) total() (string, error) {
	if r.inconsistent || r.wrongVault {
		return "", ReviewerFinanceLedgerMismatch
	}
	// Historical committed spend must remain canonical and reconciled even
	// though it is not another outstanding debt of this physical vault.
	for _, value := range []string{r.owners, r.revisions, r.entries, r.committed} {
		if _, err := reviewerAmount(value, math.MaxInt64, false); err != nil {
			return "", ReviewerFinanceLedgerMismatch
		}
	}
	var sum uint64
	for _, value := range []string{r.available, r.reserved, r.withdrawing} {
		n, err := reviewerAmount(value, math.MaxInt64, false)
		if err != nil {
			return "", ReviewerFinanceLedgerMismatch
		}
		sum, err = reviewerAdd(sum, n)
		if err != nil {
			return "", ReviewerFinanceLedgerMismatch
		}
	}
	return strconv.FormatUint(sum, 10), nil
}

func (s *ReviewerReadOnlyPGSource) readOwnerLedger(ctx context.Context) (reviewerOwnerLedger, error) {
	if s == nil || s.db == nil || s.now == nil || ctx == nil || ctx.Err() != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelRepeatableRead, ReadOnly: true})
	if err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	defer func() { _ = tx.Rollback() }()
	if _, err = tx.ExecContext(ctx, `SET LOCAL search_path = pg_catalog, public`); err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	// Fixed limits apply on the server as well as the client's cancellation.
	if _, err = tx.ExecContext(ctx, `SET LOCAL statement_timeout = '1500ms'`); err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	if _, err = tx.ExecContext(ctx, `SET LOCAL lock_timeout = '100ms'`); err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	// Keep the checked table identities and RLS posture stable through the
	// aggregate. ACCESS SHARE permits financial writers; only concurrent DDL
	// waits. Without this, RLS/table replacement could hide liabilities after
	// the role check and before the query, even in a repeatable-read snapshot.
	if _, err = tx.ExecContext(ctx, `LOCK TABLE public.war_satchel_funded_balances, public.war_satchel_funded_journal, public.war_satchel_funded_receipts IN ACCESS SHARE MODE`); err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	var login, role, readonly string
	var privileged, writable bool
	if tx.QueryRowContext(ctx, reviewerPGFinanceIdentityQuery).Scan(&login, &role, &readonly, &privileged, &writable) != nil ||
		!reviewerPGTrustIdentity(login, role, readonly, privileged, writable, s.expectedRole) {
		return reviewerOwnerLedger{}, ReviewerFinanceRoleDenied
	}
	var row reviewerOwnerLedger
	if err = tx.QueryRowContext(ctx, reviewerPGFinanceQuery, s.vault).Scan(
		&row.owners, &row.available, &row.reserved, &row.committed, &row.withdrawing,
		&row.revisions, &row.entries, &row.inconsistent, &row.wrongVault); err != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	if _, err = row.total(); err != nil {
		return reviewerOwnerLedger{}, err
	}
	if err = tx.Commit(); err != nil || ctx.Err() != nil {
		return reviewerOwnerLedger{}, ReviewerFinanceUnavailable
	}
	row.observedAt = s.now()
	return row, nil
}

type reviewerBankReader interface {
	ReadBankProof(context.Context, string, int64) (satchel.AuthenticatedBankEvidence, satchel.BankProof, error)
}

// ReviewerFinanceObservation contains authenticated assets and a reconciled
// READ-ONLY owner-ledger observation, not an approval. The global missing
// scopes are fixed in code, not a caller-supplied "complete" bit. No conversion
// from JSON, a bare bank amount or an operator environment flag can mint it.
type ReviewerFinanceObservation struct {
	bank   satchel.AuthenticatedBankEvidence
	ledger reviewerOwnerLedger
}

func (o ReviewerFinanceObservation) Bank() satchel.AuthenticatedBankEvidence { return o.bank }

// KnownOwnerLiabilitiesUWolo reports current liabilities of the custody vault.
// It excludes cumulative historical spending and does not inventory claims
// against the distinct betting escrow or establish unencumbered funds.
func (o ReviewerFinanceObservation) KnownOwnerLiabilitiesUWolo() (string, error) {
	return o.ledger.total()
}

// HistoricalCommittedUWolo retains validated cumulative owner spending. This
// history is neither a current vault liability nor available reserve/equity.
func (o ReviewerFinanceObservation) HistoricalCommittedUWolo() (string, error) {
	if _, err := o.ledger.total(); err != nil {
		return "", err
	}
	return o.ledger.committed, nil
}
func (o ReviewerFinanceObservation) SpendingAuthorized() bool { return false }
func (o ReviewerFinanceObservation) FreshAt(now time.Time) bool {
	return o.bank.FreshAt(now) && !o.ledger.observedAt.IsZero() &&
		!o.ledger.observedAt.After(now) && now.Sub(o.ledger.observedAt) <= 2*time.Second
}
func (o ReviewerFinanceObservation) MissingCoverage() []string {
	return []string{"hd_manual_and_founder_obligations", "de_and_external_obligations_and_overlaps",
		"staking_and_treasury_encumbrances", "all_signer_pending_uncertain_and_unmaterialized_fees"}
}

// This composes with the existing original/mandate/live-witness source. It
// collects useful authenticated evidence but deliberately cannot issue a
// complete fee census until issue #5 supplies independently bounded global
// obligations and outgoing-operation coverage. There is no asserted-complete
// switch and no substitute authority invented by this adapter.
type ReviewerFinanceSource struct {
	ReviewerEvidenceSource
	pg   *ReviewerReadOnlyPGSource
	bank reviewerBankReader
	now  func() time.Time
}

func NewReviewerFinanceSource(source ReviewerEvidenceSource, pg *ReviewerReadOnlyPGSource, bank *satchel.TrustedReader) (*ReviewerFinanceSource, error) {
	if source == nil || pg == nil || pg.db == nil || bank == nil {
		return nil, ReviewerFinanceUnavailable
	}
	return &ReviewerFinanceSource{source, pg, bank, time.Now}, nil
}

// ObserveFinance fixes the SDK state height H; its bank proof authenticates
// that state against header H+1. The height is an operator/server-selected read
// parameter, never an instruction to credit or sign. Both observations are
// freshness checked after I/O; they are NOT an atomic DB/chain snapshot.
func (s *ReviewerFinanceSource) ObserveFinance(ctx context.Context, height int64) (ReviewerFinanceObservation, error) {
	if s == nil || s.pg == nil || s.bank == nil || s.now == nil || ctx == nil || ctx.Err() != nil || height <= 0 {
		return ReviewerFinanceObservation{}, ReviewerFinanceUnavailable
	}
	start := time.Now()
	initial := s.now()
	completedAt := func() time.Time {
		now := s.now()
		if elapsed := initial.Add(time.Since(start)); elapsed.After(now) {
			now = elapsed
		}
		return now
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	bank, _, err := s.bank.ReadBankProof(ctx, s.pg.vault, height)
	if err != nil {
		return ReviewerFinanceObservation{}, errors.Join(ReviewerFinanceBankInvalid, err)
	}
	// Head observations are timestamped during the bank query. Comparing them
	// with the pre-query clock would reject authentic evidence as future-dated.
	bankCompleted := completedAt()
	if ctx.Err() != nil || bank.VaultAddress() != s.pg.vault || bank.Height() != height || bank.CommitHeight() != height+1 || !bank.FreshAt(bankCompleted) {
		return ReviewerFinanceObservation{}, ReviewerFinanceBankInvalid
	}
	ledger, err := s.pg.readOwnerLedger(ctx)
	if err != nil {
		return ReviewerFinanceObservation{}, err
	}
	now := completedAt()
	if ctx.Err() != nil || !bank.FreshAt(now) || ledger.observedAt.After(now) || now.Sub(ledger.observedAt) > 2*time.Second {
		return ReviewerFinanceObservation{}, ReviewerFinanceStale
	}
	return ReviewerFinanceObservation{bank, ledger}, nil
}

func (*ReviewerFinanceSource) AuthenticatedFeeCensus(context.Context, WagerReservation) (ReviewerFeeCensus, error) {
	return ReviewerFeeCensus{}, ReviewerFinanceCoverageUnknown
}

var _ ReviewerEvidenceSource = (*ReviewerFinanceSource)(nil)
