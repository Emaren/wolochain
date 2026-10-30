package satchelservice

// Principal partition evidence is deliberately separate from reserve coverage.
// It proves an exclusive existing HD debit; it grants no signature, spend,
// credit, fee release, or reduction of the independently reviewed liabilities.
import (
	"context"
	"crypto/ed25519"
	"database/sql"
	"encoding/json"
	"math"
	"math/big"
	"strconv"
	"strings"
	"time"

	bolt "go.etcd.io/bbolt"
)

const reviewerPrincipalMaxRows = 10000
const reviewerPrincipalMaxBytes = 8 << 20

// The opaque snapshot can only be produced by the actual custody journal
// reader. An HTTP implementation must authenticate the pinned service before
// constructing it; decoding caller JSON into this type cannot create evidence.
type ReviewerPrincipalJournalSnapshot struct {
	valid                        bool
	owner, vault, policy, digest string
	observed                     time.Time
	effects                      map[string]reviewerPrincipalEffect
}

type reviewerPrincipalEffect struct {
	Kind, Owner, Amount, Recipient, Memo, OriginalFingerprint string
	ReservationDigest, Fee, Status, TxHash                    string
	Height                                                    int64
}

type ReviewerPrincipalJournalReader interface {
	ReadReviewerPrincipalJournal(context.Context, string) (ReviewerPrincipalJournalSnapshot, error)
}

