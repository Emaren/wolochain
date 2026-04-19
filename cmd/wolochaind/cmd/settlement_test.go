package cmd

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestNormalizeSettlementRequest(t *testing.T) {
	t.Parallel()

	request, err := normalizeSettlementRequest(settlementExecuteRequest{
		RequestID:  "payout:match-42:user-8",
		ToAddress:  "wolo1abcdefghijklmnopqrstuvwxyz0123456789abcd",
		AmountWolo: 7,
		Memo:       "  settled  ",
	})
	if err != nil {
		t.Fatalf("expected request to normalize, got error: %v", err)
	}

	if request.AmountUWolo != "7000000" {
		t.Fatalf("expected 7000000 uwolo, got %s", request.AmountUWolo)
	}
	if request.Memo != "settled" {
		t.Fatalf("expected trimmed memo, got %q", request.Memo)
	}
}

func TestNormalizeSettlementRequestRejectsConflictingAmounts(t *testing.T) {
	t.Parallel()

	_, err := normalizeSettlementRequest(settlementExecuteRequest{
		RequestID:   "payout:match-42:user-8",
		ToAddress:   "wolo1abcdefghijklmnopqrstuvwxyz0123456789abcd",
		AmountUWolo: "1000000",
		AmountWolo:  1,
	})
	if err == nil {
		t.Fatalf("expected conflicting amount fields to fail")
	}
}

func TestSplitCoinAmounts(t *testing.T) {
	t.Parallel()

	coins := splitCoinAmounts("1000000uwolo,250stake,7ufoo")
	if len(coins) != 3 {
		t.Fatalf("expected 3 coins, got %d", len(coins))
	}

	if coins[0].Amount != "1000000" || coins[0].Denom != "uwolo" {
		t.Fatalf("unexpected first coin: %+v", coins[0])
	}
}

func TestMatchSettlementTransfer(t *testing.T) {
	t.Parallel()

	transfers := []settlementTransfer{
		{Sender: "wolo1from", Recipient: "wolo1fee", Amount: "25000", Denom: "uwolo"},
		{Sender: "wolo1from", Recipient: "wolo1winner", Amount: "7000000", Denom: "uwolo"},
	}

	match, ok := matchSettlementTransfer(transfers, settlementLookupExpectations{
		Sender:      "wolo1from",
		Recipient:   "wolo1winner",
		AmountUWolo: "7000000",
	})
	if !ok || match == nil {
		t.Fatalf("expected a matching transfer")
	}

	if match.Recipient != "wolo1winner" {
		t.Fatalf("unexpected match: %+v", *match)
	}
}

func TestClassifySettlementExecError(t *testing.T) {
	t.Parallel()

	code, retryable := classifySettlementExecError("rpc error: code = Unknown desc = account sequence mismatch")
	if code != "SEQUENCE_MISMATCH" || !retryable {
		t.Fatalf("unexpected classification: code=%s retryable=%v", code, retryable)
	}
}

func TestExtractJSONPayload(t *testing.T) {
	t.Parallel()

	payload := extractJSONPayload([]byte("gas estimate: 62602\n{\"txhash\":\"ABC123\",\"code\":0}"))
	if string(payload) != "{\"txhash\":\"ABC123\",\"code\":0}" {
		t.Fatalf("unexpected payload: %s", string(payload))
	}
}

func TestExtractSettlementTransfersFallsBackToTxResponseEvents(t *testing.T) {
	t.Parallel()

	transfers := extractSettlementTransfers(restTxLookupResponse{
		TxResponse: struct {
			Height    string          "json:\"height\""
			TxHash    string          "json:\"txhash\""
			Code      uint32          "json:\"code\""
			Codespace string          "json:\"codespace\""
			RawLog    string          "json:\"raw_log\""
			Timestamp string          "json:\"timestamp\""
			Logs      []restTxLogItem "json:\"logs\""
			Events    []restTxEvent   "json:\"events\""
		}{
			Events: []restTxEvent{
				{
					Type: "transfer",
					Attributes: []restTxEventAttribute{
						{Key: "sender", Value: "wolo1from"},
						{Key: "recipient", Value: "wolo1to"},
						{Key: "amount", Value: "4000000uwolo"},
					},
				},
			},
		},
	})
	if len(transfers) != 1 {
		t.Fatalf("expected 1 transfer, got %d", len(transfers))
	}
	if transfers[0].Recipient != "wolo1to" || transfers[0].Amount != "4000000" {
		t.Fatalf("unexpected transfer: %+v", transfers[0])
	}
}

