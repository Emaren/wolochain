package cmd

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func receiptTestRequest(id string) normalizedSettlementRequest {
	return normalizedSettlementRequest{
		RequestID: id, ToAddress: "wolo1recipient", AmountUWolo: "7",
		Memo: "same memo", SignerRole: settlementSignerRole,
	}
}

func receiptTestConfig(t *testing.T) settlementConfig {
	t.Helper()
	return settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID}
}

func receiptTestPath(cfg settlementConfig, hash string, ordinal string) string {
	return filepath.Join(cfg.StateDir, "confirmation-receipts", hash+"-"+ordinal+".json")
}

func TestSettlementReceiptSingleUseAndOwnerReplay(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	hash := strings.Repeat("A", 64)
	request := receiptTestRequest("payout:first")
	claim := func(request normalizedSettlementRequest) error {
		return cfg.claimSettlementConfirmation(t.Context(), request, "wolo1signer", hash, 1)
	}
	if err := claim(request); err != nil {
		t.Fatal(err)
	}
	if err := claim(request); err != nil {
		t.Fatalf("same owner replay: %v", err)
	}
	if err := claim(receiptTestRequest("payout:second")); !errors.Is(err, errSettlementReceiptConflict) {
		t.Fatalf("same effect cannot pay a different obligation even with identical details: %v", err)
	}
	for _, change := range []struct {
		name string
		edit func(*normalizedSettlementRequest)
	}{
		{"recipient", func(r *normalizedSettlementRequest) { r.ToAddress = "wolo1other" }},
		{"amount", func(r *normalizedSettlementRequest) { r.AmountUWolo = "8" }},
		{"memo", func(r *normalizedSettlementRequest) { r.Memo = "other" }},
		{"role", func(r *normalizedSettlementRequest) { r.SignerRole = settlementEscrowSignerRole }},
	} {
		t.Run(change.name, func(t *testing.T) {
			altered := request
			change.edit(&altered)
			if err := claim(altered); !errors.Is(err, errSettlementReceiptConflict) {
				t.Fatalf("owner context changed: %v", err)
			}
		})
	}
	if err := cfg.claimSettlementConfirmation(t.Context(), request, "wolo1othersigner", hash, 1); !errors.Is(err, errSettlementReceiptConflict) {
		t.Fatalf("different signer must not acquire same effect: %v", err)
	}
	info, err := os.Stat(receiptTestPath(cfg, hash, "1"))
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("receipt mode: %v, %v", info, err)
	}
}

func TestSettlementReceiptPreservesDistinctEffectOrdinals(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	hash := strings.Repeat("B", 64)
	if err := cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest("payout:first"), "wolo1signer", hash, 0); err != nil {
		t.Fatal(err)
	}
	if err := cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest("payout:second"), "wolo1signer", hash, 1); err != nil {
		t.Fatalf("distinct effects must not collapse to one receipt: %v", err)
	}
}

func TestSettlementReceiptPayoutOwnerIgnoresOptionalRESTEventOrder(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	hash := strings.Repeat("9", 64)
	messageIndex := 0 // strict v1 binds exactly one actual MsgSend and one uwolo coin
	for _, observation := range []struct {
		requestID                    string
		eventIndex                   int
		wantStatus, wantConfirmation string
	}{
		// Per-message REST logs omit the ante fee; fallback top-level events
		// include it. That optional representation can change a display ordinal
		// but must never grant a second payment receipt for the same MsgSend.
		{"payout:first", 0, "confirmed", "confirmed"},
		{"payout:second", 1, "accepted", "unverifiable"},
	} {
		request := receiptTestRequest(observation.requestID)
		result := settlementLookupResponse{
			Status: "confirmed", OK: true, Found: true, TxSuccess: true,
			MatchedExpected: true, MatchedTransferIndex: &observation.eventIndex,
			ReceiptTransferIndex: &messageIndex,
		}
		response := settlementExecuteResponse{TxHash: hash}
		cfg.applySettlementConfirmation(t.Context(), &response, request, "wolo1signer", &result, nil)
		if response.Status != observation.wantStatus || response.ConfirmationStatus != observation.wantConfirmation || response.Retryable {
			t.Fatalf("optional event order changed unique payout ownership: %+v", response)
		}
	}
}

func TestSettlementReceiptConcurrentOwners(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	hash := strings.Repeat("C", 64)
	start := make(chan struct{})
	results := make(chan error, 2)
	var wg sync.WaitGroup
	for _, id := range []string{"payout:first", "payout:second"} {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			<-start
			results <- cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest(id), "wolo1signer", hash, 0)
		}(id)
	}
	close(start)
	wg.Wait()
	close(results)
	successes := 0
	for err := range results {
		if err == nil {
			successes++
		} else if !errors.Is(err, errSettlementReceiptBusy) && !errors.Is(err, errSettlementReceiptConflict) {
			t.Fatalf("unexpected claim failure: %v", err)
		}
	}
	if successes != 1 {
		t.Fatalf("exactly one obligation can acquire this effect, got %d", successes)
	}
}

