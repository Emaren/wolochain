package cmd

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// A pre-broadcast hold closes the historical crash window in which a bank
// transaction could reach the network before its request ID existed on disk.
// Until a real chain hash is persisted, the outcome must remain UNVERIFIABLE
// and permanently non-retryable without independent operator reconciliation.
//
// This is not proof a transfer occurred. It intentionally favors a manual
// hold over the possibility of duplicate WOLO transfers.
func (cfg settlementConfig) writeSettlementPrebroadcastHold(path string, request normalizedSettlementRequest, signer string) error {
	record := settlementStoredResult{
		Request: request,
		Fingerprint: hashSettlementRequest(request, signer),
		Response: settlementExecuteResponse{
			OK:                 false,
			Status:             "unverifiable",
			ConfirmationStatus: "unverifiable",
			FailureCode:        "BROADCAST_OUTCOME_UNRECORDED",
			Retryable:          false,
			RequestID:          request.RequestID,
			ChainID:            cfg.ChainID,
			SignerRole:         request.SignerRole,
			SignerAddress:      signer,
			ToAddress:          request.ToAddress,
			AmountUWolo:        request.AmountUWolo,
			AmountWolo:         formatDisplayAmount(request.AmountUWolo),
			Detail:             "Pre-broadcast hold: transfer may or may not have been sent. Never rebroadcast without independent chain and signer reconciliation.",
		},
		UpdatedAt: time.Now().UTC(),
	}
	return writeSettlementDurablePrebroadcastRecord(path, record)
}

// The marker MUST survive an acknowledged return BEFORE calling the signer.
// fsync both the contents and containing directory; otherwise an os.Rename
// alone is not necessarily crash-durable. A failure denies broadcasting.
func writeSettlementDurablePrebroadcastRecord(path string, record settlementStoredResult) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(record, "", "  ")
	if err != nil {
		return err
	}
	file, err := os.CreateTemp(dir, ".settlement-intent-*.tmp")
	if err != nil {
		return err
	}
	tmp := file.Name()
	defer os.Remove(tmp)
	if err := file.Chmod(0o600); err != nil {
		_ = file.Close()
		return err
	}
	if _, err := file.Write(append(payload, '\n')); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	parent, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer parent.Close()
	return parent.Sync()
}