func TestSettlementCheckPayoutCapacity(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		MinPayoutBalanceUWolo: 200,
		FeeHeadroomUWolo:      50,
	}

	code, _, failed := cfg.checkPayoutCapacity(90, 100)
	if !failed || code != "PAYOUT_BALANCE_TOO_LOW" {
		t.Fatalf("expected low-balance refusal, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkPayoutCapacity(140, 100)
	if !failed || code != "PAYOUT_FEE_HEADROOM_TOO_LOW" {
		t.Fatalf("expected fee headroom refusal, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkPayoutCapacity(260, 100)
	if !failed || code != "PAYOUT_RESERVE_FLOOR_HIT" {
		t.Fatalf("expected reserve-floor refusal, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkPayoutCapacity(500, 100)
	if failed || code != "" {
		t.Fatalf("expected payout capacity to pass, got code=%s failed=%v", code, failed)
	}
}

func TestSettlementCheckPayoutCapacityBoundariesAndPrecedence(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		MinPayoutBalanceUWolo: 200,
		FeeHeadroomUWolo:      50,
	}

	code, _, failed := cfg.checkPayoutCapacity(149, 100)
	if !failed || code != "PAYOUT_FEE_HEADROOM_TOO_LOW" {
		t.Fatalf("expected fee-headroom precedence, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkPayoutCapacity(190, 100)
	if !failed || code != "PAYOUT_RESERVE_FLOOR_HIT" {
		t.Fatalf("expected reserve-floor refusal, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkPayoutCapacity(300, 100)
	if failed || code != "" {
		t.Fatalf("expected exact reserve-floor boundary to pass, got code=%s failed=%v", code, failed)
	}

	cfg.MinPayoutBalanceUWolo = 0
	code, _, failed = cfg.checkPayoutCapacity(150, 100)
	if failed || code != "" {
		t.Fatalf("expected exact fee-headroom boundary to pass, got code=%s failed=%v", code, failed)
	}
}

func TestSettlementCheckReserveHealth(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		MinPayoutBalanceUWolo: 200,
		FeeHeadroomUWolo:      50,
	}

	code, _, failed := cfg.checkReserveHealth(40)
	if !failed || code != "PAYOUT_FEE_HEADROOM_TOO_LOW" {
		t.Fatalf("expected fee-headroom health failure, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkReserveHealth(150)
	if !failed || code != "PAYOUT_RESERVE_FLOOR_HIT" {
		t.Fatalf("expected reserve-floor health failure, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkReserveHealth(300)
	if failed || code != "" {
		t.Fatalf("expected reserve health to pass, got code=%s failed=%v", code, failed)
	}
}

func TestSettlementCheckReserveHealthBoundaries(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		MinPayoutBalanceUWolo: 200,
		FeeHeadroomUWolo:      50,
	}

	code, _, failed := cfg.checkReserveHealth(50)
	if !failed || code != "PAYOUT_RESERVE_FLOOR_HIT" {
		t.Fatalf("expected exact fee-headroom boundary to fall through to reserve-floor refusal, got code=%s failed=%v", code, failed)
	}

	code, _, failed = cfg.checkReserveHealth(200)
	if failed || code != "" {
		t.Fatalf("expected exact reserve-floor boundary to pass, got code=%s failed=%v", code, failed)
	}
}

func TestPublicTxLookupURL(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		PublicRESTURL: "https://api.wolochain.example",
	}

	if got := cfg.publicTxLookupURL(""); got != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/{tx_hash}" {
		t.Fatalf("unexpected public lookup template: %s", got)
	}
	if got := cfg.publicTxLookupURL("ABC123"); got != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/ABC123" {
		t.Fatalf("unexpected public tx lookup: %s", got)
	}
	if got := cfg.preferredTxLookupURL("ABC123"); got != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/ABC123" {
		t.Fatalf("unexpected preferred tx lookup: %s", got)
	}
}

func TestTxLookupURLTrimsTrailingSlashes(t *testing.T) {
	t.Parallel()

	cfg := settlementConfig{
		RESTURL:       "http://127.0.0.1:1317/",
		PublicRESTURL: "https://api.wolochain.example/",
	}

	if got := cfg.txLookupURL("ABC123"); got != "http://127.0.0.1:1317/cosmos/tx/v1beta1/txs/ABC123" {
		t.Fatalf("unexpected internal tx lookup: %s", got)
	}
	if got := cfg.publicTxLookupURL("ABC123"); got != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/ABC123" {
		t.Fatalf("unexpected public tx lookup with trimmed slash: %s", got)
	}
}

func TestNormalizeHTTPURL(t *testing.T) {
	t.Parallel()

	if got := normalizeHTTPURL("api.wolochain.example/", ""); got != "http://api.wolochain.example" {
		t.Fatalf("unexpected normalized bare host url: %s", got)
	}
	if got := normalizeHTTPURL("tcp://127.0.0.1:1317/", ""); got != "http://127.0.0.1:1317" {
		t.Fatalf("unexpected normalized tcp url: %s", got)
	}
	if got := normalizeHTTPURL("https://api.wolochain.example/", ""); got != "https://api.wolochain.example" {
		t.Fatalf("unexpected normalized https url: %s", got)
	}
}

func TestParseOptionalUWoloEnv(t *testing.T) {
	const key = "WOLO_TEST_PARSE_OPTIONAL_UWOLO"
	t.Setenv(key, "2500000")
	amount, err := parseOptionalUWoloEnv(key)
	if err != nil {
		t.Fatalf("expected env parse to succeed, got %v", err)
	}
	if amount != 2500000 {
		t.Fatalf("expected parsed amount 2500000, got %d", amount)
	}

	t.Setenv(key, "bad")
	_, err = parseOptionalUWoloEnv(key)
	if err == nil {
		t.Fatalf("expected invalid env amount to fail")
	}
}

func TestListRecentSettlementRecords(t *testing.T) {
	t.Parallel()

	stateDir := t.TempDir()
	cfg := settlementConfig{StateDir: stateDir}

	older := settlementStoredResult{
		Request: normalizedSettlementRequest{
			RequestID:   "req-older",
			ToAddress:   "wolo1older",
			AmountUWolo: "10",
		},
		Response: settlementExecuteResponse{
			Status:      "failed",
			FailureCode: "PAYOUT_BALANCE_TOO_LOW",
		},
		UpdatedAt: time.Date(2026, 4, 8, 1, 0, 0, 0, time.UTC),
	}
	newer := settlementStoredResult{
		Request: normalizedSettlementRequest{
			RequestID:   "req-newer",
			ToAddress:   "wolo1newer",
			AmountUWolo: "20",
		},
		Response: settlementExecuteResponse{
			Status: "confirmed",
		},
		UpdatedAt: time.Date(2026, 4, 8, 2, 0, 0, 0, time.UTC),
	}

	if err := writeSettlementStoredResult(filepath.Join(stateDir, "requests", "req-older.json"), older); err != nil {
		t.Fatalf("write older record: %v", err)
	}
	if err := writeSettlementStoredResult(filepath.Join(stateDir, "requests", "req-newer.json"), newer); err != nil {
		t.Fatalf("write newer record: %v", err)
	}

	items, err := cfg.listRecentSettlementRecords(10, "all", "")
	if err != nil {
		t.Fatalf("list recent records: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 records, got %d", len(items))
	}
	if items[0].RequestID != "req-newer" || items[1].RequestID != "req-older" {
		t.Fatalf("unexpected request order: %+v", items)
	}

	items, err = cfg.listRecentSettlementRecords(10, "failed", "PAYOUT_BALANCE_TOO_LOW")
	if err != nil {
		t.Fatalf("list filtered records: %v", err)
	}
	if len(items) != 1 || items[0].RequestID != "req-older" {
		t.Fatalf("unexpected filtered records: %+v", items)
	}
	if items[0].Summary.Outcome != "refused" {
		t.Fatalf("expected summary outcome refused, got %+v", items[0].Summary)
	}
}

func TestSummarizeSettlementRecentItems(t *testing.T) {
	t.Parallel()

	items := []settlementRecentItem{
		{
			Summary: settlementRecordSummary{
				Status:      "failed",
				Outcome:     "refused",
				FailureCode: "PAYOUT_RESERVE_FLOOR_HIT",
				Retryable:   true,
			},
		},
		{
			Summary: settlementRecordSummary{
				Status:           "confirmed",
				Outcome:          "idempotent_replay",
				IdempotentReplay: true,
			},
		},
	}

	summary := summarizeSettlementRecentItems(20, "all", "", items)
	if summary.RequestedLimit != 20 || summary.Returned != 2 {
		t.Fatalf("unexpected recent summary counts: %+v", summary)
	}
	if summary.RefusedCount != 1 || summary.ConfirmedCount != 1 || summary.ReplayCount != 1 || summary.RetryableCount != 1 {
		t.Fatalf("unexpected recent summary totals: %+v", summary)
	}
	if summary.FailureCodes["PAYOUT_RESERVE_FLOOR_HIT"] != 1 {
		t.Fatalf("unexpected failure-code summary: %+v", summary.FailureCodes)
	}
}

func TestSettlementHTTPAuthBehavior(t *testing.T) {
	t.Parallel()

	cfg := newTestSettlementConfig(t, "wolo1payoutaddress000000000000000000000000000", map[string]string{
		"wolo1payoutaddress000000000000000000000000000": "5000000",
	})
	cfg.AuthToken = "secret-token"

	handler := cfg.newSettlementHTTPHandler()

	request := httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", strings.NewReader("{"))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected missing auth to be unauthorized, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", strings.NewReader("{"))
	request.Header.Set("Authorization", "Bearer wrong-token")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected invalid auth to be unauthorized, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", strings.NewReader("{"))
	request.Header.Set("Authorization", "Bearer secret-token")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected valid auth to proceed to request validation, got %d", recorder.Code)
	}

	cfg.AuthToken = ""
	handler = cfg.newSettlementHTTPHandler()
	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/payouts", strings.NewReader("{"))
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected auth bypass when token unset, got %d", recorder.Code)
	}
}

func TestSettlementHTTPReadOnlyRoutesStayOpen(t *testing.T) {
	t.Parallel()

	cfg := newTestSettlementConfig(t, "wolo1payoutaddress000000000000000000000000000", map[string]string{
		"wolo1payoutaddress000000000000000000000000000": "5000000",
	})
	cfg.AuthToken = "secret-token"

	handler := cfg.newSettlementHTTPHandler()

	request := httptest.NewRequest(http.MethodGet, "/settlement/v1/health", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected health route without auth to stay open, got %d body=%s", recorder.Code, recorder.Body.String())
	}

	request = httptest.NewRequest(http.MethodGet, "/settlement/v1/txs/", nil)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected proof route without auth to stay open, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodGet, "/settlement/v1/escrow/txs/not-a-real-hash", nil)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code == http.StatusUnauthorized {
		t.Fatalf("expected escrow verify route without auth to stay open, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodGet, "/settlement/v1/escrow/deposits?limit=1", nil)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code == http.StatusUnauthorized {
		t.Fatalf("expected escrow deposits route without auth to stay open, got %d", recorder.Code)
	}
}

func TestSettlementDoctorWarningsAndPayoutAddressMismatch(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"

	t.Run("warnings", func(t *testing.T) {
		t.Parallel()

		cfg := newTestSettlementConfig(t, payoutAddress, map[string]string{
			payoutAddress: "5000000",
		})
		cfg.PublicRESTURL = ""
		cfg.AuthToken = ""
		cfg.EscrowAddress = ""
		cfg.MinPayoutBalanceUWolo = 0
		cfg.FeeHeadroomUWolo = 0

		report := cfg.buildHealthReport(t.Context())
		if !report.OK {
			t.Fatalf("expected doctor report to stay healthy, got %+v", report)
		}

		expectedWarnings := []string{
			"WOLO_SETTLEMENT_AUTH_TOKEN is empty",
			"WOLO_SETTLEMENT_PUBLIC_REST_URL is empty",
			"WOLO_SETTLEMENT_MIN_PAYOUT_BALANCE_UWOLO is zero",
			"WOLO_SETTLEMENT_FEE_HEADROOM_UWOLO is zero",
			"WOLO_SETTLEMENT_ESCROW_ADDRESS is empty",
		}
		for _, expected := range expectedWarnings {
			if !containsString(report.Warnings, expected) {
				t.Fatalf("expected warning containing %q, got %+v", expected, report.Warnings)
			}
		}
	})

	t.Run("payout-address-mismatch", func(t *testing.T) {
		t.Parallel()

		cfg := newTestSettlementConfig(t, payoutAddress, map[string]string{
			payoutAddress: "5000000",
		})
		cfg.PayoutAddress = "wolo1differentpayout0000000000000000000000000"
		cfg.EscrowAddress = "wolo1escrow000000000000000000000000000000000"
		cfg.PublicRESTURL = "https://rest.aoe2hdbets.com"
		cfg.AuthToken = "secret-token"
		cfg.MinPayoutBalanceUWolo = 1000000000
		cfg.FeeHeadroomUWolo = 10000000

		report := cfg.buildHealthReport(t.Context())
		if report.OK || report.FailureCode != "PAYOUT_ADDRESS_MISMATCH" {
			t.Fatalf("expected payout address mismatch failure, got %+v", report)
		}
	})
}

func TestVerifyEscrowDepositAndHTTPRoute(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const escrowAddress = "wolo1escrow000000000000000000000000000000000"
	const depositorAddress = "wolo1sender000000000000000000000000000000000"
	txHash := strings.Repeat("D", 64)

	cfg := newTestSettlementConfigWithTxs(
		t,
		payoutAddress,
		map[string]string{payoutAddress: "5000"},
		map[string]mockSettlementTx{
			txHash: {
				Hash:        txHash,
				Sender:      depositorAddress,
				Recipient:   escrowAddress,
				AmountUWolo: "700",
				Memo:        "escrow deposit",
				Timestamp:   "2026-04-08T00:00:03Z",
			},
		},
		nil,
	)
	cfg.EscrowAddress = escrowAddress

	response, err := cfg.verifyEscrowDeposit(t.Context(), txHash, depositorAddress, "700")
	if err != nil {
		t.Fatalf("verify escrow deposit: %v", err)
	}
	if !response.OK || !response.DepositFound {
		t.Fatalf("expected escrow deposit verification to pass, got %+v", response)
	}
	if response.Lookup == nil || response.Lookup.Kind != "escrow_deposit" || !response.Lookup.MatchedExpected {
		t.Fatalf("unexpected lookup response: %+v", response.Lookup)
	}

	mismatch, err := cfg.verifyEscrowDeposit(t.Context(), txHash, depositorAddress, "701")
	if err != nil {
		t.Fatalf("verify escrow mismatch: %v", err)
	}
	if mismatch.OK || !mismatch.DepositFound || mismatch.FailureCode != "ESCROW_DEPOSIT_MISMATCH" {
		t.Fatalf("expected escrow mismatch, got %+v", mismatch)
	}

	handler := cfg.newSettlementHTTPHandler()
	request := httptest.NewRequest(http.MethodGet, "/settlement/v1/escrow/txs/"+txHash+"?expected_sender="+depositorAddress+"&expected_amount_uwolo=700", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected escrow verify route to succeed, got %d body=%s", recorder.Code, recorder.Body.String())
	}

	httpResponse := settlementEscrowVerifyResponse{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &httpResponse); err != nil {
		t.Fatalf("decode escrow verify response: %v", err)
	}
	if !httpResponse.OK || httpResponse.Lookup == nil || httpResponse.Lookup.CanonicalTxLookupPreferred == "" {
		t.Fatalf("unexpected escrow verify body: %+v", httpResponse)
	}
}

func TestListRecentEscrowDepositsAndHTTPRoute(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const escrowAddress = "wolo1escrow000000000000000000000000000000000"
	const senderA = "wolo1sendera00000000000000000000000000000000"
	const senderB = "wolo1senderb00000000000000000000000000000000"
	txHashA := strings.Repeat("A", 64)
	txHashB := strings.Repeat("B", 64)

	cfg := newTestSettlementConfigWithTxs(
		t,
		payoutAddress,
		map[string]string{payoutAddress: "5000"},
		map[string]mockSettlementTx{
			txHashA: {
				Hash:        txHashA,
				Sender:      senderA,
				Recipient:   escrowAddress,
				AmountUWolo: "400",
				Memo:        "older deposit",
				Timestamp:   "2026-04-08T00:00:04Z",
			},
			txHashB: {
				Hash:        txHashB,
				Sender:      senderB,
				Recipient:   escrowAddress,
				AmountUWolo: "900",
				Memo:        "newer deposit",
				Timestamp:   "2026-04-08T00:00:05Z",
			},
		},
		nil,
	)
	cfg.EscrowAddress = escrowAddress

	response, err := cfg.listRecentEscrowDeposits(t.Context(), 10, "")
	if err != nil {
		t.Fatalf("list recent escrow deposits: %v", err)
	}
	if !response.OK || response.Count != 2 {
		t.Fatalf("unexpected escrow recent response: %+v", response)
	}
	if response.Deposits[0].TxHash != txHashB || response.Deposits[1].TxHash != txHashA {
		t.Fatalf("expected newest deposit first, got %+v", response.Deposits)
	}
	if response.Deposits[0].CanonicalTxLookupPreferred != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/"+txHashB {
		t.Fatalf("unexpected preferred proof link: %+v", response.Deposits[0])
	}

	filtered, err := cfg.listRecentEscrowDeposits(t.Context(), 10, senderA)
	if err != nil {
		t.Fatalf("list filtered escrow deposits: %v", err)
	}
	if !filtered.OK || filtered.Count != 1 || filtered.Deposits[0].Sender != senderA {
		t.Fatalf("unexpected filtered escrow deposits: %+v", filtered)
	}

	handler := cfg.newSettlementHTTPHandler()
	request := httptest.NewRequest(http.MethodGet, "/settlement/v1/escrow/deposits?limit=1&sender="+senderB, nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected escrow recent route to succeed, got %d body=%s", recorder.Code, recorder.Body.String())
	}

	httpResponse := settlementEscrowRecentResponse{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &httpResponse); err != nil {
		t.Fatalf("decode escrow recent response: %v", err)
	}
	if !httpResponse.OK || httpResponse.Count != 1 || httpResponse.Deposits[0].Sender != senderB {
		t.Fatalf("unexpected escrow recent http response: %+v", httpResponse)
	}
}

func TestPrepareSettlementRunRequestDerivesIDsAndWarnings(t *testing.T) {
	t.Parallel()

	runID := "run-42"
	normalized, response := prepareSettlementRunRequest(settlementRunRequest{
		SettlementRunID: runID,
		Memo:            " batch memo ",
		Payouts: []settlementRunPayoutInput{
			{
				ToAddress:   "wolo1recipienta000000000000000000000000000000",
				AmountUWolo: "100",
			},
			{
				ToAddress:   "wolo1recipienta000000000000000000000000000000",
				AmountUWolo: "100",
			},
		},
	})
	if response.FailureCode != "" {
		t.Fatalf("expected request to stay valid, got failure=%s detail=%s", response.FailureCode, response.Detail)
	}
	if len(normalized.Payouts) != 2 {
		t.Fatalf("expected 2 normalized payouts, got %d", len(normalized.Payouts))
	}
	if normalized.Payouts[0].RequestID != runID+":item-001" || normalized.Payouts[1].RequestID != runID+":item-002" {
		t.Fatalf("unexpected derived request ids: %+v", normalized.Payouts)
	}
	if normalized.Payouts[0].Memo != "batch memo" || normalized.Payouts[1].Memo != "batch memo" {
		t.Fatalf("expected run memo inheritance, got %+v", normalized.Payouts)
	}
	if len(response.Warnings) != 1 || !strings.Contains(response.Warnings[0], "duplicate payout line items detected") {
		t.Fatalf("expected duplicate payout warning, got %+v", response.Warnings)
	}
	if response.Payouts[0].Outcome != "ready" || response.Payouts[1].Outcome != "ready" {
		t.Fatalf("expected ready payouts, got %+v", response.Payouts)
	}
	if len(response.Payouts[0].Warnings) != 1 || len(response.Payouts[1].Warnings) != 1 {
		t.Fatalf("expected duplicate warning on each payout, got %+v", response.Payouts)
	}
}

func TestValidateSettlementRunCapacityBoundariesAndPrecedence(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const recipientAddress = "wolo1recipienta000000000000000000000000000000"

	testCases := []struct {
		name           string
		balanceUWolo   string
		minUWolo       uint64
		headroomUWolo  uint64
		amountUWolo    string
		wantOK         bool
		wantStatus     string
		wantFailure    string
		wantProjected  string
		wantRetryable  bool
		wantFeeTotal   string
		wantItemResult string
	}{
		{
			name:           "low-balance-precedence",
			balanceUWolo:   "149",
			minUWolo:       0,
			headroomUWolo:  0,
			amountUWolo:    "150",
			wantStatus:     "failed",
			wantFailure:    "PAYOUT_BALANCE_TOO_LOW",
			wantRetryable:  true,
			wantFeeTotal:   "25",
			wantItemResult: "refused",
		},
		{
			name:           "fee-headroom-precedence",
			balanceUWolo:   "200",
			minUWolo:       100,
			headroomUWolo:  50,
			amountUWolo:    "151",
			wantStatus:     "failed",
			wantFailure:    "PAYOUT_FEE_HEADROOM_TOO_LOW",
			wantProjected:  "49",
			wantRetryable:  true,
			wantFeeTotal:   "25",
			wantItemResult: "refused",
		},
		{
			name:           "exact-reserve-floor-boundary",
			balanceUWolo:   "300",
			minUWolo:       200,
			headroomUWolo:  50,
			amountUWolo:    "100",
			wantOK:         true,
			wantStatus:     "validated",
			wantProjected:  "200",
			wantFeeTotal:   "25",
			wantItemResult: "ready",
		},
		{
			name:           "exact-fee-headroom-boundary",
			balanceUWolo:   "150",
			minUWolo:       0,
			headroomUWolo:  50,
			amountUWolo:    "100",
			wantOK:         true,
			wantStatus:     "validated",
			wantProjected:  "50",
			wantFeeTotal:   "25",
			wantItemResult: "ready",
		},
	}

	for _, testCase := range testCases {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			cfg := newTestSettlementConfig(t, payoutAddress, map[string]string{
				payoutAddress: testCase.balanceUWolo,
			})
			cfg.MinPayoutBalanceUWolo = testCase.minUWolo
			cfg.FeeHeadroomUWolo = testCase.headroomUWolo
			cfg.Fees = "25uwolo"

			response, err := cfg.validateSettlementRun(t.Context(), settlementRunRequest{
				SettlementRunID: "run-" + testCase.name,
				Payouts: []settlementRunPayoutInput{
					{
						ToAddress:   recipientAddress,
						AmountUWolo: testCase.amountUWolo,
					},
				},
			})
			if err != nil {
				t.Fatalf("validate settlement run: %v", err)
			}

			if response.OK != testCase.wantOK || response.Status != testCase.wantStatus || response.FailureCode != testCase.wantFailure {
				t.Fatalf("unexpected run response: %+v", response)
			}
			if response.ProjectedRemainingUWolo != testCase.wantProjected {
				t.Fatalf("expected projected remaining %q, got %q", testCase.wantProjected, response.ProjectedRemainingUWolo)
			}
			if response.Retryable != testCase.wantRetryable {
				t.Fatalf("expected retryable=%v, got %+v", testCase.wantRetryable, response)
			}
			if response.EstimatedFeeTotalUWolo != testCase.wantFeeTotal {
				t.Fatalf("expected estimated fee %q, got %+v", testCase.wantFeeTotal, response)
			}
			if len(response.Payouts) != 1 || response.Payouts[0].Outcome != testCase.wantItemResult {
				t.Fatalf("unexpected payout results: %+v", response.Payouts)
			}
		})
	}
}

func TestSettlementHTTPRunAuthBehavior(t *testing.T) {
	t.Parallel()

	cfg := newTestSettlementConfig(t, "wolo1payoutaddress000000000000000000000000000", map[string]string{
		"wolo1payoutaddress000000000000000000000000000": "5000000",
	})
	cfg.AuthToken = "secret-token"

	handler := cfg.newSettlementHTTPHandler()
	validPayload := `{"settlement_run_id":"run-1","payouts":[{"to_address":"wolo1recipienta000000000000000000000000000000","amount_uwolo":"1"}]}`

	request := httptest.NewRequest(http.MethodPost, "/settlement/v1/runs/validate", strings.NewReader(validPayload))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected missing auth to be unauthorized, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/runs", strings.NewReader(validPayload))
	request.Header.Set("Authorization", "Bearer wrong-token")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected invalid auth to be unauthorized, got %d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/runs/validate", strings.NewReader(validPayload))
	request.Header.Set("Authorization", "Bearer secret-token")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected valid auth to reach validation, got %d body=%s", recorder.Code, recorder.Body.String())
	}

	runResponse := settlementRunResponse{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &runResponse); err != nil {
		t.Fatalf("decode run validation response: %v", err)
	}
	if !runResponse.OK || runResponse.Status != "validated" {
		t.Fatalf("unexpected run validation response: %+v", runResponse)
	}

	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/runs", strings.NewReader("{"))
	request.Header.Set("Authorization", "Bearer secret-token")
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected invalid run JSON to fail as bad request, got %d", recorder.Code)
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &runResponse); err != nil {
		t.Fatalf("decode run execute failure response: %v", err)
	}
	if runResponse.FailureCode != "INVALID_RUN" || runResponse.Detail != "request body must be valid JSON" {
		t.Fatalf("unexpected invalid run response: %+v", runResponse)
	}

	cfg.AuthToken = ""
	handler = cfg.newSettlementHTTPHandler()
	request = httptest.NewRequest(http.MethodPost, "/settlement/v1/runs", strings.NewReader("{"))
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected auth bypass when token unset, got %d", recorder.Code)
	}
}

