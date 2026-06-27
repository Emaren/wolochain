package cmd

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"
)

func TestVerifyChallengeFundingDepositAndRecentRoutes(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
		leftAddress   = "wolo1leftplayer000000000000000000000000000000"
		rightAddress  = "wolo1rightplayer00000000000000000000000000000"
		runID         = "challenge-123-run"
	)

	leftFundingTx := strings.Repeat("A", 64)
	rightFundingTx := strings.Repeat("B", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "5000",
		escrowAddress: "5000",
	}, map[string]mockSettlementTx{
		leftFundingTx: {
			Hash:        leftFundingTx,
			Sender:      leftAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemoWithSettlementRunID(runID, "aoe2hdbets", "challenge-123", "", "left", "left-user", "100", "50"),
			Timestamp:   "2026-04-19T10:00:00Z",
		},
		rightFundingTx: {
			Hash:        rightFundingTx,
			Sender:      rightAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemoWithSettlementRunID(runID, "aoe2hdbets", "challenge-123", "", "right", "right-user", "100", "50"),
			Timestamp:   "2026-04-19T10:01:00Z",
		},
	}, nil)
	cfg.AuthToken = "secret-token"

	response, err := cfg.verifyChallengeFundingDeposit(t.Context(), leftFundingTx, settlementChallengeFundingExpectation{
		Sender:           leftAddress,
		SourceApp:        "aoe2hdbets",
		SettlementRunID:  runID,
		ChallengeID:      "challenge-123",
		ParticipantSide:  "left",
		ParticipantID:    "left-user",
		TotalFundedUWolo: "150",
		WagerUWolo:       "100",
		GuaranteeUWolo:   "50",
	})
	if err != nil {
		t.Fatalf("verify challenge funding deposit: %v", err)
	}
	if !response.OK || response.Funding == nil {
		t.Fatalf("expected verified challenge funding, got %+v", response)
	}
	if response.Funding.WagerUWolo != "100" || response.Funding.GuaranteeUWolo != "50" {
		t.Fatalf("unexpected bucket amounts: %+v", response.Funding)
	}
	if response.Funding.SettlementRunID != runID {
		t.Fatalf("expected settlement run id in funding proof, got %+v", response.Funding)
	}

	recent, err := cfg.listRecentChallengeFundingDeposits(t.Context(), settlementChallengeFundingRecentFilters{
		Limit:           2,
		SourceApp:       "aoe2hdbets",
		SettlementRunID: runID,
		ChallengeID:     "challenge-123",
	})
	if err != nil {
		t.Fatalf("list recent challenge funding deposits: %v", err)
	}
	if !recent.OK || len(recent.Funding) != 2 {
		t.Fatalf("unexpected recent challenge funding response: %+v", recent)
	}
	if recent.Funding[0].FundingTxHash != rightFundingTx || recent.Funding[1].FundingTxHash != leftFundingTx {
		t.Fatalf("unexpected recent challenge funding order: %+v", recent.Funding)
	}

	handler := cfg.newSettlementHTTPHandler()
	verifyRequest := httptest.NewRequest(
		http.MethodGet,
		"/settlement/v1/challenges/funding/txs/"+leftFundingTx+
			"?expected_sender="+url.QueryEscape(leftAddress)+
			"&source_app=aoe2hdbets&settlement_run_id=challenge-123-run&challenge_id=challenge-123&participant_side=left&participant_id=left-user&expected_amount_uwolo=150&wager_uwolo=100&guarantee_uwolo=50",
		nil,
	)
	verifyRecorder := httptest.NewRecorder()
	handler.ServeHTTP(verifyRecorder, verifyRequest)
	if verifyRecorder.Code != http.StatusOK {
		t.Fatalf("expected challenge funding verify route to succeed, got %d body=%s", verifyRecorder.Code, verifyRecorder.Body.String())
	}
	verifyBody := settlementChallengeFundingVerifyResponse{}
	if err := json.Unmarshal(verifyRecorder.Body.Bytes(), &verifyBody); err != nil {
		t.Fatalf("decode challenge funding verify response: %v", err)
	}
	if !verifyBody.OK || verifyBody.Funding == nil || verifyBody.Funding.CanonicalTxLookupPreferred == "" {
		t.Fatalf("unexpected challenge funding verify body: %+v", verifyBody)
	}

	recentRequest := httptest.NewRequest(http.MethodGet, "/settlement/v1/challenges/funding/deposits?limit=1&source_app=aoe2hdbets&settlement_run_id=challenge-123-run&challenge_id=challenge-123", nil)
	recentRecorder := httptest.NewRecorder()
	handler.ServeHTTP(recentRecorder, recentRequest)
	if recentRecorder.Code != http.StatusOK {
		t.Fatalf("expected challenge funding recent route to succeed, got %d body=%s", recentRecorder.Code, recentRecorder.Body.String())
	}
	recentBody := settlementChallengeFundingRecentResponse{}
	if err := json.Unmarshal(recentRecorder.Body.Bytes(), &recentBody); err != nil {
		t.Fatalf("decode challenge funding recent response: %v", err)
	}
	if !recentBody.OK || len(recentBody.Funding) != 1 || recentBody.Funding[0].FundingTxHash != rightFundingTx {
		t.Fatalf("unexpected challenge funding recent body: %+v", recentBody)
	}
}

