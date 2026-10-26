package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"

	"github.com/emaren/wolochain/internal/chainjson"
)

var (
	errSettlementReceiptConflict = errors.New("CONFIRMATION_RECEIPT_CONFLICT")
	errSettlementReceiptBusy     = errors.New("CONFIRMATION_RECEIPT_BUSY")
	errSettlementReceiptState    = errors.New("CONFIRMATION_RECEIPT_STATE_UNAVAILABLE")
)

const (
	settlementReceiptVersion       = "wolo.settlement.confirmation.v1"
	settlementReceiptMaxRecordSize = 64 << 10
	settlementReceiptMaxStateBytes = 16 << 20
	settlementReceiptMaxRecords    = 10000
)

type settlementConfirmationReceipt struct {
	Version       string `json:"version"`
	ChainID       string `json:"chain_id"`
	TxHash        string `json:"tx_hash"`
	TransferIndex int    `json:"transfer_index"`
	RequestID     string `json:"request_id"`
	SignerAddress string `json:"signer_address"`
	Fingerprint   string `json:"fingerprint"`
}

// Replaying a newer confirmed result requires its existing durable effect
// owner. Do not create a receipt here: that would retroactively certify a
// historical success that predates exact transaction/effect verification.
func (cfg settlementConfig) verifySettlementConfirmationReplay(ctx context.Context, request normalizedSettlementRequest, signer, txHash string) error {
	txHash = normalizeTxHash(txHash)
	if err := cfg.checkSettlementReceiptHistory(ctx, request, signer, txHash); err != nil {
		return err
	}
	dir, err := os.Open(filepath.Join(cfg.StateDir, "confirmation-receipts"))
	if err != nil {
		return errSettlementReceiptState
	}
	defer dir.Close()
	found, count, size := false, 0, 0
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		entries, readErr := dir.ReadDir(128)
		if readErr != nil && !errors.Is(readErr, io.EOF) {
			return errSettlementReceiptState
		}
		for _, entry := range entries {
			count++
			if count > settlementReceiptMaxRecords {
				return errSettlementReceiptState
			}
			if !strings.HasPrefix(entry.Name(), txHash+"-") {
				continue
			}
			if !strings.HasSuffix(entry.Name(), ".json") || !entry.Type().IsRegular() {
				return errSettlementReceiptState
			}
			data, err := readSettlementReceiptState(filepath.Join(cfg.StateDir, "confirmation-receipts", entry.Name()))
			size += len(data)
			var receipt settlementConfirmationReceipt
			if err != nil || size > settlementReceiptMaxStateBytes || !chainjson.ValidFolded(data) || json.Unmarshal(data, &receipt) != nil {
				return errSettlementReceiptState
			}
			if receipt.Version != settlementReceiptVersion || receipt.ChainID != cfg.ChainID || receipt.TxHash != txHash || receipt.TransferIndex < 0 || entry.Name() != txHash+"-"+strconv.Itoa(receipt.TransferIndex)+".json" {
				return errSettlementReceiptState
			}
			if receipt.RequestID == request.RequestID {
				if receipt.SignerAddress != signer || receipt.Fingerprint != hashSettlementRequest(request, signer) {
					return errSettlementReceiptConflict
				}
				found = true
			}
		}
		if errors.Is(readErr, io.EOF) {
			if !found {
				return errSettlementReceiptState
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			return nil
		}
	}
}