func TestExecuteSettlementRunStoresProofsAndReplays(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const recipientA = "wolo1recipienta000000000000000000000000000000"
	const recipientB = "wolo1recipientb000000000000000000000000000000"
	txHashA := strings.Repeat("A", 64)
	txHashB := strings.Repeat("B", 64)

	cfg := newTestSettlementConfigWithTxs(
		t,
		payoutAddress,
		map[string]string{payoutAddress: "5000"},
		map[string]mockSettlementTx{
			txHashA: {
				Hash:        txHashA,
				Sender:      payoutAddress,
				Recipient:   recipientA,
				AmountUWolo: "100",
				Memo:        "batch memo",
				Timestamp:   "2026-04-08T00:00:00Z",
			},
			txHashB: {
				Hash:        txHashB,
				Sender:      payoutAddress,
				Recipient:   recipientB,
				AmountUWolo: "200",
				Memo:        "batch memo",
				Timestamp:   "2026-04-08T00:00:01Z",
			},
		},
		map[string]string{
			recipientA: txHashA,
			recipientB: txHashB,
		},
	)
	cfg.Fees = "25uwolo"

	request := settlementRunRequest{
		SettlementRunID: "run-confirmed",
		SourceApp:       "settler",
		SourceEventID:   "event-42",
		Note:            "batch settlement smoke",
		Memo:            "batch memo",
		Payouts: []settlementRunPayoutInput{
			{ToAddress: recipientA, AmountUWolo: "100"},
			{ToAddress: recipientB, AmountUWolo: "200"},
		},
	}

	response, err := cfg.executeSettlementRun(t.Context(), request)
	if err != nil {
		t.Fatalf("execute settlement run: %v", err)
	}
	if !response.OK || response.Status != "confirmed" || response.ExecutedPayoutCount != 2 || response.ConfirmedPayoutCount != 2 {
		t.Fatalf("unexpected run execution response: %+v", response)
	}
	if response.Detail != "all 2 payouts confirmed on WoloChain" {
		t.Fatalf("unexpected run execution detail: %+v", response)
	}
	if response.RequestedTotalUWolo != "300" || response.ExecutedTotalUWolo != "300" || response.ConfirmedTotalUWolo != "300" {
		t.Fatalf("unexpected run totals: %+v", response)
	}
	if len(response.Payouts) != 2 {
		t.Fatalf("expected 2 payout results, got %+v", response)
	}
	if response.Payouts[0].CanonicalTxLookupPreferred != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/"+txHashA {
		t.Fatalf("unexpected preferred proof url for first payout: %+v", response.Payouts[0])
	}
	if response.Payouts[0].CanonicalTxLookupInternal != cfg.RESTURL+"/cosmos/tx/v1beta1/txs/"+txHashA {
		t.Fatalf("unexpected internal proof url for first payout: %+v", response.Payouts[0])
	}
	if response.Payouts[1].CanonicalTxLookupPublic != "https://api.wolochain.example/cosmos/tx/v1beta1/txs/"+txHashB {
		t.Fatalf("unexpected public proof url for second payout: %+v", response.Payouts[1])
	}

	record, err := readSettlementRunStoredResult(cfg.runRecordPath("run-confirmed"))
	if err != nil {
		t.Fatalf("read stored run record: %v", err)
	}
	if record.Response.Status != "confirmed" || len(record.Response.Payouts) != 2 {
		t.Fatalf("unexpected stored run record: %+v", record)
	}

	summary := summarizeSettlementRunStoredResult(record)
	if summary.SignerRole != settlementSignerRole || summary.SignerAddress != payoutAddress {
		t.Fatalf("unexpected run summary signer fields: %+v", summary)
	}
	if summary.SourceApp != "settler" || summary.SourceEventID != "event-42" || summary.ExecutedTotalUWolo != "300" {
		t.Fatalf("unexpected run summary fields: %+v", summary)
	}

	replayed, err := cfg.executeSettlementRun(t.Context(), request)
	if err != nil {
		t.Fatalf("replay settlement run: %v", err)
	}
	if !replayed.IdempotentReplay || replayed.Status != "confirmed" || replayed.Payouts[0].TxHash != txHashA {
		t.Fatalf("unexpected replayed run response: %+v", replayed)
	}
}

