package cmd

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

const (
	testBetCustodyAddress = "wolo1betcustody000000000000000000000000000000"
	testBetUserWallet     = "wolo1betuser000000000000000000000000000000000"
	testBetOperatorWallet = "wolo1betoperator00000000000000000000000000000"
)

func newTestBetCustodyConfig(t *testing.T, balances map[string]string, txs map[string]mockSettlementTx) settlementConfig {
	t.Helper()
	cfg := newTestSettlementConfigWithTxs(
		t,
		"wolo1payout0000000000000000000000000000000000",
		balances,
		txs,
		nil,
	)
	cfg.BetCustodyKeyName = "bet-custody"
	cfg.BetCustodyAddress = testBetCustodyAddress
	cfg.BetCustodyStateDir = t.TempDir()
	cfg.BetCustodyMaxBalanceUWolo = betCustodyDefaultMaxCreditedBalanceUWolo
	cfg.AuthToken = "test-secret"
	return cfg
}

func createAndFundBetCustodyAccount(
	t *testing.T,
	cfg settlementConfig,
	txs map[string]mockSettlementTx,
	requestID string,
	depositID string,
	wallet string,
	amount string,
	kind string,
	txHash string,
) string {
	t.Helper()
	accountResponse, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{
		RequestID: requestID,
		Kind:      kind,
	})
	if err != nil || !accountResponse.OK {
		t.Fatalf("create account: response=%+v err=%v", accountResponse, err)
	}
	intent, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID:   requestID + ":deposit",
		DepositID:   depositID,
		AccountID:   accountResponse.AccountID,
		Sender:      wallet,
		AmountUWolo: amount,
	})
	if err != nil || !intent.OK {
		t.Fatalf("create deposit intent: response=%+v err=%v", intent, err)
	}
	txs[txHash] = mockSettlementTx{
		Hash:        txHash,
		Sender:      wallet,
		Recipient:   testBetCustodyAddress,
		AmountUWolo: amount,
		Memo:        intent.Memo,
	}
	credit, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{
		DepositID: depositID,
		TxHash:    txHash,
	})
	if err != nil || !credit.OK {
		t.Fatalf("credit deposit: response=%+v err=%v", credit, err)
	}
	return accountResponse.AccountID
}

func TestBetCustodyAccountAndDepositIdempotency(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "20000000000"}, txs)

	first, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{
		RequestID: "account-open-1",
	})
	if err != nil || !first.OK {
		t.Fatalf("create account: %+v err=%v", first, err)
	}
	replayed, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{
		RequestID: "account-open-1",
	})
	if err != nil || !replayed.OK || !replayed.IdempotentReplay || replayed.AccountID != first.AccountID {
		t.Fatalf("expected idempotent account replay: %+v err=%v", replayed, err)
	}

	intent, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID:   "deposit-intent-1",
		DepositID:   "deposit-1",
		AccountID:   first.AccountID,
		Sender:      testBetUserWallet,
		AmountUWolo: "1000000",
	})
	if err != nil || !intent.OK {
		t.Fatalf("create deposit intent: %+v err=%v", intent, err)
	}
	if want := canonicalBetCustodyDepositMemo(first.AccountID, "deposit-1", 1_000_000); intent.Memo != want {
		t.Fatalf("memo mismatch: got %q want %q", intent.Memo, want)
	}

	txHash := strings.Repeat("A", 64)
	txs[txHash] = mockSettlementTx{
		Hash: txHash, Sender: testBetUserWallet, Recipient: testBetCustodyAddress,
		AmountUWolo: "1000000", Memo: intent.Memo,
	}
	credit, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{
		DepositID: "deposit-1", TxHash: txHash,
	})
	if err != nil || !credit.OK || credit.AvailableUWolo != "1000000" {
		t.Fatalf("credit deposit: %+v err=%v", credit, err)
	}
	replayedCredit, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{
		DepositID: "deposit-1", TxHash: txHash,
	})
	if err != nil || !replayedCredit.OK || !replayedCredit.IdempotentReplay {
		t.Fatalf("expected idempotent deposit credit: %+v err=%v", replayedCredit, err)
	}
	account, err := cfg.getBetCustodyAccount(first.AccountID)
	if err != nil || !account.OK || account.SourceWallet != testBetUserWallet || account.AvailableUWolo != "1000000" {
		t.Fatalf("unexpected bound account: %+v err=%v", account, err)
	}
}

