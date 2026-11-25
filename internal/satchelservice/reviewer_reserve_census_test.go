package satchelservice

// These tests use isolated SDK validators and TEST-only financial reviewers.
// The optional PostgreSQL test exercises a real independent read-only role;
// controlled original/owner/Watcher adapters do not certify mainnet authority.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"
)

type censusCustodyTestReader struct {
	engine *Engine
	reads  int
	after  func(int, *ReviewerCustodyFeeCheckpoint)
}

func (r *censusCustodyTestReader) ReadReviewerCustodyFees(ctx context.Context, ids []string) (ReviewerCustodyFeeCheckpoint, error) {
	if ctx == nil || ctx.Err() != nil {
		return ReviewerCustodyFeeCheckpoint{}, ErrReviewerHeld
	}
	cp, err := r.engine.ReviewerFeeCheckpoint(ids)
	r.reads++
	if r.after != nil {
		r.after(r.reads, &cp)
	}
	return cp, err
}

type censusCoverageTestReader struct {
	prepare func(context.Context) ([]byte, error)
	raw     []byte
	reads   int
	after   func(int, []byte) ([]byte, error)
}

func (r *censusCoverageTestReader) ReadReviewerReserveCoverage(ctx context.Context) ([]byte, error) {
	r.reads++
	if r.raw == nil {
		var err error
		r.raw, err = r.prepare(ctx)
		if err != nil {
			return nil, err
		}
	}
	raw := append([]byte(nil), r.raw...)
	if r.after != nil {
		return r.after(r.reads, raw)
	}
	return raw, nil
}

func censusFixtureConfig(t *testing.T, f *custodyAuthorityFixture) ReviewerReserveCensusConfig {
	t.Helper()
	key := func(value string) ed25519.PublicKey {
		decoded, err := hex.DecodeString(value)
		if err != nil {
			t.Fatal(err)
		}
		return ed25519.PublicKey(decoded)
	}
	return ReviewerReserveCensusConfig{Authority: ReserveReviewAuthority{
		AccountingReviewerKey: f.accounting.Public().(ed25519.PublicKey), CustodyReviewerKey: f.custody.Public().(ed25519.PublicKey),
		ExecutionAuthorityKey: key(f.config.ActivationAuthorityKeyHex), WagerApprovalKey: key(f.config.WagerApprovalKeyHex), WithdrawalApprovalKey: key(f.config.WithdrawalApprovalKeyHex),
		ExpectedVault: f.config.Vault, ExpectedBuildSHA256: f.review.BuildSHA256, ExpectedConfigSHA256: f.review.ConfigSHA256, ExpectedPermitSHA256: f.review.PermitSHA256},
		FeeSources: ReviewerFeeMergeAuthority{Vault: f.config.Vault, CustodyPolicyDigest: hashJSON(f.engine.policy), IssuerPolicyDigest: hashJSON(f.engine.policy), WagerApprovalKey: key(f.config.WagerApprovalKeyHex)},
		FeeUWolo:   f.config.FeesUWolo, MinimumGasReserveUWolo: "10000", MinimumUnencumberedUWolo: "10000"}
}

func censusFixtureOriginal(f *custodyAuthorityFixture) WagerReservation {
	original := *f.request.Reservation
	original.Signature, original.IssuedAt, original.ExpiresAt = "", 0, 0
	return original
}