func TestExecuteSettlementRunPartialAndRecentHistory(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const recipientA = "wolo1recipienta000000000000000000000000000000"
	const recipientB = "wolo1recipientb000000000000000000000000000000"
	txHashA := strings.Repeat("A", 64)

	cfg := newTestSettlementConfigWithTxs(
		t,
		payoutAddress,
		map[string]string{payoutAddress: "5000"},
		map[string]mockSettlementTx{
			txHashA: {
				Hash:        txHashA,
				Sender:      payoutAddress,
				Recipient:   recipientA,
				AmountUWolo: "100",
				Memo:        "partial memo",
				Timestamp:   "2026-04-08T00:00:02Z",
			},
		},
		map[string]string{
			recipientA: txHashA,
		},
	)

	conflicting := normalizedSettlementRequest{
		RequestID:   "run-partial:item-002",
		ToAddress:   "wolo1otherrecipient000000000000000000000000000",
		AmountUWolo: "999",
		Memo:        "previous payout",
	}
	if err := writeSettlementStoredResult(cfg.requestRecordPath(conflicting.RequestID), settlementStoredResult{
		Request:     conflicting,
		Fingerprint: hashSettlementRequest(conflicting, payoutAddress),
		Response: settlementExecuteResponse{
			OK:            true,
			Status:        "confirmed",
			RequestID:     conflicting.RequestID,
			ChainID:       cfg.ChainID,
			SignerRole:    settlementSignerRole,
			SignerAddress: payoutAddress,
			ToAddress:     conflicting.ToAddress,
			AmountUWolo:   conflicting.AmountUWolo,
			AmountWolo:    formatDisplayAmount(conflicting.AmountUWolo),
			TxHash:        strings.Repeat("C", 64),
		},
		UpdatedAt: time.Date(2026, 4, 8, 0, 0, 0, 0, time.UTC),
	}); err != nil {
		t.Fatalf("write conflicting request record: %v", err)
	}

	request := settlementRunRequest{
		SettlementRunID: "run-partial",
		SourceApp:       "settler",
		Payouts: []settlementRunPayoutInput{
			{ToAddress: recipientA, AmountUWolo: "100"},
			{ToAddress: recipientB, AmountUWolo: "200"},
		},
	}

	response, err := cfg.executeSettlementRun(t.Context(), request)
	if err != nil {
		t.Fatalf("execute partial settlement run: %v", err)
	}
	if response.OK || response.Status != "partial" || response.FailureCode != "IDEMPOTENCY_CONFLICT" {
		t.Fatalf("unexpected partial run response: %+v", response)
	}
	if response.ExecutedPayoutCount != 1 || response.ConfirmedPayoutCount != 1 || response.RefusedPayoutCount != 1 {
		t.Fatalf("unexpected partial run counts: %+v", response)
	}
	if response.Detail != "1 of 2 payouts executed; inspect per-recipient results for the remaining failures" {
		t.Fatalf("unexpected partial run detail: %+v", response)
	}
	if response.Payouts[1].FailureCode != "IDEMPOTENCY_CONFLICT" || response.Payouts[1].Outcome != "refused" {
		t.Fatalf("unexpected per-recipient failure result: %+v", response.Payouts)
	}

	items, err := cfg.listRecentSettlementRuns(10, "partial", "IDEMPOTENCY_CONFLICT")
	if err != nil {
		t.Fatalf("list recent partial runs: %v", err)
	}
	if len(items) != 1 || items[0].SettlementRunID != "run-partial" {
		t.Fatalf("unexpected recent partial runs: %+v", items)
	}
	if items[0].Summary.SignerAddress != payoutAddress || items[0].Summary.ExecutedTotalUWolo != "100" {
		t.Fatalf("unexpected recent partial run summary: %+v", items[0].Summary)
	}
}