func TestCanonicalAoE2HDBetsFundingMemoProofAndRejections(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
		senderAddress = "wolo1leftplayer000000000000000000000000000000"
		otherAddress  = "wolo1rightplayer00000000000000000000000000000"
		runID         = "aoe2hdbets:challenge-42:v1"
	)

	validTx := strings.Repeat("1", 64)
	wrongSIDTx := strings.Repeat("2", 64)
	wrongSideTx := strings.Repeat("3", 64)
	wrongBucketTx := strings.Repeat("4", 64)
	extraFieldTx := strings.Repeat("5", 64)
	failedTx := strings.Repeat("6", 64)
	wrongEscrowTx := strings.Repeat("7", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "5000",
		escrowAddress: "5000",
	}, map[string]mockSettlementTx{
		validTx: {
			Hash:        validTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "25000000", "10000000"),
			Timestamp:   "2026-06-27T20:00:00Z",
		},
		wrongSIDTx: {
			Hash:        wrongSIDTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        "wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-41:v1&cid=42&side=left&w=25000000&g=10000000&t=35000000",
			Timestamp:   "2026-06-27T19:59:00Z",
		},
		wrongSideTx: {
			Hash:        wrongSideTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        "wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-42:v1&cid=42&side=creator&w=25000000&g=10000000&t=35000000",
			Timestamp:   "2026-06-27T19:58:00Z",
		},
		wrongBucketTx: {
			Hash:        wrongBucketTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        "wolo.challenge.funding.v1:app=aoe2hdbets&sid=aoe2hdbets:challenge-42:v1&cid=42&side=left&w=25000000&g=9999999&t=35000000",
			Timestamp:   "2026-06-27T19:57:00Z",
		},
		extraFieldTx: {
			Hash:        extraFieldTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "25000000", "10000000") + "&pid=not-in-v1-contract",
			Timestamp:   "2026-06-27T19:56:00Z",
		},
		failedTx: {
			Hash:        failedTx,
			Sender:      senderAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "35000000",
			Memo:        canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "25000000", "10000000"),
			Code:        7,
			RawLog:      "mock failed tx",
			Timestamp:   "2026-06-27T19:55:00Z",
		},
		wrongEscrowTx: {
			Hash:        wrongEscrowTx,
			Sender:      senderAddress,
			Recipient:   otherAddress,
			AmountUWolo: "35000000",
			Memo:        canonicalAoE2HDBetsChallengeFundingMemo("42", "left", "25000000", "10000000"),
			Timestamp:   "2026-06-27T19:54:00Z",
		},
	}, nil)

	expectation := settlementChallengeFundingExpectation{
		Sender:           senderAddress,
		SourceApp:        settlementAoE2HDBetsSourceApp,
		SettlementRunID:  runID,
		ChallengeID:      "42",
		ParticipantSide:  "left",
		TotalFundedUWolo: "35000000",
		WagerUWolo:       "25000000",
		GuaranteeUWolo:   "10000000",
	}
	verified, err := cfg.verifyChallengeFundingDeposit(t.Context(), validTx, expectation)
	if err != nil {
		t.Fatalf("verify canonical funding: %v", err)
	}
	if !verified.OK || verified.Funding == nil {
		t.Fatalf("expected canonical funding proof, got %+v", verified)
	}
	proof := verified.Funding
	if !proof.TxSuccess ||
		proof.ChainID != settlementCanonicalChainID ||
		proof.FundingTxHash != validTx ||
		proof.Sender != senderAddress ||
		proof.EscrowAddress != escrowAddress ||
		proof.TotalFundedUWolo != "35000000" ||
		proof.WagerUWolo != "25000000" ||
		proof.GuaranteeUWolo != "10000000" ||
		proof.ChallengeID != "42" ||
		proof.ParticipantSide != "left" ||
		proof.SettlementRunID != runID {
		t.Fatalf("canonical funding proof omitted or changed a contract field: %+v", proof)
	}

	rejections := []struct {
		name        string
		txHash      string
		expectation settlementChallengeFundingExpectation
		failureCode string
	}{
		{name: "wrong sender", txHash: validTx, expectation: settlementChallengeFundingExpectation{Sender: otherAddress}, failureCode: "CHALLENGE_FUNDING_MISMATCH"},
		{name: "wrong settlement id", txHash: wrongSIDTx, failureCode: "INVALID_CHALLENGE_FUNDING_MEMO"},
		{name: "unsupported side", txHash: wrongSideTx, failureCode: "INVALID_CHALLENGE_FUNDING_MEMO"},
		{name: "bucket total mismatch", txHash: wrongBucketTx, failureCode: "INVALID_CHALLENGE_FUNDING_MEMO"},
		{name: "extra memo field", txHash: extraFieldTx, failureCode: "INVALID_CHALLENGE_FUNDING_MEMO"},
		{name: "failed transaction", txHash: failedTx, failureCode: "TX_FAILED"},
		{name: "noncanonical escrow", txHash: wrongEscrowTx, failureCode: "NOT_ESCROW_DEPOSIT"},
	}
	for _, tc := range rejections {
		t.Run(tc.name, func(t *testing.T) {
			response, err := cfg.verifyChallengeFundingDeposit(t.Context(), tc.txHash, tc.expectation)
			if err != nil {
				t.Fatalf("verify rejected funding: %v", err)
			}
			if response.OK || response.FailureCode != tc.failureCode {
				t.Fatalf("expected %s, got %+v", tc.failureCode, response)
			}
		})
	}

	filters := settlementChallengeFundingRecentFilters{
		Limit:           20,
		Sender:          senderAddress,
		SourceApp:       settlementAoE2HDBetsSourceApp,
		SettlementRunID: runID,
		ChallengeID:     "42",
		ParticipantSide: "left",
	}
	first, err := cfg.listRecentChallengeFundingDeposits(t.Context(), filters)
	if err != nil {
		t.Fatalf("first canonical discovery: %v", err)
	}
	second, err := cfg.listRecentChallengeFundingDeposits(t.Context(), filters)
	if err != nil {
		t.Fatalf("replayed canonical discovery: %v", err)
	}
	firstJSON, _ := json.Marshal(first)
	secondJSON, _ := json.Marshal(second)
	if string(firstJSON) != string(secondJSON) {
		t.Fatalf("read-only discovery replay changed response:\nfirst=%s\nsecond=%s", firstJSON, secondJSON)
	}
	if !first.OK || first.Count != 1 || len(first.Funding) != 1 || first.Funding[0].FundingTxHash != validTx {
		t.Fatalf("expected discovery to return only the fully valid canonical deposit, got %+v", first)
	}

	for _, invalidFilters := range []settlementChallengeFundingRecentFilters{
		{Limit: 1, SourceApp: settlementAoE2HDBetsSourceApp, SettlementRunID: "aoe2hdbets:challenge-41:v1", ChallengeID: "42"},
		{Limit: 1, SourceApp: settlementAoE2HDBetsSourceApp, SettlementRunID: runID, ChallengeID: "42", ParticipantSide: "creator"},
	} {
		rejected, err := cfg.listRecentChallengeFundingDeposits(t.Context(), invalidFilters)
		if err != nil {
			t.Fatalf("validate canonical discovery filters: %v", err)
		}
		if rejected.OK || rejected.FailureCode != "INVALID_CHALLENGE" {
			t.Fatalf("expected invalid canonical discovery filters to be rejected, got %+v", rejected)
		}
	}
}

