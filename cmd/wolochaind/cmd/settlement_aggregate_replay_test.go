package cmd

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAggregateReplayCannotInventConfirmedRunWithoutLeafEvidence(t *testing.T) {
	cfg := newTestSettlementConfig(t, c4Signer, map[string]string{c4Signer: "5000"})
	request := settlementRunRequest{SettlementRunID: "legacy-aggregate", Memo: c4Memo, Payouts: []settlementRunPayoutInput{{RequestID: "leaf", ToAddress: c4Recipient, AmountUWolo: "700"}}}
	normalized, _ := prepareSettlementRunRequest(request)
	record := settlementRunStoredResult{Request: normalized, Fingerprint: hashSettlementRunRequest(normalized), Response: settlementRunResponse{
		OK: true, Status: "confirmed", SettlementRunID: request.SettlementRunID, ConfirmedPayoutCount: 1, ConfirmedTotalUWolo: "700"}}
	path := cfg.runRecordPath(request.SettlementRunID)
	if err := writeSettlementRunStoredResult(path, record); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	got, err := cfg.executeSettlementRun(t.Context(), request)
	if err != nil || got.OK || got.Status != "unverifiable" || got.Retryable || !got.IdempotentReplay || got.ConfirmedPayoutCount != 0 || got.ConfirmedTotalUWolo == "700" {
		t.Fatalf("aggregate cache invented a payment: %+v err=%v", got, err)
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("replay rewrote historical aggregate")
	}
	if entries, err := os.ReadDir(filepath.Join(cfg.StateDir, "requests")); err == nil && len(entries) != 0 {
		t.Fatal("replay attempted fresh leaf execution")
	}
}

func TestAggregateReplayCannotOverrideInvalidChallengeWithConfirmedCache(t *testing.T) {
	cfg := settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID}
	request := settlementChallengeRequest{SettlementRunID: "legacy-challenge-cache", SourceApp: "fixture", ChallengeID: "fixture"}
	plan, err := cfg.buildSettlementChallengePlan(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	record := settlementChallengeStoredResult{Request: plan.Normalized, Fingerprint: hashSettlementChallengeRequest(plan.Normalized), Response: settlementChallengeResponse{
		OK: true, Status: "confirmed", SettlementRunID: request.SettlementRunID, ConfirmedTransferCount: 1, ConfirmedTotalUWolo: "700",
		Run: &settlementRunResponse{OK: true, Status: "confirmed", ConfirmedPayoutCount: 1, ConfirmedTotalUWolo: "700"}}}
	path := cfg.challengeRecordPath(request.SettlementRunID)
	if err := writeSettlementChallengeStoredResult(path, record); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	got, err := cfg.executeSettlementChallenge(t.Context(), request)
	if err != nil || got.OK || got.Status != "unverifiable" || got.Retryable || !got.IdempotentReplay || got.ConfirmedTransferCount != 0 ||
		(got.Run != nil && (got.Run.OK || got.Run.ConfirmedPayoutCount != 0)) {
		t.Fatalf("challenge cache invented a payment: %+v err=%v", got, err)
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("replay rewrote historical challenge")
	}
}

func TestAggregateJournalsRejectAliasSymlinkAndOversizeButPreserveLargeRecords(t *testing.T) {
	readers := map[string]func(string) error{
		"run":       func(p string) error { _, err := readSettlementRunStoredResult(p); return err },
		"challenge": func(p string) error { _, err := readSettlementChallengeStoredResult(p); return err },
	}
	for name, read := range readers {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			path := filepath.Join(root, "record.json")
			for _, raw := range []string{`{"response":{"ok":false},"Response":{"ok":true,"status":"confirmed"}}`, strings.Repeat(" ", 16<<20) + `{}`} {
				if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
					t.Fatal(err)
				}
				if err := read(path); err == nil {
					t.Fatal("ambiguous or oversized aggregate admitted")
				}
			}
			if err := os.WriteFile(path, []byte(`{}`), 0600); err != nil {
				t.Fatal(err)
			}
			linked := filepath.Join(root, "linked.json")
			if err := os.Symlink(path, linked); err != nil {
				t.Fatal(err)
			}
			if err := read(linked); err == nil {
				t.Fatal("linked aggregate admitted")
			}
			// Aggregates can legitimately exceed the leaf journal's 64KiB budget.
			raw, err := json.Marshal(map[string]any{"response": map[string]any{"detail": strings.Repeat("x", 128<<10)}})
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
			if err := read(path); err != nil {
				t.Fatalf("large bounded aggregate rejected: %v", err)
			}
		})
	}
}