func censusFixtureBundle(t *testing.T, f *custodyAuthorityFixture, proposed WagerReservation, observation ReviewerFinanceObservation, issued ReviewerIssuedFeeCheckpoint, custody ReviewerCustodyFeeCheckpoint, fees []ReviewerPendingFee) ReviewerReserveCensusBundle {
	t.Helper()
	owner, err := observation.KnownOwnerLiabilitiesUWolo()
	if err != nil {
		t.Fatal(err)
	}
	ownerDigest, err := ReviewerOwnerLedgerCheckpointDigest(observation)
	if err != nil {
		t.Fatal(err)
	}
	body := ReviewerReserveCensusBody{Protocol: 1, Scope: reviewerReserveCensusScope, Vault: f.config.Vault, OperationID: proposed.OperationID,
		ProposedFingerprint: reviewerFingerprint(proposed), BookedPrincipalUWolo: proposed.AmountUWolo, OwnerLedgerSHA256: ownerDigest,
		CustodyJournalSHA256: custody.JournalDigest, IssuerJournalSHA256: issued.JournalDigest, Producers: []ReviewerReserveProducer{}, NonOverlap: []ReviewerReserveNonOverlap{}}
	required := append([]string{}, reviewerRequiredReserveProducers...)
	sort.Strings(required)
	for _, id := range required {
		producer := ReviewerReserveProducer{ProducerID: id, CheckpointSHA256: hashJSON([]any{"controlled-test-producer-only", id}),
			Obligations: []ReviewerReserveObligation{}, PendingFees: []ReviewerPendingFee{}}
		switch id {
		case reviewerOwnerLedgerProducer:
			producer.CheckpointSHA256 = ownerDigest
			producer.Obligations = []ReviewerReserveObligation{{EconomicKey: "vault-owner-liabilities", Kind: "confirmed", AmountUWolo: owner}}
		case reviewerPendingFeesProducer:
			producer.CheckpointSHA256 = ReviewerPendingFeeCheckpointDigest(issued, custody, fees)
			producer.PendingFees = append([]ReviewerPendingFee{}, fees...)
		case "hd_manual_and_founder_obligations":
			producer.Obligations = []ReviewerReserveObligation{{EconomicKey: "fixture-unknown-obligation", Kind: "unknown", AmountUWolo: "1000000"}}
		}
		for _, obligation := range producer.Obligations {
			body.NonOverlap = append(body.NonOverlap, ReviewerReserveNonOverlap{EconomicKey: obligation.EconomicKey, ProducerID: id})
		}
		for _, fee := range producer.PendingFees {
			body.NonOverlap = append(body.NonOverlap, ReviewerReserveNonOverlap{EconomicKey: "fee:" + fee.OperationID, ProducerID: id})
		}
		body.Producers = append(body.Producers, producer)
	}
	sort.Slice(body.NonOverlap, func(i, j int) bool { return body.NonOverlap[i].EconomicKey < body.NonOverlap[j].EconomicKey })
	review := f.review
	review.StateHeight, review.CommitBlockHash, review.ObservedBankUWolo = observation.bank.Height(), observation.bank.BlockHash(), observation.bank.BalanceUWolo()
	review.ConfirmedLiabilitiesUWolo, review.UncertainMaxLiabilitiesUWolo = owner, "1000000"
	review.JournalSnapshotSHA256 = custody.JournalDigest
	bundle := ReviewerReserveCensusBundle{Version: 1, Review: review, Body: body}
	censusSignFixtureBundle(f, &bundle)
	return bundle
}

func censusSignFixtureBundle(f *custodyAuthorityFixture, bundle *ReviewerReserveCensusBundle) {
	bundle.Review.LiabilityInventorySHA256 = ReviewerReserveCensusBodyDigest(bundle.Body)
	bundle.Review.NonOverlapWitnessSHA256 = ReviewerReserveNonOverlapDigest(bundle.Body.NonOverlap)
	signReview(&bundle.Review, f.accounting, f.custody)
}