func TestAoE2HDBetsCanonicalRunIDAndDuplicateFundingAreReplaySafe(t *testing.T) {
	t.Parallel()

	const payoutAddress = "wolo1payoutaddress000000000000000000000000000"
	const escrowAddress = "wolo1escrow000000000000000000000000000000000"
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "5000",
		escrowAddress: "5000",
	}, nil, nil)

	plan, err := cfg.buildSettlementChallengePlan(t.Context(), settlementChallengeRequest{
		SettlementRunID: "aoe2hdbets:challenge-42:second-run:v1",
		SourceApp:       settlementAoE2HDBetsSourceApp,
		ChallengeID:     "42",
		Funding:         []settlementChallengeFundingInput{{FundingTxHash: strings.Repeat("8", 64)}},
		Transfers:       []settlementChallengeTransferInput{{ParticipantSide: "left", Bucket: "wager", Reason: "refund", ToAddress: payoutAddress, AmountUWolo: "1"}},
	})
	if err != nil {
		t.Fatalf("build challenge plan: %v", err)
	}
	if plan.Response.OK || plan.Response.FailureCode != "INVALID_CHALLENGE" ||
		!strings.Contains(plan.Response.Detail, `settlement_run_id must be "aoe2hdbets:challenge-42:v1"`) {
		t.Fatalf("expected canonical idempotency-key refusal, got %+v", plan.Response)
	}

	duplicateTx := strings.Repeat("9", 64)
	participantErrors := validateVerifiedChallengeFundingParticipants([]verifiedSettlementChallengeFunding{
		{Result: settlementChallengeFundingResult{FundingTxHash: duplicateTx, ParticipantSide: "left"}},
		{Result: settlementChallengeFundingResult{FundingTxHash: duplicateTx, ParticipantSide: "right"}},
	})
	if len(participantErrors) == 0 || !strings.Contains(strings.Join(participantErrors, "; "), "funding_tx_hash") {
		t.Fatalf("expected duplicate funding tx refusal, got %v", participantErrors)
	}
}