func TestBetCustodyDepositRejectsMemoWalletDuplicateTxAndBalanceCap(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "50000000000"}, txs)
	account, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{RequestID: "account-cap"})
	if err != nil || !account.OK {
		t.Fatalf("create account: %+v err=%v", account, err)
	}

	intent, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID: "intent-cap-1", DepositID: "dep-cap-1", AccountID: account.AccountID,
		Sender: testBetUserWallet, AmountUWolo: "9000000000",
	})
	if err != nil || !intent.OK {
		t.Fatalf("create first intent: %+v err=%v", intent, err)
	}
	txHash := strings.Repeat("B", 64)
	txs[txHash] = mockSettlementTx{
		Hash: txHash, Sender: testBetUserWallet, Recipient: testBetCustodyAddress,
		AmountUWolo: "9000000000", Memo: intent.Memo + "&evil=1",
	}
	badMemo, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{DepositID: "dep-cap-1", TxHash: txHash})
	if err != nil || badMemo.FailureCode != "INVALID_DEPOSIT_MEMO" {
		t.Fatalf("expected canonical memo refusal: %+v err=%v", badMemo, err)
	}
	txs[txHash] = mockSettlementTx{
		Hash: txHash, Sender: testBetUserWallet, Recipient: testBetCustodyAddress,
		AmountUWolo: "9000000000", Memo: intent.Memo,
	}
	good, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{DepositID: "dep-cap-1", TxHash: txHash})
	if err != nil || !good.OK {
		t.Fatalf("credit first deposit: %+v err=%v", good, err)
	}

	second, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID: "intent-cap-2", DepositID: "dep-cap-2", AccountID: account.AccountID,
		Sender: testBetUserWallet, AmountUWolo: "1000000001",
	})
	if err != nil || second.FailureCode != "ACCOUNT_BALANCE_CAP_EXCEEDED" {
		t.Fatalf("expected balance cap refusal: %+v err=%v", second, err)
	}

	wrongWallet, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID: "intent-wrong-wallet", DepositID: "dep-wrong-wallet", AccountID: account.AccountID,
		Sender: "wolo1anotherwallet00000000000000000000000000000", AmountUWolo: "1",
	})
	if err != nil || wrongWallet.FailureCode != "SOURCE_WALLET_MISMATCH" {
		t.Fatalf("expected wallet binding refusal: %+v err=%v", wrongWallet, err)
	}

	other, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{RequestID: "account-other"})
	if err != nil || !other.OK {
		t.Fatalf("create second account: %+v err=%v", other, err)
	}
	otherIntent, err := cfg.createBetCustodyDepositIntent(betCustodyDepositIntentRequest{
		RequestID: "other-intent", DepositID: "other-dep", AccountID: other.AccountID,
		Sender: testBetUserWallet, AmountUWolo: "1",
	})
	if err != nil || !otherIntent.OK {
		t.Fatalf("create other intent: %+v err=%v", otherIntent, err)
	}
	duplicateTx, err := cfg.creditBetCustodyDeposit(t.Context(), betCustodyDepositCreditRequest{
		DepositID: "other-dep", TxHash: txHash,
	})
	if err != nil {
		t.Fatalf("duplicate tx check error: %v", err)
	}
	if duplicateTx.OK {
		t.Fatalf("expected duplicate/mismatched tx refusal, got %+v", duplicateTx)
	}
}

func TestBetCustodyConcurrentReservationsConserveAvailableBalance(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "1000"}, txs)
	cfg.RequestTimeout = 2 * time.Second
	accountID := createAndFundBetCustodyAccount(
		t, cfg, txs, "account-race", "dep-race", testBetUserWallet, "1000", "user", strings.Repeat("C", 64),
	)

	request := func(id string) betCustodyReservationRequest {
		return betCustodyReservationRequest{
			RequestID: id, ReservationID: id, AccountID: accountID,
			GameIdentity: "game-race", PropositionHash: "prop-race",
			Legs: []betCustodyReservationLegRequest{{
				ID: id + "-winner", MarketID: "market-race", MarketType: "winner", Side: "left", AmountUWolo: "700",
			}},
		}
	}
	var wg sync.WaitGroup
	responses := make(chan betCustodyReservationResponse, 2)
	errorsCh := make(chan error, 2)
	for _, id := range []string{"reservation-race-a", "reservation-race-b"} {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			response, err := cfg.createBetCustodyReservation(request(id))
			responses <- response
			errorsCh <- err
		}(id)
	}
	wg.Wait()
	close(responses)
	close(errorsCh)
	successes := 0
	insufficient := 0
	for err := range errorsCh {
		if err != nil {
			t.Fatalf("concurrent reservation returned error: %v", err)
		}
	}
	for response := range responses {
		if response.OK {
			successes++
		}
		if response.FailureCode == "INSUFFICIENT_AVAILABLE_BALANCE" {
			insufficient++
		}
	}
	if successes != 1 || insufficient != 1 {
		t.Fatalf("expected one success and one balance refusal, got successes=%d insufficient=%d", successes, insufficient)
	}
	account, err := cfg.getBetCustodyAccount(accountID)
	if err != nil || account.AvailableUWolo != "300" || account.ReservedUWolo != "700" {
		t.Fatalf("unexpected account after concurrent reservations: %+v err=%v", account, err)
	}
}