func censusMutateFixtureBundle(t *testing.T, f *custodyAuthorityFixture, bundle *ReviewerReserveCensusBundle, name string) {
	t.Helper()
	switch name {
	case "wrong_root":
		bundle.Review.CommitBlockHash = strings.Repeat("c", 64)
	case "wrong_height":
		bundle.Review.StateHeight++
	case "gas":
		bundle.Review.GasReserveUWolo = "2499"
	case "floor":
		bundle.Review.UnencumberedMinimumUWolo = "9999"
	case "zero_unknown":
		bundle.Review.UncertainMaxLiabilitiesUWolo = "0"
		for i := range bundle.Body.Producers {
			if bundle.Body.Producers[i].ProducerID == "hd_manual_and_founder_obligations" {
				bundle.Body.Producers[i].Obligations[0].AmountUWolo = "0"
			}
		}
	case "missing_producer":
		bundle.Body.Producers = bundle.Body.Producers[1:]
	case "missing_nonoverlap":
		bundle.Body.NonOverlap = bundle.Body.NonOverlap[1:]
	case "unassigned_nonoverlap":
		// Equal list lengths cannot prove an economic key was assigned. An
		// absent map entry's zero value must not match an empty producer ID.
		bundle.Body.NonOverlap[0] = ReviewerReserveNonOverlap{EconomicKey: "unassigned-economic-key", ProducerID: ""}
		sort.Slice(bundle.Body.NonOverlap, func(i, j int) bool {
			return bundle.Body.NonOverlap[i].EconomicKey < bundle.Body.NonOverlap[j].EconomicKey
		})
	case "duplicate_obligation":
		bundle.Body.Producers[0].Obligations = []ReviewerReserveObligation{{EconomicKey: "vault-owner-liabilities", Kind: "confirmed", AmountUWolo: "100000000"}}
	case "duplicate_fee":
		fee := ReviewerPendingFee{OperationID: "satchel:ticket:8", Stage: "uncertain", FeeUWolo: "1"}
		bundle.Body.Producers[0].PendingFees = []ReviewerPendingFee{fee}
		bundle.Body.Producers[1].PendingFees = []ReviewerPendingFee{fee}
	case "owner_understated":
		bundle.Review.ConfirmedLiabilitiesUWolo = "1"
		for i := range bundle.Body.Producers {
			if bundle.Body.Producers[i].ProducerID == reviewerOwnerLedgerProducer {
				bundle.Body.Producers[i].Obligations[0].AmountUWolo = "1"
			}
		}
	case "booked_principal":
		bundle.Body.BookedPrincipalUWolo = "1"
	case "owner_digest":
		bundle.Body.OwnerLedgerSHA256 = strings.Repeat("c", 64)
	case "issuer_digest":
		bundle.Body.IssuerJournalSHA256 = strings.Repeat("c", 64)
	case "custody_digest":
		bundle.Body.CustodyJournalSHA256 = strings.Repeat("c", 64)
	case "stale_review":
		expired := f.review.IssuedAt - 1
		bundle.Review.IssuedAt, bundle.Review.ExpiresAt = expired-60, expired
	case "future_review":
		bundle.Review.IssuedAt = time.Now().Unix() + 10
	case "uncovered":
		bundle.Review.AllObligationsCovered = false
	case "invalid_amount":
		bundle.Body.Producers[0].Obligations = []ReviewerReserveObligation{{EconomicKey: "test-invalid", Kind: "confirmed", AmountUWolo: "01"}}
	}
	censusSignFixtureBundle(f, bundle)
	if name == "wrong_key" {
		bundle.Review.AccountingReviewerSignature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestApprovalKey(), ReserveReviewMessage(bundle.Review)))
	}
}