func TestSettlementChallengeHTTPAuthAndReadOnlyRoutes(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
	)

	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "wolo1treasury000000000000000000000000000000", map[string]string{
		payoutAddress: "5000",
		escrowAddress: "5000",
	}, nil, nil)
	cfg.AuthToken = "secret-token"

	handler := cfg.newSettlementHTTPHandler()

	validateRequest := httptest.NewRequest(http.MethodPost, "/settlement/v1/challenges/validate", strings.NewReader("{}"))
	validateRecorder := httptest.NewRecorder()
	handler.ServeHTTP(validateRecorder, validateRequest)
	if validateRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected challenge validate route without auth to be unauthorized, got %d", validateRecorder.Code)
	}

	executeRequest := httptest.NewRequest(http.MethodPost, "/settlement/v1/challenges", strings.NewReader("{}"))
	executeRecorder := httptest.NewRecorder()
	handler.ServeHTTP(executeRecorder, executeRequest)
	if executeRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected challenge execute route without auth to be unauthorized, got %d", executeRecorder.Code)
	}

	readOnlyPaths := []string{
		"/settlement/v1/challenges/funding/txs/not-a-real-hash",
		"/settlement/v1/challenges/funding/deposits?limit=1",
		"/settlement/v1/challenges/example-missing",
		"/settlement/v1/challenges?limit=1&summary_only=1",
	}
	for _, path := range readOnlyPaths {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code == http.StatusUnauthorized {
			t.Fatalf("expected challenge read-only route %s to stay open, got %d", path, recorder.Code)
		}
	}
}

func TestValidateSettlementChallengeRequiresExactBucketAllocation(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
		leftAddress   = "wolo1leftplayer000000000000000000000000000000"
		rightAddress  = "wolo1rightplayer00000000000000000000000000000"
	)

	leftFundingTx := strings.Repeat("C", 64)
	rightFundingTx := strings.Repeat("D", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "1000",
		escrowAddress: "1000",
	}, map[string]mockSettlementTx{
		leftFundingTx: {
			Hash:        leftFundingTx,
			Sender:      leftAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-tight", "", "left", "left-user", "100", "50"),
			Timestamp:   "2026-04-19T11:00:00Z",
		},
		rightFundingTx: {
			Hash:        rightFundingTx,
			Sender:      rightAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-tight", "", "right", "right-user", "100", "50"),
			Timestamp:   "2026-04-19T11:01:00Z",
		},
	}, nil)

	response, err := cfg.validateSettlementChallenge(t.Context(), settlementChallengeRequest{
		SettlementRunID: "challenge-tight-run",
		SourceApp:       "aoe2hdbets",
		ChallengeID:     "challenge-tight",
		Funding: []settlementChallengeFundingInput{
			{FundingTxHash: leftFundingTx, DepositorAddress: leftAddress, ParticipantSide: "left", ParticipantID: "left-user"},
			{FundingTxHash: rightFundingTx, DepositorAddress: rightAddress, ParticipantSide: "right", ParticipantID: "right-user"},
		},
		Transfers: []settlementChallengeTransferInput{
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "guarantee", Reason: "return", ToAddress: leftAddress, AmountUWolo: "50"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "guarantee", Reason: "return", ToAddress: rightAddress, AmountUWolo: "50"},
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "wager", Reason: "payout", ToAddress: leftAddress, AmountUWolo: "100"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "wager", Reason: "payout", ToAddress: leftAddress, AmountUWolo: "90"},
		},
	})
	if err != nil {
		t.Fatalf("validate settlement challenge: %v", err)
	}
	if response.OK || response.FailureCode != "INVALID_CHALLENGE" {
		t.Fatalf("expected invalid challenge bucket allocation, got %+v", response)
	}
	if !strings.Contains(response.Detail, "wager bucket allocates 90 uwolo but funding proves 100 uwolo") {
		t.Fatalf("expected bucket allocation detail, got %q", response.Detail)
	}
}

