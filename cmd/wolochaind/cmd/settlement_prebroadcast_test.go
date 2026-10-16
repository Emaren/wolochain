package cmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func prebroadcastTestRequest() normalizedSettlementRequest {
	return normalizedSettlementRequest{
		RequestID: "payout:prebroadcast-proof",
		ToAddress: "wolo1recipient",
		AmountUWolo: "12000000",
		Memo: "prebroadcast-c4b",
		SignerRole: settlementSignerRole,
	}
}

func TestPrebroadcastHoldIsDurablyVisibleAndNeverRetryable(t *testing.T) {
	t.Parallel()
	cfg := settlementConfig{StateDir: t.TempDir(), ChainID: "wolo-1"}
	request := prebroadcastTestRequest()
	path := cfg.requestRecordPath(request.RequestID)
	signer := "wolo1signer"
	if err := cfg.writeSettlementPrebroadcastHold(path, request, signer); err != nil {
		t.Fatal(err)
	}
	record, err := readSettlementStoredResult(path)
	if err != nil {
		t.Fatal(err)
	}
	if record.Request != request || record.Fingerprint != hashSettlementRequest(request, signer) ||
		record.Response.OK || record.Response.Retryable ||
		record.Response.Status != "unverifiable" ||
		record.Response.ConfirmationStatus != "unverifiable" ||
		record.Response.FailureCode != "BROADCAST_OUTCOME_UNRECORDED" ||
		record.Response.TxHash != "" ||
		record.Response.SignerAddress != signer ||
		record.Response.RequestID != request.RequestID ||
		record.Response.ToAddress != request.ToAddress ||
		record.Response.AmountUWolo != request.AmountUWolo {
		t.Fatalf("hold must be attributable, immutable by replay, and non-retryable: %+v", record)
	}
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("private record mode: %+v, %v", info, err)
	}
	// This is the exact predicate used in both request executors.
	if record.Response.OK || record.Response.TxHash != "" || !record.Response.Retryable {
		// Expected: it must replay the hold instead of signing again.
	} else {
		t.Fatal("a crash-before-final-result would rebroadcast the request")
	}
}

func TestPrebroadcastHoldWorksForEscrowAndPayoutWithoutCrediting(t *testing.T) {
	t.Parallel()
	for _, role := range []string{settlementSignerRole, settlementEscrowSignerRole} {
		t.Run(role, func(t *testing.T) {
			cfg := settlementConfig{StateDir: t.TempDir(), ChainID: "wolo-1"}
			req := prebroadcastTestRequest()
			req.SignerRole = role
			path := cfg.requestRecordPath(req.RequestID)
			if err := cfg.writeSettlementPrebroadcastHold(path, req, "wolo1escrow"); err != nil {
				t.Fatal(err)
			}
			stored, err := readSettlementStoredResult(path)
			if err != nil || stored.Request.SignerRole != role || stored.Response.SignerRole != role ||
				stored.Response.OK || stored.Response.Retryable || stored.Response.TxHash != "" {
				t.Fatalf("ambiguous %s transfer may not receive payout authority: %+v %v", role, stored, err)
			}
		})
	}
}

func TestPrebroadcastHoldRejectsUnwritableRecordWithoutFinancialSideEffects(t *testing.T) {
	t.Parallel()
	cfg := settlementConfig{StateDir: t.TempDir(), ChainID: "wolo-1"}
	request := prebroadcastTestRequest()
	path := cfg.requestRecordPath(request.RequestID)
	if err := os.MkdirAll(path, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := cfg.writeSettlementPrebroadcastHold(path, request, "wolo1signer"); err == nil {
		t.Fatal("renaming a durable marker over a directory must abort before broadcasting")
	}
}

func TestBothBankBroadcastersRequireDurableHoldInSource(t *testing.T) {
	t.Parallel()
	for _, file := range []string{"settlement.go", "settlement_challenge.go"} {
		data, err := os.ReadFile(filepath.Join(".", file))
		if err != nil {
			t.Fatal(err)
		}
		text := string(data)
		h := strings.Index(text, "if err := cfg.writeSettlementPrebroadcastHold(recordPath, normalized, signerAddress); err != nil {")
		b := strings.Index(text, "result := cfg.broadcastPayout(ctx, normalized, signerAddress)")
		if file == "settlement_challenge.go" {
			b = strings.Index(text, "result := cfg.broadcastEscrowTransfer(ctx, normalized, signerAddress)")
		}
		if h < 0 || b < 0 || h >= b {
			t.Fatalf("%s must persist hold before any external transfer", file)
		}
	}
}

func TestPrebroadcastWriterSyncsFileAndContainingDirectory(t *testing.T) {
	t.Parallel()
	data, err := os.ReadFile("settlement_prebroadcast.go")
	if err != nil {
		t.Fatal(err)
	}
	text := string(data)
	for _, must := range []string{
		"file.Sync()", "os.Rename(tmp, path)", "parent.Sync()", "return parent.Sync()",
		"defer os.Remove(tmp)", "file.Chmod(0o600)",
	} {
		if !strings.Contains(text, must) {
			t.Fatalf("crash-durability prerequisite absent: %s", must)
		}
	}
}

func TestUncertainBroadcastNeverReopensPaymentRetry(t *testing.T) {
	t.Parallel()
	for _, state := range []settlementExecuteResponse{
		{Status: "failed", Retryable: true, FailureCode: "RPC_UNREACHABLE"},
		{Status: "failed", Retryable: true, FailureCode: "BROADCAST_ERROR"},
		{Status: "failed", Retryable: false, FailureCode: "UNKNOWN_ERROR"},
	} {
		got := preserveUnresolvedSettlementBroadcast(state)
		if got.OK || got.Retryable || got.TxHash != "" ||
			got.Status != "unverifiable" || got.ConfirmationStatus != "unverifiable" ||
			got.FailureCode != "BROADCAST_OUTCOME_UNRECORDED" {
			t.Fatalf("ambiguous CLI result must remain held after signer command: %+v", got)
		}
	}
}

func TestKnownBroadcastHashStillCannotBeRetried(t *testing.T) {
	t.Parallel()
	hash := strings.Repeat("A", 64)
	confirmed := preserveUnresolvedSettlementBroadcast(settlementExecuteResponse{
		Status: "accepted", OK: true, Retryable: true, TxHash: hash,
		ConfirmationStatus: "pending",
	})
	if !confirmed.OK || confirmed.Retryable || confirmed.TxHash != hash ||
		confirmed.Status != "accepted" || confirmed.ConfirmationStatus != "pending" {
		t.Fatalf("canonical accepted hash altered unexpectedly: %+v", confirmed)
	}
}

func TestBothBankBroadcastersPreserveUncertainResultBeforeFinalStorage(t *testing.T) {
	t.Parallel()
	for _, name := range []string{"settlement.go", "settlement_challenge.go"} {
		raw, err := os.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		source := string(raw)
		a := strings.Index(source, "result = preserveUnresolvedSettlementBroadcast(result)")
		b := strings.Index(source, "if err := cfg.writeSettlementRecord(recordPath, normalized, signerAddress, result); err != nil {")
		if a < 0 || b <= a {
			t.Fatalf("%s must preserve a nonretryable unknown outcome before storing", name)
		}
	}
}