func TestExecuteSettlementStoresRetryableRefusal(t *testing.T) {
	t.Parallel()

	payoutAddress := "wolo1payoutaddress000000000000000000000000000"
	cfg := newTestSettlementConfig(t, payoutAddress, map[string]string{
		payoutAddress: "250",
	})
	cfg.MinPayoutBalanceUWolo = 200
	cfg.FeeHeadroomUWolo = 50

	response, err := cfg.executeSettlement(t.Context(), settlementExecuteRequest{
		RequestID:   "reserve-floor-refusal",
		ToAddress:   "wolo1recipient000000000000000000000000000000",
		AmountUWolo: "101",
		Memo:        "reserve check",
	})
	if err != nil {
		t.Fatalf("execute settlement: %v", err)
	}
	if response.OK || response.FailureCode != "PAYOUT_RESERVE_FLOOR_HIT" || !response.Retryable {
		t.Fatalf("unexpected refusal response: %+v", response)
	}

	record, err := readSettlementStoredResult(cfg.requestRecordPath("reserve-floor-refusal"))
	if err != nil {
		t.Fatalf("read stored refusal record: %v", err)
	}
	if record.Response.FailureCode != "PAYOUT_RESERVE_FLOOR_HIT" || record.Response.Status != "failed" {
		t.Fatalf("unexpected stored refusal record: %+v", record)
	}

	items, err := cfg.listRecentSettlementRecords(10, "refused", "PAYOUT_RESERVE_FLOOR_HIT")
	if err != nil {
		t.Fatalf("list recent refusal records: %v", err)
	}
	if len(items) != 1 || items[0].Summary.Outcome != "refused" {
		t.Fatalf("unexpected recent refusal items: %+v", items)
	}
}