func TestReviewerReserveCensusNativeProofValidatorAndCoverageFailures(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	proposed := censusFixtureOriginal(f)
	issuer, err := OpenReviewerIssuer(filepath.Join(t.TempDir(), "census-issuer.db"), &fakeReviewerEvidence{original: proposed}, engineTestWagerApprovalKey(), f.engine.policy)
	if err != nil {
		t.Fatal(err)
	}
	defer issuer.Close()
	issued, err := issuer.FeeCheckpoint()
	if err != nil {
		t.Fatal(err)
	}
	custody, err := f.engine.ReviewerFeeCheckpoint([]string{proposed.OperationID})
	if err != nil {
		t.Fatal(err)
	}
	bank, _, err := f.reader.ReadCurrentBankProof(t.Context(), f.config.Vault)
	if err != nil {
		t.Fatal(err)
	}
	// Only the ledger struct is controlled here. This mandatory test proves the
	// actual opaque SDK/Comet bank and signed coverage validator, not PG access.
	observation := ReviewerFinanceObservation{bank: bank, ledger: reviewerOwnerLedger{owners: "1", available: "93000000", reserved: "7000000", committed: "0", withdrawing: "0", revisions: "2", entries: "2", observedAt: time.Now()}}
	cfg := censusFixtureConfig(t, f)
	source := &ReviewerReserveCensusSource{config: cfg, required: append([]string{}, reviewerRequiredReserveProducers...)}
	sort.Strings(source.required)
	fees, err := MergeReviewerPendingFees(proposed, issued, custody, cfg.FeeSources, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	original := censusFixtureBundle(t, f, proposed, observation, issued, custody, fees)
	now := time.Now()
	positive, err := source.verifyCoverage(original, proposed, observation, issued, custody, fees, now)
	if err != nil || !positive.PendingOperationsComplete || positive.AllOwnerLiabilitiesUWolo != "101000000" {
		t.Fatal("actual native positive coverage rejected", positive, err)
	}
	budget, err := AssessReviewerFeeBudget(positive, proposed)
	if err != nil || budget.Status != "BUDGET_SUFFICIENT_NONAUTHORIZING" || budget.SpendingAuthorized || budget.BankAuthenticated || budget.OwnerLedgerAuthenticated {
		t.Fatal("validator created execution/credit authority", budget, err)
	}
	for _, name := range []string{"wrong_root", "wrong_height", "wrong_key", "gas", "floor", "zero_unknown", "missing_producer", "missing_nonoverlap", "unassigned_nonoverlap", "duplicate_obligation", "duplicate_fee", "owner_understated", "booked_principal", "owner_digest", "issuer_digest", "custody_digest", "stale_review", "future_review", "uncovered", "invalid_amount"} {
		t.Run(name, func(t *testing.T) {
			raw, _ := json.Marshal(original)
			var bundle ReviewerReserveCensusBundle
			if err := json.Unmarshal(raw, &bundle); err != nil {
				t.Fatal(err)
			}
			censusMutateFixtureBundle(t, f, &bundle, name)
			got, err := source.verifyCoverage(bundle, proposed, observation, issued, custody, fees, now)
			if !errors.Is(err, ErrReviewerHeld) || !reflect.DeepEqual(got, ReviewerFeeCensus{}) {
				t.Fatal("untrusted coverage returned partial census", got, err)
			}
		})
	}
	if f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
		t.Fatal("reserve validation signed or transmitted native funds")
	}
}

func TestReviewerReserveCensusBundleDecoderStrictAndBounded(t *testing.T) {
	for _, raw := range [][]byte{nil, []byte(`{"version":1,"Version":1}`), []byte(`{"version":1,"version":1}`), []byte(`{"version":1,"key":"caller"}`), []byte(`{"version":2}`), []byte(`{} {}`), bytes.Repeat([]byte(" "), reviewerReserveCensusMaxBytes+1), []byte{'{', '"', 0xff, '"', ':', '1', '}'}} {
		if _, err := decodeReviewerReserveBundle(raw); !errors.Is(err, ErrReviewerHeld) {
			t.Fatal("invalid coverage encoding accepted", err)
		}
	}
}