func TestSettlementReceiptLegacyHashOwnership(t *testing.T) {
	t.Parallel()
	for _, status := range []string{"accepted", "confirmed", "failed", "unverifiable"} {
		t.Run(status, func(t *testing.T) {
			cfg := receiptTestConfig(t)
			hash := strings.Repeat("D", 64)
			request := receiptTestRequest("payout:legacy")
			signer := "wolo1signer"
			if err := cfg.writeSettlementRecord(cfg.requestRecordPath(request.RequestID), request, signer, settlementExecuteResponse{
				Status: status, RequestID: request.RequestID, TxHash: strings.ToLower(hash), SignerAddress: signer,
			}); err != nil {
				t.Fatal(err)
			}
			if err := cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest("payout:new"), signer, hash, 4); !errors.Is(err, errSettlementReceiptConflict) {
				t.Fatalf("legacy hash with unknown ordinal must reserve every effect regardless status: %v", err)
			}
			if err := cfg.claimSettlementConfirmation(t.Context(), request, signer, hash, 4); err != nil {
				t.Fatalf("same legacy owner with exact context: %v", err)
			}
		})
	}
}

func TestSettlementReceiptChecksHistoryOnReplay(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	hash := strings.Repeat("E", 64)
	request := receiptTestRequest("payout:first")
	if err := cfg.claimSettlementConfirmation(t.Context(), request, "wolo1signer", hash, 0); err != nil {
		t.Fatal(err)
	}
	other := receiptTestRequest("payout:legacy-other")
	if err := cfg.writeSettlementRecord(cfg.requestRecordPath(other.RequestID), other, "wolo1signer", settlementExecuteResponse{
		TxHash: hash, SignerAddress: "wolo1signer", Status: "accepted",
	}); err != nil {
		t.Fatal(err)
	}
	if err := cfg.claimSettlementConfirmation(t.Context(), request, "wolo1signer", hash, 0); !errors.Is(err, errSettlementReceiptConflict) {
		t.Fatalf("receipt replay must not hide conflicting legacy history: %v", err)
	}
}

func TestSettlementReceiptRefusesUncertainLocalState(t *testing.T) {
	t.Parallel()
	for _, kind := range []string{"malformed_receipt", "malformed_history", "unfinished_legacy_write", "oversize_history", "symlink_history", "bad_fingerprint", "stale_lock"} {
		t.Run(kind, func(t *testing.T) {
			cfg := receiptTestConfig(t)
			hash := strings.Repeat("F", 64)
			request := receiptTestRequest("payout:first")
			path := receiptTestPath(cfg, hash, "0")
			if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
				t.Fatal(err)
			}
			if err := os.MkdirAll(filepath.Join(cfg.StateDir, "requests"), 0o700); err != nil {
				t.Fatal(err)
			}
			expected := errSettlementReceiptState
			switch kind {
			case "malformed_receipt":
				if err := os.WriteFile(path, []byte("{"), 0o600); err != nil {
					t.Fatal(err)
				}
			case "malformed_history":
				if err := os.WriteFile(cfg.requestRecordPath("bad"), []byte("{}"), 0o600); err != nil {
					t.Fatal(err)
				}
			case "unfinished_legacy_write":
				if err := os.WriteFile(cfg.requestRecordPath("bad")+".tmp", []byte("{"), 0o600); err != nil {
					t.Fatal(err)
				}
			case "oversize_history":
				if err := os.WriteFile(cfg.requestRecordPath("bad"), []byte(strings.Repeat("x", settlementReceiptMaxRecordSize+1)), 0o600); err != nil {
					t.Fatal(err)
				}
			case "symlink_history":
				outside := filepath.Join(t.TempDir(), "outside.json")
				if err := os.WriteFile(outside, []byte("{}"), 0o600); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(outside, cfg.requestRecordPath("bad")); err != nil {
					t.Fatal(err)
				}
			case "bad_fingerprint":
				if err := writeSettlementStoredResult(cfg.requestRecordPath(request.RequestID), settlementStoredResult{
					Request: request, Fingerprint: "incorrect", Response: settlementExecuteResponse{TxHash: hash, SignerAddress: "wolo1signer"},
				}); err != nil {
					t.Fatal(err)
				}
				expected = errSettlementReceiptConflict
			case "stale_lock":
				lockPath := path + ".lock"
				if err := os.WriteFile(lockPath, nil, 0o600); err != nil {
					t.Fatal(err)
				}
				old := time.Now().Add(-365 * 24 * time.Hour)
				if err := os.Chtimes(lockPath, old, old); err != nil {
					t.Fatal(err)
				}
				expected = errSettlementReceiptBusy
			}
			if err := cfg.claimSettlementConfirmation(t.Context(), request, "wolo1signer", hash, 0); !errors.Is(err, expected) {
				t.Fatalf("uncertain state must not authorize confirmation: got %v, want %v", err, expected)
			}
		})
	}
}

func TestSettlementReceiptCancellationAndInvalidIdentity(t *testing.T) {
	t.Parallel()
	cfg := receiptTestConfig(t)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if err := cfg.claimSettlementConfirmation(ctx, receiptTestRequest("payout:first"), "wolo1signer", strings.Repeat("A", 64), 0); !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled claim: %v", err)
	}
	if entries, err := os.ReadDir(cfg.StateDir); err != nil || len(entries) != 0 {
		t.Fatalf("canceled claim must not write ownership: %v, %v", entries, err)
	}
	for _, hash := range []string{"", "ABC", strings.Repeat("G", 64)} {
		if err := cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest("payout:first"), "wolo1signer", hash, 0); !errors.Is(err, errSettlementReceiptState) {
			t.Fatalf("invalid hash %q: %v", hash, err)
		}
	}
	if err := cfg.claimSettlementConfirmation(t.Context(), receiptTestRequest("payout:first"), "wolo1signer", strings.Repeat("A", 64), -1); !errors.Is(err, errSettlementReceiptState) {
		t.Fatalf("negative ordinal: %v", err)
	}
}