func newTestSettlementConfig(t *testing.T, payoutAddress string, balances map[string]string) settlementConfig {
	t.Helper()

	return newTestSettlementConfigWithTxs(t, payoutAddress, balances, nil, nil)
}

func newMockSettlementChainHandler(balances map[string]string) http.Handler {
	return newMockSettlementChainHandlerWithTxs(balances, nil)
}

type mockSettlementTx struct {
	Hash        string
	Sender      string
	Recipient   string
	AmountUWolo string
	Memo        string
	Code        uint32
	Codespace   string
	RawLog      string
	Timestamp   string
}

func newTestSettlementConfigWithTxs(t *testing.T, payoutAddress string, balances map[string]string, txs map[string]mockSettlementTx, recipientTxHashes map[string]string) settlementConfig {
	t.Helper()

	server := httptest.NewServer(newMockSettlementChainHandlerWithTxs(balances, txs))
	t.Cleanup(server.Close)

	executablePath := writeFakeSettlementExecutableWithTxs(t, payoutAddress, recipientTxHashes)

	return settlementConfig{
		ExecutablePath:  executablePath,
		HomeDir:         t.TempDir(),
		KeyringBackend:  "test",
		NodeAddr:        "tcp://127.0.0.1:26657",
		RPCHTTP:         server.URL,
		RESTURL:         server.URL,
		PublicRESTURL:   "https://api.wolochain.example/",
		ChainID:         settlementCanonicalChainID,
		BaseDenom:       settlementCanonicalBaseDenom,
		DisplayDenom:    settlementCanonicalDisplayDenom,
		AddressPrefix:   settlementCanonicalPrefix,
		PayoutKeyName:   "payout",
		PayoutAddress:   payoutAddress,
		BroadcastMode:   "sync",
		Gas:             "auto",
		GasAdjustment:   "1.5",
		GasPrices:       settlementDefaultGasPrices,
		StateDir:        t.TempDir(),
		ListenAddr:      settlementDefaultListenAddr,
		RequestLockTTL:  2 * time.Minute,
		RequestTimeout:  30 * time.Second,
		LookupTimeout:   2 * time.Second,
		HealthTimeout:   2 * time.Second,
		ConfirmTimeout:  2 * time.Second,
		ConfirmInterval: 10 * time.Millisecond,
	}
}