func TestValidateSettlementChallengeFundingExpectationsAndTreasuryForfeit(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress   = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress   = "wolo1escrow000000000000000000000000000000000"
		leftAddress     = "wolo1leftplayer000000000000000000000000000000"
		rightAddress    = "wolo1rightplayer00000000000000000000000000000"
		treasuryAddress = "wolo1treasury000000000000000000000000000000"
		runID           = "challenge-double-noshow-run"
	)

	leftFundingTx := strings.Repeat("7", 64)
	rightFundingTx := strings.Repeat("8", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, treasuryAddress, map[string]string{
		payoutAddress: "1000",
		escrowAddress: "1000",
	}, map[string]mockSettlementTx{
		leftFundingTx: {
			Hash:        leftFundingTx,
			Sender:      leftAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemoWithSettlementRunID(runID, "aoe2hdbets", "challenge-double-noshow", "", "left", "left-user", "100", "50"),
			Timestamp:   "2026-04-19T12:30:00Z",
		},
		rightFundingTx: {
			Hash:        rightFundingTx,
			Sender:      rightAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemoWithSettlementRunID(runID, "aoe2hdbets", "challenge-double-noshow", "", "right", "right-user", "100", "50"),
			Timestamp:   "2026-04-19T12:31:00Z",
		},
	}, nil)

	buildRequest := func() settlementChallengeRequest {
		return settlementChallengeRequest{
			SettlementRunID: runID,
			SourceApp:       "aoe2hdbets",
			ChallengeID:     "challenge-double-noshow",
			TreasuryAddress: treasuryAddress,
			Funding: []settlementChallengeFundingInput{
				{
					FundingTxHash:       leftFundingTx,
					DepositorAddress:    leftAddress,
					SettlementRunID:     runID,
					ParticipantSide:     "left",
					ParticipantID:       "left-user",
					ExpectedAmountUWolo: "150",
					WagerUWolo:          "100",
					GuaranteeUWolo:      "50",
				},
				{
					FundingTxHash:       rightFundingTx,
					DepositorAddress:    rightAddress,
					SettlementRunID:     runID,
					ParticipantSide:     "right",
					ParticipantID:       "right-user",
					ExpectedAmountUWolo: "150",
					WagerUWolo:          "100",
					GuaranteeUWolo:      "50",
				},
			},
			Transfers: []settlementChallengeTransferInput{
				{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "guarantee", Reason: "treasury", ToAddress: treasuryAddress, AmountUWolo: "50"},
				{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "guarantee", Reason: "treasury", ToAddress: treasuryAddress, AmountUWolo: "50"},
				{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "wager", Reason: "refund", ToAddress: leftAddress, AmountUWolo: "100"},
				{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "wager", Reason: "refund", ToAddress: rightAddress, AmountUWolo: "100"},
			},
		}
	}

	response, err := cfg.validateSettlementChallenge(t.Context(), buildRequest())
	if err != nil {
		t.Fatalf("validate double no-show challenge settlement: %v", err)
	}
	if !response.OK || response.Status != "validated" {
		t.Fatalf("expected valid double no-show settlement plan, got %+v", response)
	}
	if response.Funding[0].SettlementRunID != runID || response.RequestedTotalUWolo != "300" {
		t.Fatalf("expected settlement-run funding proof and full requested total, got %+v", response)
	}

	wrongWager := buildRequest()
	wrongWager.Funding[0].WagerUWolo = "99"
	mismatch, err := cfg.validateSettlementChallenge(t.Context(), wrongWager)
	if err != nil {
		t.Fatalf("validate mismatch challenge settlement: %v", err)
	}
	if mismatch.OK ||
		mismatch.FailureCode != "INVALID_CHALLENGE" ||
		len(mismatch.Funding) == 0 ||
		!strings.Contains(mismatch.Funding[0].Detail, "wager_uwolo") {
		t.Fatalf("expected wager funding expectation mismatch, got %+v", mismatch)
	}

	wrongTreasury := buildRequest()
	wrongTreasury.Transfers[0].ToAddress = leftAddress
	treasuryMismatch, err := cfg.validateSettlementChallenge(t.Context(), wrongTreasury)
	if err != nil {
		t.Fatalf("validate treasury mismatch challenge settlement: %v", err)
	}
	if treasuryMismatch.OK || treasuryMismatch.Transfers[0].FailureCode != "INVALID_TREASURY_ROUTE" {
		t.Fatalf("expected explicit treasury route failure, got %+v", treasuryMismatch)
	}
}