func TestReviewerFinancePostgresReserveCensusSignsOnlyWithActualIndependentSources(t *testing.T) {
	dsn := os.Getenv("SATCHEL_REVIEWER_TEST_PG_DSN")
	if dsn == "" {
		t.Skip("isolated PostgreSQL fixture not configured")
	}
	u, err := url.Parse(dsn)
	if err != nil || (u.Hostname() != "127.0.0.1" && u.Hostname() != "localhost") || u.Path != "/satchel_reviewer_test" {
		t.Fatal("fixture requires explicit disposable localhost /satchel_reviewer_test")
	}
	admin, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = admin.Close() })
	const role = "satchel_reviewer_reserve_it"
	fixture := `CREATE ROLE satchel_reviewer_reserve_it LOGIN PASSWORD 'isolated-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE public.war_satchel_funded_balances(owner_user_id integer PRIMARY KEY,available_uwolo bigint NOT NULL,reserved_uwolo bigint NOT NULL,committed_uwolo bigint NOT NULL,withdrawal_pending_uwolo bigint NOT NULL,version bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_journal(owner_user_id integer NOT NULL,delta_available_uwolo bigint NOT NULL,delta_reserved_uwolo bigint NOT NULL,delta_committed_uwolo bigint NOT NULL,delta_withdrawal_pending_uwolo bigint NOT NULL);
CREATE TABLE public.war_satchel_funded_receipts(vault_address text NOT NULL,chain_id text NOT NULL,canonical_height bigint NOT NULL,amount_uwolo bigint NOT NULL);
GRANT SELECT ON public.war_satchel_funded_balances,public.war_satchel_funded_journal,public.war_satchel_funded_receipts TO satchel_reviewer_reserve_it;
INSERT INTO public.war_satchel_funded_balances VALUES(1,93000000,7000000,0,0,2);
INSERT INTO public.war_satchel_funded_journal VALUES(1,100000000,0,0,0),(1,-7000000,7000000,0,0);`
	if _, err := admin.ExecContext(t.Context(), fixture); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(`DROP TABLE public.war_satchel_funded_receipts,public.war_satchel_funded_journal,public.war_satchel_funded_balances; DROP ROLE satchel_reviewer_reserve_it`)
	})
	u.User = url.UserPassword(role, "isolated-test-only")
	db, err := sql.Open("postgres", u.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	f := newCustodyAuthorityFixture(t)
	proposed, cfg := censusFixtureOriginal(f), censusFixtureConfig(t, f)
	for _, name := range []string{"positive", "wrong_root", "wrong_key", "gas", "zero_unknown", "duplicate_obligation", "missing_producer", "missing_nonoverlap", "unassigned_nonoverlap", "owner_understated", "stale_review", "future_review", "custody_stale", "custody_future", "custody_wrong_key", "review_revoked_during_read", "body_changed_during_read", "custody_changed_during_read", "ledger_changed_during_read", "wrong_pg_role", "proposed_owner_changed"} {
		t.Run(name, func(t *testing.T) {
			connection := db
			if name == "wrong_pg_role" {
				connection = admin
			}
			pg, err := NewReviewerReadOnlyPGSource(connection, role, cfg.FeeUWolo, f.config.Vault, f.config.BettingEscrow)
			if err != nil {
				t.Fatal(err)
			}
			original := proposed
			if name == "proposed_owner_changed" {
				original.OwnerID = "different-owner"
			}
			// These owner/Watcher adapters are explicitly synthetic test roots;
			// bank, three-table PG role/query and fee checkpoints remain actual.
			base, err := NewReviewerFinanceSource(&fakeReviewerEvidence{original: original}, pg, f.reader)
			if err != nil {
				t.Fatal(err)
			}
			custodyReader := &censusCustodyTestReader{engine: f.engine}
			coverage := &censusCoverageTestReader{}
			coverage.prepare = func(ctx context.Context) ([]byte, error) {
				issued, err := reviewerIssuedFeesFromContext(ctx)
				if err != nil {
					return nil, err
				}
				custody, err := f.engine.ReviewerFeeCheckpoint([]string{proposed.OperationID})
				if err != nil {
					return nil, err
				}
				bank, _, err := f.reader.ReadCurrentBankProof(ctx, f.config.Vault)
				if err != nil {
					return nil, err
				}
				row, err := pg.readOwnerLedger(ctx)
				if err != nil {
					return nil, err
				}
				observation := ReviewerFinanceObservation{bank: bank, ledger: row}
				fees, err := MergeReviewerPendingFees(proposed, issued, custody, cfg.FeeSources, time.Now())
				if err != nil {
					return nil, err
				}
				bundle := censusFixtureBundle(t, f, proposed, observation, issued, custody, fees)
				censusMutateFixtureBundle(t, f, &bundle, name)
				return json.Marshal(bundle)
			}
			coverage.after = func(read int, raw []byte) ([]byte, error) {
				if read == 2 && name == "review_revoked_during_read" {
					return nil, ErrReviewerHeld
				}
				if read == 2 && name == "body_changed_during_read" {
					return append(raw, ' '), nil
				}
				return raw, nil
			}
			custodyReader.after = func(read int, cp *ReviewerCustodyFeeCheckpoint) {
				if name == "custody_stale" {
					cp.ObservedAtMS = time.Now().Add(-reviewerFeeCheckpointMaxAge - time.Second).UnixMilli()
				}
				if name == "custody_future" {
					cp.ObservedAtMS = time.Now().Add(time.Second).UnixMilli()
				}
				if name == "custody_wrong_key" {
					cp.WagerApprovalKeyFingerprint = strings.Repeat("c", 64)
				}
				if read == 2 && name == "custody_changed_during_read" {
					cp.JournalDigest = strings.Repeat("c", 64)
				}
				if read == 2 && name == "ledger_changed_during_read" {
					if _, err := admin.ExecContext(t.Context(), `INSERT INTO public.war_satchel_funded_journal VALUES(1,1,0,0,0); UPDATE public.war_satchel_funded_balances SET available_uwolo=available_uwolo+1,version=version+1 WHERE owner_user_id=1`); err != nil {
						t.Fatal(err)
					}
				}
			}
			if name == "ledger_changed_during_read" {
				defer func() {
					_, _ = admin.Exec(`DELETE FROM public.war_satchel_funded_journal WHERE delta_available_uwolo=1; UPDATE public.war_satchel_funded_balances SET available_uwolo=93000000,version=2 WHERE owner_user_id=1`)
				}()
			}
			source, err := NewReviewerReserveCensusSource(base, custodyReader, coverage, cfg)
			if err != nil {
				t.Fatal(err)
			}
			issuer, err := OpenReviewerIssuer(filepath.Join(t.TempDir(), "reviewer.db"), source, engineTestWagerApprovalKey(), f.engine.policy)
			if err != nil {
				t.Fatal(err)
			}
			defer issuer.Close()
			result := issuer.ReviewOne(t.Context(), proposed.OperationID)
			if name == "positive" {
				if result.Status != "SIGNED" || result.Approval == nil || f.engine.policy.VerifyWager(TransferRequest{OperationID: proposed.OperationID, Kind: "wager", ChainID: "wolo-1", Denom: "uwolo", OwnerID: proposed.OwnerID, Sender: proposed.Vault, Recipient: proposed.Recipient, AmountUWolo: proposed.AmountUWolo, Memo: proposed.Memo, Reservation: result.Approval}) != nil {
					t.Fatal("genuine SDK+PG+dual review did not produce exact signed approval", result)
				}
				if custodyReader.reads != 4 || coverage.reads != 4 {
					t.Fatal("actual issuer did not independently recheck both fee censuses", custodyReader.reads, coverage.reads)
				}
				bank, _, err := f.reader.ReadCurrentBankProof(t.Context(), f.config.Vault)
				if err != nil || !bank.CurrentAt(time.Now()) || bank.Height()+1 != bank.CommitHeight() || bank.CommitHeight() != f.chain.head {
					t.Fatal("positive approval did not use actual current H/H+1 native bank evidence", err)
				}
				issued, err := issuer.FeeCheckpoint()
				if err != nil || len(issued.PendingFees) != 1 || issued.PendingFees[0].FeeUWolo != proposed.FeeUWolo || issued.EntryFingerprints[proposed.OperationID] != reviewerFingerprint(proposed) {
					t.Fatal("actual signed approval fee did not enter durable issuer history", issued, err)
				}
			} else if result.Status != "PENDING" || result.Approval != nil {
				t.Fatal("untrusted/revoked/changed source issued approval", name, result)
			}
			if f.SDKSigns.Load() != 0 || f.chain.broadcasts != 0 {
				t.Fatal("reviewer caused custody signing/broadcast")
			}
		})
	}
}