// claimSettlementConfirmation reserves one observed bank effect for one durable
// request. Call only AFTER exact transaction/transfer confirmation; this function
// is a local single-use guard, not chain evidence or permission to broadcast.
// Its authority is limited to this service's StateDir. Never delete a receipt or
// stale receipt lock to retry a payment: unresolved ownership must fail closed.
func (cfg settlementConfig) claimSettlementConfirmation(ctx context.Context, request normalizedSettlementRequest, signerAddress, txHash string, transferIndex int) error {
	txHash = normalizeTxHash(txHash)
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if strings.TrimSpace(cfg.StateDir) == "" || cfg.ChainID != settlementCanonicalChainID || len(txHash) != 64 || !isHexHash(txHash) || transferIndex < 0 || !settlementRequestIDPattern.MatchString(request.RequestID) || signerAddress == "" {
		return errSettlementReceiptState
	}
	owner := settlementConfirmationReceipt{
		Version:       settlementReceiptVersion,
		ChainID:       cfg.ChainID,
		TxHash:        txHash,
		TransferIndex: transferIndex,
		RequestID:     request.RequestID,
		SignerAddress: signerAddress,
		Fingerprint:   hashSettlementRequest(request, signerAddress),
	}
	dir := filepath.Join(cfg.StateDir, "confirmation-receipts")
	if os.MkdirAll(dir, 0o700) != nil {
		return errSettlementReceiptState
	}
	info, err := os.Lstat(dir)
	if err != nil || !info.IsDir() || syncSettlementReceiptDirectory(cfg.StateDir) != nil {
		return errSettlementReceiptState
	}
	path := filepath.Join(dir, txHash+"-"+strconv.Itoa(transferIndex)+".json")
	lockPath := path + ".lock"
	lock, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			return errSettlementReceiptBusy
		}
		return errSettlementReceiptState
	}
	if lock.Close() != nil {
		return errSettlementReceiptState
	}
	defer os.Remove(lockPath)

	var existing settlementConfirmationReceipt
	data, err := readSettlementReceiptState(path)
	if err == nil {
		if json.Unmarshal(data, &existing) != nil {
			return errSettlementReceiptState
		}
		if existing != owner {
			return errSettlementReceiptConflict
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return errSettlementReceiptState
	}

	// Existing records predate the receipt registry. Without a trustworthy
	// ordinal, any use of this hash by a different request conservatively owns
	// every effect. Scan even on same-owner replay to detect conflicting history.
	if err := cfg.checkSettlementReceiptHistory(ctx, request, signerAddress, txHash); err != nil {
		return err
	}
	if existing == owner {
		// Re-acknowledge the directory sync if an earlier caller lost its
		// response or encountered a transient failure after rename.
		if syncSettlementReceiptDirectory(dir) != nil {
			return errSettlementReceiptState
		}
		return nil
	}
	if ctx.Err() != nil {
		return ctx.Err()
	}
	payload, err := json.MarshalIndent(owner, "", "  ")
	if err != nil || writeSettlementReceipt(path, append(payload, '\n')) != nil {
		return errSettlementReceiptState
	}
	return nil
}

func (cfg settlementConfig) checkSettlementReceiptHistory(ctx context.Context, request normalizedSettlementRequest, signerAddress, txHash string) error {
	dir, err := os.Open(filepath.Join(cfg.StateDir, "requests"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return errSettlementReceiptState
	}
	defer dir.Close()
	count, size := 0, 0
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		entries, readErr := dir.ReadDir(128)
		if readErr != nil && !errors.Is(readErr, io.EOF) {
			return errSettlementReceiptState
		}
		for _, entry := range entries {
			count++
			if count > settlementReceiptMaxRecords || ctx.Err() != nil {
				if ctx.Err() != nil {
					return ctx.Err()
				}
				return errSettlementReceiptState
			}
			// The legacy writer broadcasts before its temporary-file rename.
			// A leftover request temp file therefore represents unresolved
			// ownership, not evidence that no payment was attempted.
			if strings.HasSuffix(entry.Name(), ".json.tmp") {
				return errSettlementReceiptState
			}
			if !strings.HasSuffix(entry.Name(), ".json") {
				continue
			}
			if !entry.Type().IsRegular() {
				return errSettlementReceiptState
			}
			data, err := readSettlementReceiptState(filepath.Join(cfg.StateDir, "requests", entry.Name()))
			size += len(data)
			if err != nil || size > settlementReceiptMaxStateBytes {
				return errSettlementReceiptState
			}
			var record settlementStoredResult
			if json.Unmarshal(data, &record) != nil || !settlementRequestIDPattern.MatchString(record.Request.RequestID) || entry.Name() != record.Request.RequestID+".json" {
				return errSettlementReceiptState
			}
			if normalizeTxHash(record.Response.TxHash) != txHash {
				continue
			}
			if record.Request != request || record.Response.SignerAddress != signerAddress || record.Fingerprint != hashSettlementRequest(record.Request, record.Response.SignerAddress) {
				return errSettlementReceiptConflict
			}
		}
		if errors.Is(readErr, io.EOF) {
			return nil
		}
	}
}

func readSettlementReceiptState(path string) ([]byte, error) {
	return readSettlementStateBounded(path, settlementReceiptMaxRecordSize)
}

func readSettlementStateBounded(path string, limit int64) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > limit {
		return nil, errSettlementReceiptState
	}
	f, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	opened, err := f.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(info, opened) || opened.Size() > limit {
		return nil, errSettlementReceiptState
	}
	data, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil || int64(len(data)) > limit || len(bytes.TrimSpace(data)) == 0 || !chainjson.ValidFolded(data) {
		return nil, errSettlementReceiptState
	}
	current, statErr := f.Stat()
	if statErr != nil || current.Size() != opened.Size() || !current.ModTime().Equal(opened.ModTime()) {
		return nil, errSettlementReceiptState
	}
	return data, nil
}

// Unlike the historical request writer, receipt ownership must survive an
// acknowledged write before a response can be called confirmed. A crash after
// rename may leave a reservation even when Sync fails; that is a safe refusal.
func writeSettlementReceipt(path string, payload []byte) error {
	f, err := os.CreateTemp(filepath.Dir(path), ".receipt-*.tmp")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err := f.Write(payload); err != nil {
		_ = f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		_ = f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	return syncSettlementReceiptDirectory(filepath.Dir(path))
}

func syncSettlementReceiptDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