func TestValidateSettlementChallengePlayedMatchPlan(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
		leftAddress   = "wolo1leftplayer000000000000000000000000000000"
		rightAddress  = "wolo1rightplayer00000000000000000000000000000"
	)

	leftFundingTx := strings.Repeat("E", 64)
	rightFundingTx := strings.Repeat("F", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "1000",
		escrowAddress: "1000",
	}, map[string]mockSettlementTx{
		leftFundingTx: {
			Hash:        leftFundingTx,
			Sender:      leftAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-played", "", "left", "left-user", "100", "50"),
			Timestamp:   "2026-04-19T12:00:00Z",
		},
		rightFundingTx: {
			Hash:        rightFundingTx,
			Sender:      rightAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "150",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-played", "", "right", "right-user", "100", "50"),
			Timestamp:   "2026-04-19T12:01:00Z",
		},
	}, nil)

	response, err := cfg.validateSettlementChallenge(t.Context(), settlementChallengeRequest{
		SettlementRunID: "challenge-played-run",
		SourceApp:       "aoe2hdbets",
		ChallengeID:     "challenge-played",
		Note:            "played match settlement",
		Memo:            "played-match",
		Funding: []settlementChallengeFundingInput{
			{FundingTxHash: leftFundingTx, DepositorAddress: leftAddress, ParticipantSide: "left", ParticipantID: "left-user"},
			{FundingTxHash: rightFundingTx, DepositorAddress: rightAddress, ParticipantSide: "right", ParticipantID: "right-user"},
		},
		Transfers: []settlementChallengeTransferInput{
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "guarantee", Reason: "return", ToAddress: leftAddress, AmountUWolo: "50"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "guarantee", Reason: "return", ToAddress: rightAddress, AmountUWolo: "50"},
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "wager", Reason: "release", ToAddress: leftAddress, AmountUWolo: "100"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "wager", Reason: "release", ToAddress: leftAddress, AmountUWolo: "100"},
		},
	})
	if err != nil {
		t.Fatalf("validate played challenge settlement: %v", err)
	}
	if !response.OK || response.Status != "validated" {
		t.Fatalf("expected challenge validation success, got %+v", response)
	}
	if response.FundingTotalUWolo != "300" || response.RequestedTotalUWolo != "300" {
		t.Fatalf("unexpected challenge totals: %+v", response)
	}
	if len(response.BucketTotals) != 2 {
		t.Fatalf("expected wager and guarantee bucket totals, got %+v", response.BucketTotals)
	}
	if response.BucketTotals[0].Bucket != settlementChallengeBucketWager || response.BucketTotals[0].RequestedUWolo != "200" {
		t.Fatalf("unexpected wager totals: %+v", response.BucketTotals)
	}
	if response.BucketTotals[1].Bucket != settlementChallengeBucketGuarantee || response.BucketTotals[1].RequestedUWolo != "100" {
		t.Fatalf("unexpected guarantee totals: %+v", response.BucketTotals)
	}
	if response.Run == nil || !response.Run.OK {
		t.Fatalf("expected nested payout run validation success, got %+v", response.Run)
	}
}

func TestBuildAndExecuteChallengeTopUp(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress = "wolo1escrow000000000000000000000000000000000"
	)

	topUpTxHash := strings.Repeat("9", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, "", map[string]string{
		payoutAddress: "10",
		escrowAddress: "500",
	}, map[string]mockSettlementTx{
		topUpTxHash: {
			Hash:        topUpTxHash,
			Sender:      escrowAddress,
			Recipient:   payoutAddress,
			AmountUWolo: "290",
			Memo:        "challenge top-up challenge-topup-run",
			Timestamp:   "2026-04-19T13:00:00Z",
		},
	}, map[string]string{
		payoutAddress + "|290uwolo|challenge top-up challenge-topup-run": topUpTxHash,
	})
	cfg.EscrowAutoTopUp = true

	plan, err := cfg.buildChallengeTopUpPlan(t.Context(), "challenge-topup-run", settlementRunResponse{
		RequestedTotalUWolo:      "300",
		PayoutBalanceBeforeUWolo: "10",
		PayoutBalanceBeforeWolo:  formatDisplayAmount("10"),
	})
	if err != nil {
		t.Fatalf("build challenge top-up plan: %v", err)
	}
	if plan == nil || !plan.Required || !plan.Possible || plan.AmountUWolo != "290" {
		t.Fatalf("unexpected top-up plan: %+v", plan)
	}

	executed, err := cfg.executeChallengeTopUp(t.Context(), "challenge-topup-run", *plan)
	if err != nil {
		t.Fatalf("execute challenge top-up: %v", err)
	}
	if executed.Response == nil || !executed.Response.OK || executed.Response.SignerRole != "escrow" {
		t.Fatalf("unexpected top-up execution response: %+v", executed)
	}
	if executed.Response.TxHash != topUpTxHash || executed.Response.Status != "confirmed" {
		t.Fatalf("unexpected top-up tx result: %+v", executed.Response)
	}
}