func aggregateReceiptFixture(t *testing.T) (settlementConfig, settlementRunStoredResult) {
	t.Helper()
	cfg := settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID}
	request := settlementRunRequest{SettlementRunID: "current-aggregate", Memo: c4Memo, Payouts: []settlementRunPayoutInput{{RequestID: "current-leaf", ToAddress: c4Recipient, AmountUWolo: "700"}}}
	normalized, _ := prepareSettlementRunRequest(request)
	p := normalized.Payouts[0]
	leaf := normalizedSettlementRequest{RequestID: p.RequestID, ToAddress: p.ToAddress, AmountUWolo: p.AmountUWolo, Memo: p.Memo, SignerRole: normalized.SignerRole}
	if err := cfg.claimSettlementConfirmation(t.Context(), leaf, c4Signer, c4TxHash, 0); err != nil {
		t.Fatal(err)
	}
	response := settlementExecuteResponse{OK: true, Status: "confirmed", ConfirmationStatus: "confirmed", RequestID: leaf.RequestID, ChainID: cfg.ChainID, SignerRole: leaf.SignerRole, SignerAddress: c4Signer, ToAddress: leaf.ToAddress, AmountUWolo: leaf.AmountUWolo, AmountWolo: formatDisplayAmount(leaf.AmountUWolo), TxHash: c4TxHash}
	if err := cfg.writeSettlementRecord(cfg.requestRecordPath(leaf.RequestID), leaf, c4Signer, response); err != nil {
		t.Fatal(err)
	}
	run := finalizeSettlementRunResponse(settlementRunResponse{SettlementRunID: normalized.SettlementRunID, Memo: normalized.Memo, SignerRole: normalized.SignerRole, SignerAddress: c4Signer, Payouts: []settlementRunPayoutResult{settlementRunPayoutResultFromExecuteResponse(p, response)}})
	return cfg, settlementRunStoredResult{Request: normalized, Fingerprint: hashSettlementRunRequest(normalized), Response: run}
}

