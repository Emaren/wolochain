package cmd

import "testing"

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