func TestExecuteSettlementChallengeOneNoShowIdempotent(t *testing.T) {
	t.Parallel()

	const (
		payoutAddress   = "wolo1payoutaddress000000000000000000000000000"
		escrowAddress   = "wolo1escrow000000000000000000000000000000000"
		leftAddress     = "wolo1leftplayer000000000000000000000000000000"
		rightAddress    = "wolo1rightplayer00000000000000000000000000000"
		treasuryAddress = "wolo1treasury000000000000000000000000000000"
	)

	leftFundingTx := strings.Repeat("1", 64)
	rightFundingTx := strings.Repeat("2", 64)
	leftGuaranteeTx := strings.Repeat("3", 64)
	rightGuaranteeTx := strings.Repeat("4", 64)
	leftRefundTx := strings.Repeat("5", 64)
	rightRefundTx := strings.Repeat("6", 64)
	cfg := newTestChallengeSettlementConfig(t, payoutAddress, escrowAddress, treasuryAddress, map[string]string{
		payoutAddress: "1000",
		escrowAddress: "1000",
	}, map[string]mockSettlementTx{
		leftFundingTx: {
			Hash:        leftFundingTx,
			Sender:      leftAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "160",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-noshow", "", "left", "left-user", "100", "60"),
			Timestamp:   "2026-04-19T14:00:00Z",
		},
		rightFundingTx: {
			Hash:        rightFundingTx,
			Sender:      rightAddress,
			Recipient:   escrowAddress,
			AmountUWolo: "170",
			Memo:        challengeFundingMemo("aoe2hdbets", "challenge-noshow", "", "right", "right-user", "100", "70"),
			Timestamp:   "2026-04-19T14:01:00Z",
		},
		leftGuaranteeTx: {
			Hash:        leftGuaranteeTx,
			Sender:      payoutAddress,
			Recipient:   leftAddress,
			AmountUWolo: "60",
			Memo:        "left-guarantee-return",
			Timestamp:   "2026-04-19T14:02:00Z",
		},
		rightGuaranteeTx: {
			Hash:        rightGuaranteeTx,
			Sender:      payoutAddress,
			Recipient:   leftAddress,
			AmountUWolo: "70",
			Memo:        "right-guarantee-forfeit",
			Timestamp:   "2026-04-19T14:03:00Z",
		},
		leftRefundTx: {
			Hash:        leftRefundTx,
			Sender:      payoutAddress,
			Recipient:   leftAddress,
			AmountUWolo: "100",
			Memo:        "left-wager-refund",
			Timestamp:   "2026-04-19T14:04:00Z",
		},
		rightRefundTx: {
			Hash:        rightRefundTx,
			Sender:      payoutAddress,
			Recipient:   rightAddress,
			AmountUWolo: "100",
			Memo:        "right-wager-refund",
			Timestamp:   "2026-04-19T14:05:00Z",
		},
	}, map[string]string{
		leftAddress + "|60uwolo|left-guarantee-return":   leftGuaranteeTx,
		leftAddress + "|70uwolo|right-guarantee-forfeit": rightGuaranteeTx,
		leftAddress + "|100uwolo|left-wager-refund":      leftRefundTx,
		rightAddress + "|100uwolo|right-wager-refund":    rightRefundTx,
	})

	request := settlementChallengeRequest{
		SettlementRunID: "challenge-noshow-run",
		SourceApp:       "aoe2hdbets",
		ChallengeID:     "challenge-noshow",
		TreasuryAddress: treasuryAddress,
		Note:            "left checked in, right no-show",
		Memo:            "challenge-noshow",
		Funding: []settlementChallengeFundingInput{
			{FundingTxHash: leftFundingTx, DepositorAddress: leftAddress, ParticipantSide: "left", ParticipantID: "left-user"},
			{FundingTxHash: rightFundingTx, DepositorAddress: rightAddress, ParticipantSide: "right", ParticipantID: "right-user"},
		},
		Transfers: []settlementChallengeTransferInput{
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "guarantee", Reason: "return", ToAddress: leftAddress, AmountUWolo: "60", Memo: "left-guarantee-return"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "guarantee", Reason: "forfeit", ToAddress: leftAddress, AmountUWolo: "70", Memo: "right-guarantee-forfeit"},
			{ParticipantSide: "left", ParticipantID: "left-user", Bucket: "wager", Reason: "refund", ToAddress: leftAddress, AmountUWolo: "100", Memo: "left-wager-refund"},
			{ParticipantSide: "right", ParticipantID: "right-user", Bucket: "wager", Reason: "refund", ToAddress: rightAddress, AmountUWolo: "100", Memo: "right-wager-refund"},
		},
	}

	response, err := cfg.executeSettlementChallenge(t.Context(), request)
	if err != nil {
		t.Fatalf("execute challenge settlement: %v", err)
	}
	if !response.OK || response.Status != "confirmed" {
		t.Fatalf("expected confirmed challenge settlement, got %+v", response)
	}
	if response.ConfirmedTransferCount != 4 || response.ExecutedTransferCount != 4 {
		t.Fatalf("unexpected transfer execution counts: %+v", response)
	}
	if response.RequestedTotalUWolo != "330" || response.ConfirmedTotalUWolo != "330" {
		t.Fatalf("unexpected executed totals: %+v", response)
	}
	if response.Run == nil || response.Run.Status != "confirmed" {
		t.Fatalf("expected confirmed nested run response, got %+v", response.Run)
	}
	if len(response.BucketTotals) != 2 || response.BucketTotals[0].ConfirmedUWolo != "200" || response.BucketTotals[1].ConfirmedUWolo != "130" {
		t.Fatalf("unexpected bucket totals: %+v", response.BucketTotals)
	}

	replayed, err := cfg.executeSettlementChallenge(t.Context(), request)
	if err != nil {
		t.Fatalf("replay challenge settlement: %v", err)
	}
	if !replayed.OK || !replayed.IdempotentReplay || replayed.Status != "confirmed" {
		t.Fatalf("expected idempotent replay, got %+v", replayed)
	}

	audit, err := cfg.auditSettlementChallenge(t.Context(), "challenge-noshow-run")
	if err != nil {
		t.Fatalf("audit challenge settlement: %v", err)
	}
	if !audit.OK {
		t.Fatalf("expected successful challenge audit, got %+v", audit)
	}
	if audit.Summary.WagerFundedUWolo != "200" || audit.Summary.GuaranteeFundedUWolo != "130" || audit.Summary.TransferTxCheckedCount != 4 {
		t.Fatalf("unexpected challenge audit summary: %+v", audit.Summary)
	}

	recordPath := cfg.challengeRecordPath("challenge-noshow-run")
	stored, err := readSettlementChallengeStoredResult(recordPath)
	if err != nil {
		t.Fatalf("read stored challenge settlement: %v", err)
	}
	stored.Response.RequestedTotalUWolo = "999"
	if err := writeSettlementChallengeStoredResult(recordPath, stored); err != nil {
		t.Fatalf("write tampered challenge settlement: %v", err)
	}
	tamperedAudit, err := cfg.auditSettlementChallenge(t.Context(), "challenge-noshow-run")
	if err != nil {
		t.Fatalf("audit tampered challenge settlement: %v", err)
	}
	if tamperedAudit.OK || tamperedAudit.FailureCode != "REQUESTED_TOTAL_MISMATCH" {
		t.Fatalf("expected requested total mismatch audit failure, got %+v", tamperedAudit)
	}
}