func TestBetCustodyReleaseAndConservingSettlementWithOperatorAllocation(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "5000"}, txs)
	userID := createAndFundBetCustodyAccount(
		t, cfg, txs, "account-user-settle", "dep-user-settle", testBetUserWallet, "1000", "user", strings.Repeat("D", 64),
	)
	operatorID := createAndFundBetCustodyAccount(
		t, cfg, txs, "account-operator", "dep-operator", testBetOperatorWallet, "1000", "operator", strings.Repeat("E", 64),
	)
	reservation, err := cfg.createBetCustodyReservation(betCustodyReservationRequest{
		RequestID: "reserve-two-leg", ReservationID: "reserve-two-leg", AccountID: userID,
		GameIdentity: "game-42", PropositionHash: "prop-42",
		Legs: []betCustodyReservationLegRequest{
			{ID: "winner-leg", MarketID: "winner-42", MarketType: "winner", Side: "left", AmountUWolo: "400"},
			{ID: "desync-leg", MarketID: "desync-42", MarketType: "desync", Side: "no", AmountUWolo: "200"},
		},
	})
	if err != nil || !reservation.OK {
		t.Fatalf("create reservation: %+v err=%v", reservation, err)
	}

	released, err := cfg.releaseBetCustodyReservationLeg(betCustodyReleaseRequest{
		RequestID: "release-desync", ReservationID: "reserve-two-leg", LegID: "desync-leg",
	})
	if err != nil || !released.OK || released.ReservedUWolo != "400" || released.AvailableUWolo != "600" {
		t.Fatalf("release desync: %+v err=%v", released, err)
	}

	mismatch, err := cfg.executeBetCustodySettlementRun(betCustodySettlementRunRequest{
		SettlementRunID: "settle-bad-prop", PropositionHash: "wrong-prop",
		Debits:  []betCustodySettlementDebitRequest{{ReservationID: "reserve-two-leg", LegID: "winner-leg"}},
		Credits: []betCustodySettlementCreditRequest{{AccountID: userID, AmountUWolo: "400", Kind: "winner_return"}},
	}, true)
	if err != nil || mismatch.FailureCode != "PROPOSITION_MISMATCH" {
		t.Fatalf("expected proposition mismatch: %+v err=%v", mismatch, err)
	}

	runRequest := betCustodySettlementRunRequest{
		SettlementRunID: "settle-42", PropositionHash: "prop-42",
		Debits:              []betCustodySettlementDebitRequest{{ReservationID: "reserve-two-leg", LegID: "winner-leg"}},
		OperatorAllocations: []betCustodyOperatorAllocationRequest{{AccountID: operatorID, AmountUWolo: "100"}},
		Credits:             []betCustodySettlementCreditRequest{{AccountID: userID, AmountUWolo: "500", Kind: "winner_payout"}},
	}
	run, err := cfg.executeBetCustodySettlementRun(runRequest, false)
	if err != nil || !run.OK || run.DebitedUWolo != "400" || run.OperatorUWolo != "100" || run.CreditedUWolo != "500" {
		t.Fatalf("execute settlement: %+v err=%v", run, err)
	}
	replay, err := cfg.executeBetCustodySettlementRun(runRequest, false)
	if err != nil || !replay.OK || !replay.IdempotentReplay {
		t.Fatalf("settlement idempotent replay: %+v err=%v", replay, err)
	}
	secondConsume, err := cfg.executeBetCustodySettlementRun(betCustodySettlementRunRequest{
		SettlementRunID: "settle-42-again", PropositionHash: "prop-42",
		Debits:  []betCustodySettlementDebitRequest{{ReservationID: "reserve-two-leg", LegID: "winner-leg"}},
		Credits: []betCustodySettlementCreditRequest{{AccountID: userID, AmountUWolo: "400", Kind: "duplicate"}},
	}, false)
	if err != nil || secondConsume.FailureCode != "RESERVATION_LEG_NOT_RESERVED" {
		t.Fatalf("expected double-consume refusal: %+v err=%v", secondConsume, err)
	}

	user, _ := cfg.getBetCustodyAccount(userID)
	operator, _ := cfg.getBetCustodyAccount(operatorID)
	if user.AvailableUWolo != "1100" || user.ReservedUWolo != "0" {
		t.Fatalf("unexpected user settlement balance: %+v", user)
	}
	if operator.AvailableUWolo != "900" {
		t.Fatalf("unexpected operator balance: %+v", operator)
	}
	liabilities, err := cfg.getBetCustodyLiabilities()
	if err != nil || liabilities.UserLiabilityUWolo != "1100" || liabilities.OperatorCapitalUWolo != "900" || liabilities.TotalLedgerUWolo != "2000" {
		t.Fatalf("unexpected liabilities: %+v err=%v", liabilities, err)
	}
}