func TestAggregateConfirmedReplayRequiresConservedOwnedLeafProofs(t *testing.T) {
	for _, kind := range []string{"current-valid", "missing-receipt", "missing-leaf", "wrong-hash", "wrong-recipient", "wrong-role", "wrong-memo", "wrong-total", "wrong-display-total", "wrong-display-leaf", "wrong-count", "wrong-fingerprint", "duplicate-leaf", "partial-laundering"} {
		t.Run(kind, func(t *testing.T) {
			cfg, record := aggregateReceiptFixture(t)
			switch kind {
			case "missing-receipt":
				if err := os.Remove(filepath.Join(cfg.StateDir, "confirmation-receipts", c4TxHash+"-0.json")); err != nil {
					t.Fatal(err)
				}
			case "missing-leaf":
				if err := os.Remove(cfg.requestRecordPath(record.Request.Payouts[0].RequestID)); err != nil {
					t.Fatal(err)
				}
			case "wrong-hash":
				record.Response.Payouts[0].TxHash = strings.Repeat("C", 64)
			case "wrong-recipient":
				record.Response.Payouts[0].ToAddress = c4Signer
			case "wrong-role":
				record.Response.Payouts[0].SignerRole = settlementEscrowSignerRole
			case "wrong-memo":
				record.Response.Payouts[0].Memo = "foreign"
			case "wrong-total":
				record.Response.ConfirmedTotalUWolo = "701"
			case "wrong-display-total":
				record.Response.ConfirmedTotalWolo = "999999"
			case "wrong-display-leaf":
				record.Response.Payouts[0].AmountWolo = "999999"
			case "wrong-count":
				record.Response.ConfirmedPayoutCount = 2
			case "wrong-fingerprint":
				record.Fingerprint = strings.Repeat("0", 64)
			case "duplicate-leaf":
				record.Response.Payouts = append(record.Response.Payouts, record.Response.Payouts[0])
			case "partial-laundering":
				record.Response.OK = false
				record.Response.Status = "partial"
				record.Response.Payouts[0].TxHash = strings.Repeat("B", 64)
			}
			// No RPC endpoint or signer is configured: this path must be read-only.
			held := cfg.guardSettlementRunStoredReplay(t.Context(), record)
			if kind == "current-valid" {
				if held != nil {
					t.Fatalf("valid owned aggregate failed replay: %+v", held)
				}
				return
			}
			if held == nil || held.OK || held.Retryable || held.Status != "unverifiable" || held.ConfirmedPayoutCount != 0 || held.ConfirmedTotalUWolo != "" {
				t.Fatalf("unverified aggregate retained financial success: %+v", held)
			}
			for _, p := range held.Payouts {
				if p.OK || p.Status == "confirmed" || p.ConfirmationStatus == "confirmed" || p.Retryable {
					t.Fatalf("nested success survived: %+v", p)
				}
			}
		})
	}
}

func TestAggregateReplayCannotRetryMissingLeafUnderRetryableCache(t *testing.T) {
	cfg, record := aggregateReceiptFixture(t)
	request := settlementRunRequest{SettlementRunID: record.Request.SettlementRunID, Memo: c4Memo, Payouts: []settlementRunPayoutInput{{RequestID: record.Request.Payouts[0].RequestID, ToAddress: c4Recipient, AmountUWolo: "700"}}}
	record.Response.Payouts[0].Retryable = true
	record.Response.Retryable = true
	if err := os.Remove(cfg.requestRecordPath(record.Request.Payouts[0].RequestID)); err != nil {
		t.Fatal(err)
	}
	path := cfg.runRecordPath(request.SettlementRunID)
	if err := writeSettlementRunStoredResult(path, record); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	got, err := cfg.executeSettlementRun(t.Context(), request)
	if err != nil || got.OK || got.Status != "unverifiable" || got.Retryable || !got.IdempotentReplay {
		t.Fatalf("retryable cache bypassed evidence: %+v %v", got, err)
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("ambiguous cache was rewritten")
	}
	if _, err := os.Stat(cfg.requestRecordPath(record.Request.Payouts[0].RequestID)); !os.IsNotExist(err) {
		t.Fatal("missing leaf was executed again")
	}
}

func TestAggregateConfirmedReplayRefusesFoldedForeignOwnershipHistory(t *testing.T) {
	cfg, record := aggregateReceiptFixture(t)
	raw := `{"request":{"request_id":"foreign"},"response":{"tx_hash":"` + c4TxHash + `"},"Response":{"tx_hash":"` + strings.Repeat("B", 64) + `"}}`
	if err := os.WriteFile(cfg.requestRecordPath("foreign"), []byte(raw), 0600); err != nil {
		t.Fatal(err)
	}
	if held := cfg.guardSettlementRunStoredReplay(t.Context(), record); held == nil || held.OK {
		t.Fatal("foreign effect owner was hidden by a JSON alias")
	}
	req := normalizedSettlementRequest{RequestID: "new-owner", ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo, SignerRole: settlementSignerRole}
	if err := cfg.claimSettlementConfirmation(t.Context(), req, c4Signer, c4TxHash, 0); err == nil {
		t.Fatal("ambiguous foreign history allowed receipt acquisition")
	}
}