func newTestChallengeSettlementConfig(t *testing.T, payoutAddress string, escrowAddress string, treasuryAddress string, balances map[string]string, txs map[string]mockSettlementTx, recipientTxHashes map[string]string) settlementConfig {
	t.Helper()

	cfg := newTestSettlementConfigWithTxs(t, payoutAddress, balances, txs, nil)
	cfg.ExecutablePath = writeFakeSettlementExecutableWithTxsAndKeys(t, map[string]string{
		"payout": payoutAddress,
		"escrow": escrowAddress,
	}, recipientTxHashes)
	cfg.EscrowKeyName = "escrow"
	cfg.EscrowAddress = escrowAddress
	cfg.TreasuryAddress = treasuryAddress
	return cfg
}

func challengeFundingMemo(sourceApp, challengeID, sourceEventID, participantSide, participantID, wagerUWolo, guaranteeUWolo string) string {
	return challengeFundingMemoWithSettlementRunID("", sourceApp, challengeID, sourceEventID, participantSide, participantID, wagerUWolo, guaranteeUWolo)
}

func challengeFundingMemoWithSettlementRunID(settlementRunID, sourceApp, challengeID, sourceEventID, participantSide, participantID, wagerUWolo, guaranteeUWolo string) string {
	values := url.Values{}
	values.Set("source_app", sourceApp)
	if settlementRunID != "" {
		values.Set("settlement_run_id", settlementRunID)
	}
	if challengeID != "" {
		values.Set("challenge_id", challengeID)
	}
	if sourceEventID != "" {
		values.Set("source_event_id", sourceEventID)
	}
	if participantSide != "" {
		values.Set("participant_side", participantSide)
	}
	if participantID != "" {
		values.Set("participant_id", participantID)
	}
	values.Set("wager_uwolo", wagerUWolo)
	values.Set("guarantee_uwolo", guaranteeUWolo)
	return settlementChallengeFundingMemoPrefix + values.Encode()
}

func canonicalAoE2HDBetsChallengeFundingMemo(challengeID, participantSide, wagerUWolo, guaranteeUWolo string) string {
	wager, _ := strconv.ParseUint(wagerUWolo, 10, 64)
	guarantee, _ := strconv.ParseUint(guaranteeUWolo, 10, 64)
	return settlementChallengeFundingMemoPrefix +
		"app=aoe2hdbets" +
		"&sid=" + aoE2HDBetsChallengeSettlementRunID(challengeID) +
		"&cid=" + challengeID +
		"&side=" + participantSide +
		"&w=" + wagerUWolo +
		"&g=" + guaranteeUWolo +
		"&t=" + strconv.FormatUint(wager+guarantee, 10)
}