func TestBetCustodyJournalRecoveryAndCorruptionDetection(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "1000"}, txs)
	account, err := cfg.createBetCustodyAccount(betCustodyAccountRequest{RequestID: "account-recovery"})
	if err != nil || !account.OK {
		t.Fatalf("create account: %+v err=%v", account, err)
	}
	if err := os.Remove(cfg.betCustodySnapshotPath()); err != nil {
		t.Fatalf("remove snapshot: %v", err)
	}
	recovered, err := cfg.loadBetCustodyState()
	if err != nil || !recovered.Recovered || recovered.Snapshot.Accounts[account.AccountID].ID != account.AccountID {
		t.Fatalf("expected journal recovery: recovered=%+v err=%v", recovered, err)
	}

	journal, err := os.ReadFile(cfg.betCustodyJournalPath())
	if err != nil {
		t.Fatalf("read journal: %v", err)
	}
	tampered := bytes.Replace(journal, []byte(`"operation_type":"account_opened"`), []byte(`"operation_type":"account_tampered"`), 1)
	if bytes.Equal(tampered, journal) {
		t.Fatalf("expected journal fixture replacement")
	}
	if err := os.WriteFile(cfg.betCustodyJournalPath(), tampered, 0o600); err != nil {
		t.Fatalf("tamper journal: %v", err)
	}
	if _, err := cfg.loadBetCustodyState(); err == nil || !strings.Contains(err.Error(), "CUSTODY_JOURNAL_CORRUPT") {
		t.Fatalf("expected corruption refusal, got %v", err)
	}
}

func TestBetCustodyHTTPRequiresAuthAndUsesStringAmounts(t *testing.T) {
	t.Parallel()
	txs := map[string]mockSettlementTx{}
	cfg := newTestBetCustodyConfig(t, map[string]string{testBetCustodyAddress: "1000"}, txs)
	handler := cfg.newSettlementHTTPHandler()

	body := []byte(`{"request_id":"http-account","kind":"user"}`)
	unauthorized := httptest.NewRequest(http.MethodPost, "/settlement/v1/bet-custody/accounts", bytes.NewReader(body))
	unauthorized.Header.Set("content-type", "application/json")
	unauthorizedRecorder := httptest.NewRecorder()
	handler.ServeHTTP(unauthorizedRecorder, unauthorized)
	if unauthorizedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d body=%s", unauthorizedRecorder.Code, unauthorizedRecorder.Body.String())
	}

	request := httptest.NewRequest(http.MethodPost, "/settlement/v1/bet-custody/accounts", bytes.NewReader(body))
	request.Header.Set("Authorization", "Bearer test-secret")
	request.Header.Set("content-type", "application/json")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected account route success, got %d body=%s", recorder.Code, recorder.Body.String())
	}
	var decoded map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if _, ok := decoded["available_uwolo"].(string); !ok {
		t.Fatalf("available_uwolo must be a JSON string: %s", recorder.Body.String())
	}
	if _, ok := decoded["reserved_uwolo"].(string); !ok {
		t.Fatalf("reserved_uwolo must be a JSON string: %s", recorder.Body.String())
	}
}