func newMockSettlementChainHandlerWithTxs(balances map[string]string, txs map[string]mockSettlementTx) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/status", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"result": map[string]any{
				"node_info": map[string]any{
					"network": settlementCanonicalChainID,
				},
			},
		})
	})
	mux.HandleFunc("/cosmos/base/tendermint/v1beta1/node_info", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"default_node_info": map[string]any{
				"network": settlementCanonicalChainID,
			},
		})
	})
	mux.HandleFunc("/cosmos/bank/v1beta1/denoms_metadata/uwolo", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"metadata": map[string]any{
				"base":    settlementCanonicalBaseDenom,
				"display": settlementCanonicalDisplayDenom,
			},
		})
	})
	mux.HandleFunc("/cosmos/staking/v1beta1/params", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"params": map[string]any{
				"bond_denom": settlementCanonicalBaseDenom,
			},
		})
	})
	mux.HandleFunc("/cosmos/mint/v1beta1/params", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"params": map[string]any{
				"mint_denom": settlementCanonicalBaseDenom,
			},
		})
	})
	mux.HandleFunc("/cosmos/bank/v1beta1/balances/", func(w http.ResponseWriter, r *http.Request) {
		address := filepath.Base(r.URL.Path)
		amount := balances[address]
		_ = json.NewEncoder(w).Encode(map[string]any{
			"balances": []map[string]string{
				{
					"denom":  settlementCanonicalBaseDenom,
					"amount": amount,
				},
			},
		})
	})
	mux.HandleFunc("/cosmos/tx/v1beta1/txs", func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		recipient := extractTxSearchFilter(query, "transfer.recipient")
		sender := extractTxSearchFilter(query, "transfer.sender")

		type searchHit struct {
			tx mockSettlementTx
		}
		hits := make([]searchHit, 0, len(txs))
		for _, tx := range txs {
			if recipient != "" && !strings.EqualFold(tx.Recipient, recipient) {
				continue
			}
			if sender != "" && !strings.EqualFold(tx.Sender, sender) {
				continue
			}
			hits = append(hits, searchHit{tx: tx})
		}

		sort.Slice(hits, func(i, j int) bool {
			left := firstNonEmpty(hits[i].tx.Timestamp, "2026-04-08T00:00:00Z")
			right := firstNonEmpty(hits[j].tx.Timestamp, "2026-04-08T00:00:00Z")
			if left == right {
				return hits[i].tx.Hash > hits[j].tx.Hash
			}
			return left > right
		})

		limit := len(hits)
		if rawLimit := strings.TrimSpace(r.URL.Query().Get("pagination.limit")); rawLimit != "" {
			if parsedLimit, err := strconv.Atoi(rawLimit); err == nil && parsedLimit < limit {
				limit = parsedLimit
			}
		}
		hits = hits[:limit]

		searchTxs := make([]map[string]any, 0, len(hits))
		searchResponses := make([]map[string]any, 0, len(hits))
		for _, hit := range hits {
			searchTxs = append(searchTxs, map[string]any{
				"body": map[string]any{
					"memo": hit.tx.Memo,
				},
			})
			searchResponses = append(searchResponses, map[string]any{
				"height":    "123",
				"txhash":    hit.tx.Hash,
				"code":      hit.tx.Code,
				"codespace": hit.tx.Codespace,
				"raw_log":   hit.tx.RawLog,
				"timestamp": firstNonEmpty(hit.tx.Timestamp, "2026-04-08T00:00:00Z"),
				"events": []map[string]any{
					{
						"type": "transfer",
						"attributes": []map[string]string{
							{"key": "sender", "value": hit.tx.Sender},
							{"key": "recipient", "value": hit.tx.Recipient},
							{"key": "amount", "value": hit.tx.AmountUWolo + settlementCanonicalBaseDenom},
						},
					},
				},
			})
		}

		_ = json.NewEncoder(w).Encode(map[string]any{
			"txs":          searchTxs,
			"tx_responses": searchResponses,
			"pagination": map[string]string{
				"next_key": "",
				"total":    strconv.Itoa(len(hits)),
			},
			"total": strconv.Itoa(len(hits)),
		})
	})
	mux.HandleFunc("/cosmos/tx/v1beta1/txs/", func(w http.ResponseWriter, r *http.Request) {
		txHash := strings.ToUpper(filepath.Base(r.URL.Path))
		tx, ok := txs[txHash]
		if !ok {
			http.NotFound(w, r)
			return
		}

		_ = json.NewEncoder(w).Encode(map[string]any{
			"tx": map[string]any{
				"body": map[string]any{
					"memo": tx.Memo,
				},
			},
			"tx_response": map[string]any{
				"height":    "123",
				"txhash":    tx.Hash,
				"code":      tx.Code,
				"codespace": tx.Codespace,
				"raw_log":   tx.RawLog,
				"timestamp": firstNonEmpty(tx.Timestamp, "2026-04-08T00:00:00Z"),
				"events": []map[string]any{
					{
						"type": "transfer",
						"attributes": []map[string]string{
							{"key": "sender", "value": tx.Sender},
							{"key": "recipient", "value": tx.Recipient},
							{"key": "amount", "value": tx.AmountUWolo + settlementCanonicalBaseDenom},
						},
					},
				},
			},
		})
	})

	return mux
}