// ReadReviewerPrincipalJournal uses the existing full-journal validator and
// native signed-byte validator in one read transaction. It inventories ALL
// operations, rather than IDs chosen by the app, so omitted HD holds cannot
// hide a confirmed outflow or an already consumed operation identity.
func (e *Engine) ReadReviewerPrincipalJournal(ctx context.Context, owner string) (ReviewerPrincipalJournalSnapshot, error) {
	if e == nil || ctx == nil || ctx.Err() != nil || !ownerUIDPattern.MatchString(owner) {
		return ReviewerPrincipalJournalSnapshot{}, ErrReviewerHeld
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.db == nil || e.backend == nil || e.now == nil || ctx.Err() != nil {
		return ReviewerPrincipalJournalSnapshot{}, ErrReviewerHeld
	}
	out := ReviewerPrincipalJournalSnapshot{owner: owner, vault: e.policy.Vault, effects: map[string]reviewerPrincipalEffect{}}
	err := e.db.View(func(tx *bolt.Tx) error {
		journal, err := e.custodyJournalTx(tx)
		if err != nil || journal.OperationsCount > reviewerPrincipalMaxRows || journal.UnresolvedCount != 0 || ctx.Err() != nil {
			return ErrReviewerHeld // The existing global uncertain-signer fence remains binding.
		}
		out.policy, out.digest = journal.PolicyDigest, journal.JournalDigest
		var bytesRead int
		return tx.Bucket(operations).ForEach(func(id, value []byte) error {
			if ctx.Err() != nil || value == nil || len(id)+len(value) > reviewerPrincipalMaxBytes-bytesRead {
				return ErrReviewerHeld
			}
			bytesRead += len(id) + len(value)
			r, err := load(tx, string(id))
			if err != nil {
				return ErrReviewerHeld
			}
			request := r.Request
			var issued time.Time
			var original, reservation string
			switch request.Kind {
			case "wager":
				if request.Reservation == nil {
					return ErrReviewerHeld
				}
				issued = time.Unix(request.Reservation.IssuedAt, 0)
				original = e.custodyWagerFingerprint(request)
				reservation = request.Reservation.ReservationDigest
			case "withdrawal":
				if request.Approval == nil || request.OwnerMandate == nil {
					return ErrReviewerHeld
				}
				issued = time.Unix(request.Approval.IssuedAt, 0)
				mandateIssued, err := time.Parse(time.RFC3339Nano, request.OwnerMandate.Challenge.IssuedAtUTC)
				if err != nil {
					return ErrReviewerHeld
				}
				if mandateIssued.After(issued) {
					issued = mandateIssued
				}
				reservation = request.Approval.ReservationDigest
				original = hashJSON([]any{"aoe2war/satchel/withdraw-original/v1", request.OperationID, request.OwnerID,
					request.Sender, request.Recipient, request.AmountUWolo, request.Memo, reservation, OwnerMandateDigest(*request.OwnerMandate)})
			default:
				return ErrReviewerHeld
			}
			// Historical expiry never erases a liability or renews authorization.
			if issued.Unix() <= 0 || original == "" || !validReserveDigest(reservation) ||
				!ownerUIDPattern.MatchString(request.OwnerID) || e.policy.validate(request, issued) != nil {
				return ErrReviewerHeld
			}
			out.effects[string(id)] = reviewerPrincipalEffect{Kind: request.Kind, Owner: request.OwnerID, Amount: request.AmountUWolo,
				Recipient: request.Recipient, Memo: request.Memo, OriginalFingerprint: original, ReservationDigest: reservation,
				Status: r.Result.Status, TxHash: r.Result.TxHash, Height: r.Confirmation.Height}
			if request.Reservation != nil {
				effect := out.effects[string(id)]
				effect.Fee = request.Reservation.FeeUWolo
				out.effects[string(id)] = effect
			}
			return nil
		})
	})
	if err != nil || ctx.Err() != nil {
		return ReviewerPrincipalJournalSnapshot{}, ErrReviewerHeld
	}
	out.observed, out.valid = e.now(), true
	return out, nil
}

// VerifiedReviewerPrincipalPartition cannot be constructed from amounts or a
// JSON "complete" flag. Its digests must still be bound by both independent
// reserve reviewers before any operation-specific custody discharge is wired.
type VerifiedReviewerPrincipalPartition struct {
	valid                                                    bool
	operation, owner, principal, proposedFingerprint         string
	partitionDigest, ownerLedgerDigest, custodyJournalDigest string
	ledgerVersion                                            string
	observed                                                 time.Time
}

func (p VerifiedReviewerPrincipalPartition) PrincipalUWolo() (string, error) {
	if !p.valid {
		return "", ErrReviewerHeld
	}
	return p.principal, nil
}
func (p VerifiedReviewerPrincipalPartition) PartitionSHA256() string   { return p.partitionDigest }
func (p VerifiedReviewerPrincipalPartition) OwnerLedgerSHA256() string { return p.ownerLedgerDigest }
func (p VerifiedReviewerPrincipalPartition) CustodyJournalSHA256() string {
	return p.custodyJournalDigest
}
func (p VerifiedReviewerPrincipalPartition) ProposedFingerprint() string {
	return p.proposedFingerprint
}
func (p VerifiedReviewerPrincipalPartition) LedgerVersion() string { return p.ledgerVersion }
func (p VerifiedReviewerPrincipalPartition) FreshAt(now time.Time) bool {
	return p.valid && !p.observed.IsZero() && !p.observed.After(now) && now.Sub(p.observed) <= 2*time.Second
}
func (VerifiedReviewerPrincipalPartition) SpendingAuthorized() bool { return false }

type ReviewerPrincipalPartitionSource struct {
	pg      *ReviewerReadOnlyPGSource
	journal ReviewerPrincipalJournalReader
	policy  string
}

func NewReviewerPrincipalPartitionSource(pg *ReviewerReadOnlyPGSource, journal ReviewerPrincipalJournalReader, expected Policy) (*ReviewerPrincipalPartitionSource, error) {
	if pg == nil || pg.db == nil || pg.now == nil || journal == nil || expected.Vault != pg.vault || expected.BettingEscrow != pg.escrow ||
		expected.MaxAmountUWolo == 0 || len(expected.WagerApprovalKey) != ed25519.PublicKeySize || len(expected.WithdrawalApprovalKey) != ed25519.PublicKeySize ||
		bytesAllZero(expected.WagerApprovalKey) || bytesAllZero(expected.WithdrawalApprovalKey) || string(expected.WagerApprovalKey) == string(expected.WithdrawalApprovalKey) {
		return nil, ErrReviewerHeld
	}
	return NewReviewerPrincipalPartitionSourceWithPolicyDigest(pg, journal, hashJSON(expected))
}

// The separately enrolled custody policy may have a larger product ceiling
// than the reviewer's canary policy. Pin its exact protected startup digest;
// neither an operation request nor the service response chooses this root.
func NewReviewerPrincipalPartitionSourceWithPolicyDigest(pg *ReviewerReadOnlyPGSource, journal ReviewerPrincipalJournalReader, expectedCustodyPolicyDigest string) (*ReviewerPrincipalPartitionSource, error) {
	if pg == nil || pg.db == nil || pg.now == nil || journal == nil || !reviewerPGRole.MatchString(pg.expectedRole) ||
		!validAddress(pg.vault) || !validAddress(pg.escrow) || pg.vault == pg.escrow || !reviewerUnsignedDecimal(pg.fee, false, reviewerMaxOperationFeeUWolo) ||
		!validReserveDigest(expectedCustodyPolicyDigest) {
		return nil, ErrReviewerHeld
	}
	return &ReviewerPrincipalPartitionSource{pg: pg, journal: journal, policy: expectedCustodyPolicyDigest}, nil
}

// This is intentionally a wager-only discharge surface. Withdrawals remain in
// the complete owner partition but acquire no new execution authority here.
func (s *ReviewerPrincipalPartitionSource) ReadWagerPrincipalPartition(ctx context.Context, proposed WagerReservation) (VerifiedReviewerPrincipalPartition, error) {
	if s == nil || s.pg == nil || s.journal == nil || ctx == nil || ctx.Err() != nil || !validReviewerFeeProposal(proposed, s.pg.vault) ||
		proposed.Recipient != s.pg.escrow || proposed.FeeUWolo != s.pg.fee {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	started, elapsed := s.pg.now(), time.Now()
	before, err := s.journal.ReadReviewerPrincipalJournal(ctx, proposed.OwnerID)
	if err != nil {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	rows, err := s.pg.readPrincipalPartition(ctx, proposed.OwnerID)
	if err != nil {
		return VerifiedReviewerPrincipalPartition{}, err
	}
	after, err := s.journal.ReadReviewerPrincipalJournal(ctx, proposed.OwnerID)
	if err != nil {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	// A second independent SQL transaction detects a hold/owner/journal change
	// during custody I/O; REPEATABLE READ in the first transaction would hide it.
	currentRows, err := s.pg.readPrincipalPartition(ctx, proposed.OwnerID)
	completed := s.pg.now()
	if floor := started.Add(time.Since(elapsed)); completed.Before(floor) {
		completed = floor
	}
	initialDigest, initialErr := principalRowsDigest(rows)
	currentDigest, currentErr := principalRowsDigest(currentRows)
	if err != nil || initialErr != nil || currentErr != nil || initialDigest != currentDigest || ctx.Err() != nil || before.digest != after.digest || before.policy != after.policy ||
		!principalJournalCurrent(before, proposed.OwnerID, s.pg.vault, s.policy, completed) ||
		!principalJournalCurrent(after, proposed.OwnerID, s.pg.vault, s.policy, completed) {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	result, err := verifyReviewerPrincipalRows(rows, proposed, after, completed)
	finished := s.pg.now()
	if floor := started.Add(time.Since(elapsed)); finished.Before(floor) {
		finished = floor
	}
	if err != nil || ctx.Err() != nil || !result.FreshAt(finished) ||
		!principalJournalCurrent(before, proposed.OwnerID, s.pg.vault, s.policy, finished) ||
		!principalJournalCurrent(after, proposed.OwnerID, s.pg.vault, s.policy, finished) {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	return result, nil
}

func principalJournalCurrent(j ReviewerPrincipalJournalSnapshot, owner, vault, policy string, now time.Time) bool {
	return j.valid && j.owner == owner && j.vault == vault && j.policy == policy && validReserveDigest(j.digest) &&
		!j.observed.IsZero() && !j.observed.After(now) && now.Sub(j.observed) <= 2*time.Second && len(j.effects) <= reviewerPrincipalMaxRows
}

type reviewerPrincipalWager struct {
	ID, Owner, Execution, Amount, Status, Operation, Ticket, TxHash                      string
	AuthOwner, AuthOperation, Snapshot, ReservationDigest, LedgerRevision, ConsentDigest string
}
type reviewerPrincipalWithdrawal struct {
	ID, Owner, Wallet, Amount, Status, TxHash, Height, Challenge string
	AuthOwner, UID, AuthWallet, Vault, AuthAmount, AuthChallenge string
	Mandate, MandateDigest, ReservationDigest, Memo              string
}
type reviewerPrincipalJournalRow struct {
	ID, Source, Event, Amount, Available, Reserved, Committed, Withdrawing string
	Execution, Receipt, ClaimReturn                                        string
}
type reviewerPrincipalRows struct {
	Owner, UID, Wallet, Available, Reserved, Committed, Withdrawing, Version string
	Global                                                                   reviewerOwnerLedger
	Wagers                                                                   []reviewerPrincipalWager
	Withdrawals                                                              []reviewerPrincipalWithdrawal
	Journal                                                                  []reviewerPrincipalJournalRow
}

func principalRowsDigest(rows reviewerPrincipalRows) (string, error) {
	global, err := ReviewerOwnerLedgerCheckpointDigest(ReviewerFinanceObservation{ledger: rows.Global})
	if err != nil {
		return "", err
	}
	return hashJSON([]any{"aoe2war/satchel/owner-principal-rows/v1", rows, global}), nil
}

const reviewerPrincipalTables = `public.users, public.war_satchel_funded_balances, public.war_satchel_funded_journal, public.war_satchel_funded_receipts, public.war_satchel_funded_reservations, public.war_satchel_wager_authorizations, public.war_satchel_funded_withdrawals, public.war_satchel_withdrawal_authorizations`
const reviewerPrincipalIdentityQuery = `SELECT count(*)=8 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN ('users','war_satchel_funded_balances','war_satchel_funded_journal','war_satchel_funded_receipts',
 'war_satchel_funded_reservations','war_satchel_wager_authorizations','war_satchel_funded_withdrawals','war_satchel_withdrawal_authorizations')
 AND c.relkind='r' AND c.relpersistence='p' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity`
const reviewerPrincipalWagersQuery = `SELECT COALESCE(r.id,''),COALESCE(r.owner_user_id::text,''),COALESCE(r.execution_id::text,''),COALESCE(r.amount_uwolo::text,''),
 COALESCE(r.status,''),COALESCE(r.ticket_request_id,''),COALESCE(r.ticket_id::text,''),COALESCE(r.tx_hash,''),COALESCE(a.owner_user_id::text,''),COALESCE(a.operation_id,''),
 CASE WHEN octet_length(a.snapshot_json::text)<=16384 THEN COALESCE(a.snapshot_json::text,'') ELSE '' END,
 COALESCE(a.reservation_digest,''),COALESCE(a.ledger_revision,''),COALESCE(a.consent_digest,'')
 FROM public.war_satchel_funded_reservations r FULL JOIN public.war_satchel_wager_authorizations a ON a.reservation_id=r.id
 WHERE r.owner_user_id=$1 OR a.owner_user_id=$1 ORDER BY r.id,a.operation_id LIMIT 10001`
const reviewerPrincipalWithdrawalsQuery = `SELECT COALESCE(w.id::text,''),COALESCE(w.owner_user_id::text,''),COALESCE(w.owner_wallet_address,''),COALESCE(w.amount_uwolo::text,''),
 COALESCE(w.status,''),COALESCE(w.tx_hash,''),COALESCE(w.confirmed_height::text,''),COALESCE(w.authorizing_challenge_id::text,''),
 COALESCE(a.owner_user_id::text,''),COALESCE(a.owner_uid,''),COALESCE(a.wallet_address,''),COALESCE(a.vault_address,''),COALESCE(a.amount_uwolo::text,''),
 COALESCE(a.challenge_id::text,''),CASE WHEN octet_length(a.owner_mandate_json::text)<=16384 THEN COALESCE(a.owner_mandate_json::text,'') ELSE '' END,
 COALESCE(a.owner_mandate_digest,''),COALESCE(a.reservation_digest,''),COALESCE(a.memo,'')
 FROM public.war_satchel_funded_withdrawals w FULL JOIN public.war_satchel_withdrawal_authorizations a ON a.withdrawal_id=w.id
 WHERE w.owner_user_id=$1 OR a.owner_user_id=$1 ORDER BY w.id LIMIT 10001`
const reviewerPrincipalJournalQuery = `SELECT id::text,source_key,event_kind,amount_uwolo::text,delta_available_uwolo::text,delta_reserved_uwolo::text,
 delta_committed_uwolo::text,delta_withdrawal_pending_uwolo::text,COALESCE(execution_id::text,''),COALESCE(receipt_id::text,''),COALESCE(claim_return_id::text,'')
 FROM public.war_satchel_funded_journal WHERE owner_user_id=$1 ORDER BY id LIMIT 10001`

func (s *ReviewerReadOnlyPGSource) readPrincipalPartition(ctx context.Context, owner string) (reviewerPrincipalRows, error) {
	var out reviewerPrincipalRows
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelRepeatableRead, ReadOnly: true})
	if err != nil {
		return out, ErrReviewerHeld
	}
	defer func() { _ = tx.Rollback() }()
	for _, statement := range []string{`SET LOCAL search_path=pg_catalog,public`, `SET LOCAL statement_timeout='1500ms'`, `SET LOCAL lock_timeout='100ms'`, `LOCK TABLE ` + reviewerPrincipalTables + ` IN ACCESS SHARE MODE`} {
		if _, err = tx.ExecContext(ctx, statement); err != nil {
			return out, ErrReviewerHeld
		}
	}
	var login, role, readonly string
	var privileged, writable, tables bool
	if tx.QueryRowContext(ctx, reviewerPGFinanceIdentityQuery).Scan(&login, &role, &readonly, &privileged, &writable) != nil ||
		!reviewerPGTrustIdentity(login, role, readonly, privileged, writable, s.expectedRole) ||
		tx.QueryRowContext(ctx, reviewerPrincipalIdentityQuery).Scan(&tables) != nil || !tables {
		return out, ErrReviewerHeld
	}
	if tx.QueryRowContext(ctx, `SELECT u.id::text,u.uid,COALESCE(u.wallet_address,''),b.available_uwolo::text,b.reserved_uwolo::text,b.committed_uwolo::text,b.withdrawal_pending_uwolo::text,b.version::text FROM public.users u JOIN public.war_satchel_funded_balances b ON b.owner_user_id=u.id WHERE u.uid=$1 AND (SELECT count(*) FROM public.users WHERE uid=$1)=1`, owner).
		Scan(&out.Owner, &out.UID, &out.Wallet, &out.Available, &out.Reserved, &out.Committed, &out.Withdrawing, &out.Version) != nil {
		return out, ErrReviewerHeld
	}
	if tx.QueryRowContext(ctx, reviewerPGFinanceQuery, s.vault).Scan(&out.Global.owners, &out.Global.available, &out.Global.reserved, &out.Global.committed, &out.Global.withdrawing, &out.Global.revisions, &out.Global.entries, &out.Global.inconsistent, &out.Global.wrongVault) != nil {
		return out, ErrReviewerHeld
	}
	if _, err = out.Global.total(); err != nil {
		return out, err
	}
	bytesRead, count := 0, 0
	bounded := func(value any) bool {
		raw, err := json.Marshal(value)
		bytesRead += len(raw)
		count++
		return err == nil && bytesRead <= reviewerPrincipalMaxBytes && count <= reviewerPrincipalMaxRows
	}
	wagers, err := tx.QueryContext(ctx, reviewerPrincipalWagersQuery, out.Owner)
	if err != nil {
		return out, ErrReviewerHeld
	}
	for wagers.Next() {
		var r reviewerPrincipalWager
		if wagers.Scan(&r.ID, &r.Owner, &r.Execution, &r.Amount, &r.Status, &r.Operation, &r.Ticket, &r.TxHash, &r.AuthOwner, &r.AuthOperation, &r.Snapshot, &r.ReservationDigest, &r.LedgerRevision, &r.ConsentDigest) != nil || !bounded(r) {
			_ = wagers.Close()
			return out, ErrReviewerHeld
		}
		out.Wagers = append(out.Wagers, r)
	}
	if err = wagers.Err(); err != nil {
		_ = wagers.Close()
		return out, ErrReviewerHeld
	}
	_ = wagers.Close()
	withdrawals, err := tx.QueryContext(ctx, reviewerPrincipalWithdrawalsQuery, out.Owner)
	if err != nil {
		return out, ErrReviewerHeld
	}
	for withdrawals.Next() {
		var r reviewerPrincipalWithdrawal
		if withdrawals.Scan(&r.ID, &r.Owner, &r.Wallet, &r.Amount, &r.Status, &r.TxHash, &r.Height, &r.Challenge, &r.AuthOwner, &r.UID, &r.AuthWallet, &r.Vault, &r.AuthAmount, &r.AuthChallenge, &r.Mandate, &r.MandateDigest, &r.ReservationDigest, &r.Memo) != nil || !bounded(r) {
			_ = withdrawals.Close()
			return out, ErrReviewerHeld
		}
		out.Withdrawals = append(out.Withdrawals, r)
	}
	if err = withdrawals.Err(); err != nil {
		_ = withdrawals.Close()
		return out, ErrReviewerHeld
	}
	_ = withdrawals.Close()
	journal, err := tx.QueryContext(ctx, reviewerPrincipalJournalQuery, out.Owner)
	if err != nil {
		return out, ErrReviewerHeld
	}
	for journal.Next() {
		var r reviewerPrincipalJournalRow
		if journal.Scan(&r.ID, &r.Source, &r.Event, &r.Amount, &r.Available, &r.Reserved, &r.Committed, &r.Withdrawing, &r.Execution, &r.Receipt, &r.ClaimReturn) != nil || !bounded(r) {
			_ = journal.Close()
			return out, ErrReviewerHeld
		}
		out.Journal = append(out.Journal, r)
	}
	if err = journal.Err(); err != nil {
		_ = journal.Close()
		return out, ErrReviewerHeld
	}
	_ = journal.Close()
	if tx.Commit() != nil || ctx.Err() != nil {
		return out, ErrReviewerHeld
	}
	return out, nil
}

func verifyReviewerPrincipalRows(rows reviewerPrincipalRows, proposed WagerReservation, native ReviewerPrincipalJournalSnapshot, now time.Time) (VerifiedReviewerPrincipalPartition, error) {
	bad := func() (VerifiedReviewerPrincipalPartition, error) {
		return VerifiedReviewerPrincipalPartition{}, ErrReviewerHeld
	}
	owner, err := reviewerAmount(rows.Owner, math.MaxInt32, true)
	if err != nil || rows.UID != proposed.OwnerID || !validAddress(rows.Wallet) || !native.valid || native.owner != rows.UID ||
		!validReserveDigest(native.digest) || len(rows.Wagers)+len(rows.Withdrawals)+len(rows.Journal) > reviewerPrincipalMaxRows {
		return bad()
	}
	for _, v := range []string{rows.Available, rows.Reserved, rows.Committed, rows.Withdrawing, rows.Version} {
		if _, err := reviewerAmount(v, math.MaxInt64, false); err != nil {
			return bad()
		}
	}
	if _, exists := native.effects[proposed.OperationID]; exists {
		return bad()
	} // Replays are handled by Engine; no new principal grant.
	expected := map[string]reviewerPrincipalJournalRow{}
	journalBySource := map[string]reviewerPrincipalJournalRow{}
	for _, j := range rows.Journal {
		if _, duplicate := journalBySource[j.Source]; duplicate {
			return bad()
		}
		journalBySource[j.Source] = j
	}
	operations := map[string]bool{}
	reservations := map[string]bool{}
	var reserved, committed, withdrawing uint64
	found := false
	add := func(dst *uint64, amount string) bool {
		n, e := reviewerAmount(amount, math.MaxInt64, true)
		if e != nil {
			return false
		}
		total, e := reviewerAdd(*dst, n)
		if e != nil || total > math.MaxInt64 {
			return false
		}
		*dst = total
		return true
	}
	entry := func(source, event, amount, available, reserve, commit, withdraw, execution string) bool {
		if _, ok := expected[source]; ok {
			return false
		}
		expected[source] = reviewerPrincipalJournalRow{Source: source, Event: event, Amount: amount, Available: available, Reserved: reserve, Committed: commit, Withdrawing: withdraw, Execution: execution}
		return true
	}
	for _, w := range rows.Wagers {
		_, e := reviewerAmount(w.Execution, 999999999999, true)
		if e != nil || w.Owner != rows.Owner || w.ID != "satchel:reserve:"+w.Execution || w.Operation != "satchel:ticket:"+w.Execution || !wagerIDs.MatchString(w.Operation) || operations[w.Operation] ||
			!reviewerUnsignedDecimal(w.Amount, false, ProductMaxWagerUWolo) {
			return bad()
		}
		operations[w.Operation] = true
		if !entry(w.ID, "wager_reserve", w.Amount, "-"+w.Amount, w.Amount, "0", "0", w.Execution) {
			return bad()
		}
		var origin ReviewerHDOriginResult
		if w.AuthOwner != "" {
			if w.AuthOwner != rows.Owner || w.AuthOperation != w.Operation {
				return bad()
			}
			origin, e = VerifyReviewerHDOrigin([]byte(w.Snapshot), ReviewerHDOriginColumns{OperationID: w.Operation, ReservationID: w.ID, OwnerUserID: int64(owner), ReservationDigest: w.ReservationDigest, LedgerRevision: w.LedgerRevision, ConsentDigest: w.ConsentDigest})
			if e != nil || origin.OwnerUID != rows.UID || origin.AmountUWolo != w.Amount || origin.Vault != proposed.Vault || origin.Recipient != proposed.Recipient || reservations[w.ReservationDigest] || origin.JournalID != journalBySource[w.ID].ID {
				return bad()
			}
			reservations[w.ReservationDigest] = true
		} else if w.AuthOperation != "" || w.Snapshot != "" || w.ReservationDigest != "" || w.LedgerRevision != "" || w.ConsentDigest != "" {
			return bad()
		}
		switch w.Status {
		case "reserved", "unknown_hold":
			if w.Ticket != "" || w.TxHash != "" || !add(&reserved, w.Amount) {
				return bad()
			}
		case "committed":
			if origin.OperationID == "" || w.Ticket != strconv.FormatInt(origin.TicketID, 10) || !principalTxHash(w.TxHash) || !add(&committed, w.Amount) ||
				!entry("satchel:commit:"+w.ID, "wager_commit", w.Amount, "0", "-"+w.Amount, w.Amount, "0", w.Execution) {
				return bad()
			}
		case "released":
			if w.Ticket != "" || w.TxHash != "" || !entry("satchel:refund:"+w.ID, "wager_refund", w.Amount, w.Amount, "-"+w.Amount, "0", "0", w.Execution) {
				return bad()
			}
		default:
			return bad()
		}
		if w.Operation == proposed.OperationID {
			if found || w.Status != "reserved" || origin.OwnerWallet != rows.Wallet || origin.ReservationDigest != proposed.ReservationDigest || origin.LedgerRevision != proposed.LedgerRevision || origin.ConsentDigest != proposed.ConsentDigest || origin.Memo != proposed.Memo || origin.AmountUWolo != proposed.AmountUWolo {
				return bad()
			}
			found = true
		}
		if effect, exists := native.effects[w.Operation]; exists {
			if effect.Owner != rows.UID || effect.Kind != "wager" || effect.Amount != w.Amount || origin.OperationID == "" || effect.ReservationDigest != w.ReservationDigest || effect.Recipient != origin.Recipient || effect.Memo != origin.Memo {
				return bad()
			}
			original := WagerReservation{Version: 1, OperationID: w.Operation, OwnerID: rows.UID, Vault: proposed.Vault, Recipient: origin.Recipient, AmountUWolo: w.Amount, Memo: origin.Memo, ReservationDigest: w.ReservationDigest, LedgerRevision: w.LedgerRevision, ConsentDigest: w.ConsentDigest, FeeUWolo: effect.Fee}
			if effect.OriginalFingerprint != reviewerFingerprint(original) || !principalTerminalMatches(effect, w.Status == "committed", w.TxHash, "") {
				return bad()
			}
		} else if w.Status == "committed" {
			return bad()
		}
	}
	for _, w := range rows.Withdrawals {
		op := "satchel:withdrawal:" + w.ID
		if !uuid.MatchString(w.ID) || w.Owner != rows.Owner || w.AuthOwner != rows.Owner || w.UID != rows.UID || w.AuthWallet != w.Wallet || w.Vault != proposed.Vault || w.AuthAmount != w.Amount || w.AuthChallenge != w.Challenge ||
			!uuid.MatchString(w.Challenge) || !validAddress(w.Wallet) || w.Wallet == w.Vault || !reviewerUnsignedDecimal(w.Amount, false, 50000000000) || operations[op] || !validReserveDigest(w.ReservationDigest) || reservations[w.ReservationDigest] {
			return bad()
		}
		operations[op], reservations[w.ReservationDigest] = true, true
		var mandate OwnerWithdrawalMandate
		if chainStrictPrincipalJSON(w.Mandate, &mandate) != nil || OwnerMandateDigest(mandate) != w.MandateDigest || w.Memo != "aoe2war/satchel/withdraw/v1/"+w.ID {
			return bad()
		}
		reservation := hashJSON([]any{"aoe2war/satchel/hd-reservation/v1", w.ID, int64(owner), rows.UID, w.Wallet, w.Vault, w.Amount, w.Memo, "satchel:withdraw:reserve:" + w.ID, OwnerMandateDigest(mandate)})
		issued, e := time.Parse(time.RFC3339Nano, mandate.Challenge.IssuedAtUTC)
		if e != nil || reservation != w.ReservationDigest {
			return bad()
		}
		expires, e := time.Parse(time.RFC3339Nano, mandate.Challenge.ExpiresAtUTC)
		if e != nil {
			return bad()
		}
		a := WithdrawalApproval{ChallengeID: w.Challenge, ReservationDigest: reservation, HoldDigest: WithdrawalHoldDigest(reservation, mandate), IssuedAt: issued.Unix(), ExpiresAt: expires.Unix()}
		request := TransferRequest{OwnerID: rows.UID, Recipient: w.Wallet, AmountUWolo: w.Amount, Approval: &a, OwnerMandate: &mandate}
		if verifyOwnerWithdrawal(request, issued) != nil || !entry("satchel:withdraw:reserve:"+w.ID, "withdraw_reserve", w.Amount, "-"+w.Amount, "0", "0", w.Amount, "") {
			return bad()
		}
		switch w.Status {
		case "reserved", "unknown_hold":
			if w.TxHash != "" || w.Height != "" || !add(&withdrawing, w.Amount) {
				return bad()
			}
		case "sent":
			if !principalTxHash(w.TxHash) || !reviewerUnsignedDecimal(w.Height, false, math.MaxInt64) || !entry("satchel:withdraw:sent:"+w.ID, "withdraw_sent", w.Amount, "0", "0", "0", "-"+w.Amount, "") {
				return bad()
			}
		case "cancelled":
			if w.TxHash != "" || w.Height != "" || !entry("satchel:withdraw:cancel:"+w.ID, "withdraw_cancel", w.Amount, w.Amount, "0", "0", "-"+w.Amount, "") {
				return bad()
			}
		default:
			return bad()
		}
		if effect, exists := native.effects[op]; exists {
			original := hashJSON([]any{"aoe2war/satchel/withdraw-original/v1", op, rows.UID, w.Vault, w.Wallet, w.Amount, w.Memo, reservation, OwnerMandateDigest(mandate)})
			if effect.Owner != rows.UID || effect.Kind != "withdrawal" || effect.Amount != w.Amount || effect.Recipient != w.Wallet || effect.Memo != w.Memo || effect.ReservationDigest != reservation || effect.OriginalFingerprint != original || !principalTerminalMatches(effect, w.Status == "sent", w.TxHash, w.Height) {
				return bad()
			}
		} else if w.Status == "sent" {
			return bad()
		}
	}
	// Every native effect attributed to this owner must have an HD hold. No
	// aggregate netting can conceal a confirmed-but-unposted/missing outflow.
	for op, effect := range native.effects {
		if effect.Owner == rows.UID && !operations[op] {
			return bad()
		}
	}
	if !found || strconv.FormatUint(reserved, 10) != rows.Reserved || strconv.FormatUint(committed, 10) != rows.Committed || strconv.FormatUint(withdrawing, 10) != rows.Withdrawing {
		return bad()
	}
	totals := []*big.Int{new(big.Int), new(big.Int), new(big.Int), new(big.Int)}
	last := uint64(0)
	for _, j := range rows.Journal {
		id, e := reviewerAmount(j.ID, math.MaxInt64, true)
		if e != nil || id <= last || !reviewerUnsignedDecimal(j.Amount, false, math.MaxInt64) {
			return bad()
		}
		last = id
		if want, ok := expected[j.Source]; ok {
			if j.Event != want.Event || j.Amount != want.Amount || j.Available != want.Available || j.Reserved != want.Reserved || j.Committed != want.Committed || j.Withdrawing != want.Withdrawing || j.Execution != want.Execution || j.Receipt != "" || j.ClaimReturn != "" {
				return bad()
			}
			delete(expected, j.Source)
		} else {
			if j.Available != j.Amount || j.Reserved != "0" || j.Committed != "0" || j.Withdrawing != "0" || j.Execution != "" {
				return bad()
			}
			switch j.Event {
			case "deposit_credit":
				if !reviewerUnsignedDecimal(j.Receipt, false, math.MaxInt64) || j.ClaimReturn != "" || !strings.HasPrefix(j.Source, "satchel:credit:wolo-1:") || !strings.HasSuffix(j.Source, ":0") || !principalTxHash(strings.TrimSuffix(strings.TrimPrefix(j.Source, "satchel:credit:wolo-1:"), ":0")) {
					return bad()
				}
			case "claim_return_credit":
				if !reviewerUnsignedDecimal(j.ClaimReturn, false, math.MaxInt64) || j.Receipt != "" || !reviewerUnsignedDecimal(strings.TrimPrefix(j.Source, "satchel:return:claim:"), false, math.MaxInt32) || !strings.HasPrefix(j.Source, "satchel:return:claim:") {
					return bad()
				}
			default:
				return bad()
			}
		}
		for i, text := range []string{j.Available, j.Reserved, j.Committed, j.Withdrawing} {
			n, ok := new(big.Int).SetString(text, 10)
			if !ok || n.String() != text || new(big.Int).Abs(new(big.Int).Set(n)).Cmp(big.NewInt(math.MaxInt64)) > 0 {
				return bad()
			}
			totals[i].Add(totals[i], n)
			if totals[i].Sign() < 0 || totals[i].Cmp(big.NewInt(math.MaxInt64)) > 0 {
				return bad()
			}
		}
	}
	if len(expected) != 0 {
		return bad()
	}
	for i, want := range []string{rows.Available, rows.Reserved, rows.Committed, rows.Withdrawing} {
		if totals[i].String() != want {
			return bad()
		}
	}
	global, err := ReviewerOwnerLedgerCheckpointDigest(ReviewerFinanceObservation{ledger: rows.Global})
	if err != nil {
		return bad()
	}
	partition := hashJSON([]any{"aoe2war/satchel/owner-principal-partition/v1", rows, global, reviewerFingerprint(proposed), native.digest, native.policy})
	return VerifiedReviewerPrincipalPartition{valid: true, operation: proposed.OperationID, owner: proposed.OwnerID, principal: proposed.AmountUWolo, proposedFingerprint: reviewerFingerprint(proposed), partitionDigest: partition, ownerLedgerDigest: global, custodyJournalDigest: native.digest, ledgerVersion: rows.Version, observed: now}, nil
}

func principalTxHash(hash string) bool { return nonzeroDigest(hash) && hash == strings.ToUpper(hash) }
func principalTerminalMatches(effect reviewerPrincipalEffect, posted bool, hash, height string) bool {
	if effect.Status == "CONFIRMED" {
		return posted && effect.TxHash == hash && effect.Height > 0 && (height == "" || strconv.FormatInt(effect.Height, 10) == height)
	}
	// FAILED/REFUSED do not discharge principal. The original HD hold persists.
	return !posted && (effect.Status == "FAILED" || effect.Status == "REFUSED")
}
func chainStrictPrincipalJSON(raw string, target any) error {
	if len(raw) == 0 || len(raw) > 16384 {
		return ErrReviewerHeld
	}
	// Duplicate-key and unknown-field rejection are both required for mandate identity.
	if _, err := reviewerStrictJSON([]byte(raw)); err != nil {
		return ErrReviewerHeld
	}
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(target) != nil {
		return ErrReviewerHeld
	}
	return nil
}

var _ ReviewerPrincipalJournalReader = (*Engine)(nil)
