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