func extractTxSearchFilter(query, key string) string {
	for _, part := range strings.Split(query, "AND") {
		part = strings.TrimSpace(part)
		if !strings.HasPrefix(part, key+"=") {
			continue
		}
		value := strings.TrimPrefix(part, key+"=")
		value = strings.TrimSpace(value)
		value = strings.Trim(value, "'")
		return value
	}

	return ""
}

func containsString(values []string, needle string) bool {
	for _, value := range values {
		if strings.Contains(value, needle) {
			return true
		}
	}

	return false
}

func writeFakeSettlementExecutable(t *testing.T, payoutAddress string) string {
	return writeFakeSettlementExecutableWithTxs(t, payoutAddress, nil)
}

func writeFakeSettlementExecutableWithTxs(t *testing.T, payoutAddress string, recipientTxHashes map[string]string) string {
	return writeFakeSettlementExecutableWithTxsAndKeys(t, map[string]string{
		"payout": payoutAddress,
	}, recipientTxHashes)
}

func writeFakeSettlementExecutableWithTxsAndKeys(t *testing.T, keyAddresses map[string]string, recipientTxHashes map[string]string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "fake-wolochaind.sh")
	script := "#!/bin/sh\n"
	if len(keyAddresses) > 0 {
		script += "if [ \"$1\" = \"keys\" ] && [ \"$2\" = \"show\" ]; then\n" +
			"  case \"$3\" in\n"
		for keyName, address := range keyAddresses {
			script += "    \"" + keyName + "\") printf '%s\\n' '" + address + "'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"fi\n"
	}
	if len(recipientTxHashes) > 0 {
		script += "if [ \"$1\" = \"tx\" ] && [ \"$2\" = \"bank\" ] && [ \"$3\" = \"send\" ]; then\n" +
			"  sender=\"$4\"\n" +
			"  recipient=\"$5\"\n" +
			"  amount=\"$6\"\n" +
			"  memo=\"\"\n" +
			"  prev=\"\"\n" +
			"  for arg in \"$@\"; do\n" +
			"    if [ \"$prev\" = \"--note\" ]; then\n" +
			"      memo=\"$arg\"\n" +
			"      break\n" +
			"    fi\n" +
			"    prev=\"$arg\"\n" +
			"  done\n" +
			"  case \"$sender|$recipient|$amount|$memo\" in\n"
		for key, txHash := range recipientTxHashes {
			script += "    \"" + key + "\") printf '{\"height\":\"0\",\"txhash\":\"" + txHash + "\",\"code\":0,\"codespace\":\"\",\"raw_log\":\"\"}\\n'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"  case \"$recipient|$amount|$memo\" in\n"
		for key, txHash := range recipientTxHashes {
			script += "    \"" + key + "\") printf '{\"height\":\"0\",\"txhash\":\"" + txHash + "\",\"code\":0,\"codespace\":\"\",\"raw_log\":\"\"}\\n'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"  case \"$sender|$recipient|$amount\" in\n"
		for key, txHash := range recipientTxHashes {
			script += "    \"" + key + "\") printf '{\"height\":\"0\",\"txhash\":\"" + txHash + "\",\"code\":0,\"codespace\":\"\",\"raw_log\":\"\"}\\n'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"  case \"$recipient|$amount\" in\n"
		for recipient, txHash := range recipientTxHashes {
			script += "    \"" + recipient + "\") printf '{\"height\":\"0\",\"txhash\":\"" + txHash + "\",\"code\":0,\"codespace\":\"\",\"raw_log\":\"\"}\\n'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"  case \"$recipient\" in\n"
		for recipient, txHash := range recipientTxHashes {
			script += "    \"" + recipient + "\") printf '{\"height\":\"0\",\"txhash\":\"" + txHash + "\",\"code\":0,\"codespace\":\"\",\"raw_log\":\"\"}\\n'; exit 0 ;;\n"
		}
		script += "  esac\n" +
			"  printf 'unknown send target: %s %s %s %s\\n' \"$sender\" \"$recipient\" \"$amount\" \"$memo\" >&2\n" +
			"  exit 1\n" +
			"fi\n"
	}
	script += "printf 'unexpected command: %s\\n' \"$*\" >&2\n" +
		"exit 1\n"
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatalf("write fake settlement executable: %v", err)
	}

	return path
}
