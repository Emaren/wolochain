package cmd

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLegacyReplayCannotPromoteUnverifiedStoredSuccess(t *testing.T) {
	t.Parallel()
	for _, role := range []string{settlementSignerRole, settlementEscrowSignerRole} {
		for _, kind := range []string{"old-confirmed", "missing-hash", "wrong-chain", "wrong-owner", "wrong-amount", "bad-fingerprint", "failed-code", "missing-receipt", "duplicate-response"} {
			t.Run(role+"/"+kind, func(t *testing.T) {
				cfg := settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID}
				request := settlementExecuteRequest{RequestID: "legacy-" + role + "-" + kind, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}
				normalized, err := normalizeSettlementRequest(request)
				if err != nil {
					t.Fatal(err)
				}
				normalized.SignerRole = role
				response := settlementExecuteResponse{OK: true, Status: "confirmed", ConfirmationStatus: "confirmed", RequestID: request.RequestID, ChainID: cfg.ChainID, SignerRole: role, SignerAddress: c4Signer, ToAddress: request.ToAddress, AmountUWolo: request.AmountUWolo, TxHash: c4TxHash}
				record := settlementStoredResult{Request: normalized, Fingerprint: hashSettlementRequest(normalized, c4Signer), Response: response}
				switch kind {
				case "old-confirmed":
					record.Response.ConfirmationStatus = ""
				case "missing-hash":
					record.Response.TxHash = ""
				case "wrong-chain":
					record.Response.ChainID = "other-chain"
				case "wrong-owner":
					record.Response.RequestID = "other-request"
				case "wrong-amount":
					record.Response.AmountUWolo = "701"
				case "bad-fingerprint":
					record.Fingerprint = strings.Repeat("0", 64)
				case "failed-code":
					record.Response.Code = 9
				}
				path := cfg.requestRecordPath(request.RequestID)
				if err := writeSettlementStoredResult(path, record); err != nil {
					t.Fatal(err)
				}
				if kind == "duplicate-response" {
					data, err := os.ReadFile(path)
					if err != nil {
						t.Fatal(err)
					}
					encoded, err := json.Marshal(response)
					if err != nil {
						t.Fatal(err)
					}
					// encoding/json aliases Response to response and silently uses
					// the last member unless the bounded journal reader rejects it.
					data = append([]byte(`{"Response":`+string(encoded)+`,`), data[1:]...)
					if err := os.WriteFile(path, data, 0o600); err != nil {
						t.Fatal(err)
					}
				}
				before, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				execute := cfg.executeSettlement
				if role == settlementEscrowSignerRole {
					execute = cfg.executeEscrowTransfer
				}
				// Intentionally no RPC or executable configured. Replay must
				// return a noncrediting hold without attempting fresh execution.
				got, err := execute(t.Context(), request)
				if err != nil || got.OK || got.Retryable || got.Status == "confirmed" || got.ConfirmationStatus == "confirmed" || got.FailureCode == "" {
					t.Errorf("stored %s success was promoted without valid proof: %+v err=%v", kind, got, err)
				}
				after, err := os.ReadFile(path)
				if err != nil || string(after) != string(before) {
					t.Fatal("read-only quarantine changed historical bytes")
				}
			})
		}
	}
}

func TestSettlementCurrentConfirmedReplayRequiresOriginalEffectOwner(t *testing.T) {
	t.Parallel()
	for _, role := range []string{settlementSignerRole, settlementEscrowSignerRole} {
		t.Run(role, func(t *testing.T) {
			cfg := settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID}
			request := settlementExecuteRequest{RequestID: "current-" + role, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}
			normalized, err := normalizeSettlementRequest(request)
			if err != nil {
				t.Fatal(err)
			}
			normalized.SignerRole = role
			if err := cfg.claimSettlementConfirmation(t.Context(), normalized, c4Signer, c4TxHash, 0); err != nil {
				t.Fatal(err)
			}
			response := settlementExecuteResponse{OK: true, Status: "confirmed", ConfirmationStatus: "confirmed", RequestID: request.RequestID, ChainID: cfg.ChainID, SignerRole: role, SignerAddress: c4Signer, ToAddress: request.ToAddress, AmountUWolo: request.AmountUWolo, TxHash: c4TxHash}
			path := cfg.requestRecordPath(request.RequestID)
			if err := cfg.writeSettlementRecord(path, normalized, c4Signer, response); err != nil {
				t.Fatal(err)
			}
			before, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			execute := cfg.executeSettlement
			if role == settlementEscrowSignerRole {
				execute = cfg.executeEscrowTransfer
			}
			// A new process can replay the established receipt without a signer
			// or network. Source replay does not authenticate chain consensus.
			got, err := execute(t.Context(), request)
			if err != nil || !got.OK || !got.IdempotentReplay || got.Status != "confirmed" || got.Retryable {
				t.Fatalf("valid current replay: %+v %v", got, err)
			}
			other := normalized
			other.RequestID += "-conflict"
			if err := cfg.writeSettlementRecord(cfg.requestRecordPath(other.RequestID), other, c4Signer, response); err != nil {
				t.Fatal(err)
			}
			got, err = execute(t.Context(), request)
			if err != nil || got.OK || got.Retryable || got.FailureCode != "TX_RECEIPT_UNAVAILABLE" {
				t.Fatalf("shared historical hash lost effect ownership: %+v %v", got, err)
			}
			after, err := os.ReadFile(path)
			if err != nil || string(after) != string(before) {
				t.Fatal("confirmation replay rewrote original bytes")
			}
		})
	}
}

func TestLegacyProvenPreflightCanExecuteOnceThenReplayWithoutSigning(t *testing.T) {
	for _, role := range []string{settlementSignerRole, settlementEscrowSignerRole} {
		t.Run(role, func(t *testing.T) {
			cfg := newTestSettlementConfig(t, c4Signer, map[string]string{c4Signer: "10000000", c4EscrowSigner: "10000000"})
			cfg.EscrowKeyName, cfg.EscrowAddress = "escrow", c4EscrowSigner
			fake := writeFakeSettlementExecutableWithTxsAndKeys(t, map[string]string{"payout": c4Signer, "escrow": c4EscrowSigner}, map[string]string{c4Recipient: c4TxHash})
			counter, wrapper := filepath.Join(t.TempDir(), "broadcasts"), filepath.Join(t.TempDir(), "cli.sh")
			if err := os.WriteFile(wrapper, []byte("#!/bin/sh\nif [ \"$1\" = tx ]; then printf 'send\\n' >> '"+counter+"'; fi\nexec /bin/sh '"+fake+"' \"$@\"\n"), 0o700); err != nil {
				t.Fatal(err)
			}
			cfg.ExecutablePath, cfg.ExecutableInterpreter = wrapper, "/bin/sh"
			request := settlementExecuteRequest{RequestID: "safe-preflight-" + role, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}
			normalized, err := normalizeSettlementRequest(request)
			if err != nil {
				t.Fatal(err)
			}
			normalized.SignerRole = role
			signer, code := c4Signer, "PAYOUT_BALANCE_TOO_LOW"
			if role == settlementEscrowSignerRole {
				signer, code = c4EscrowSigner, "ESCROW_BALANCE_TOO_LOW"
			}
			response := settlementExecuteResponse{Status: "failed", FailureCode: code, Retryable: true, RequestID: request.RequestID, ChainID: cfg.ChainID, SignerRole: role, SignerAddress: signer, ToAddress: request.ToAddress, AmountUWolo: request.AmountUWolo}
			if err := cfg.writeSettlementRecord(cfg.requestRecordPath(request.RequestID), normalized, signer, response); err != nil {
				t.Fatal(err)
			}
			execute := cfg.executeSettlement
			if role == settlementEscrowSignerRole {
				execute = cfg.executeEscrowTransfer
			}
			first, err := execute(t.Context(), request)
			if err != nil || !first.OK || first.Retryable || first.IdempotentReplay {
				t.Fatalf("proven preflight retry: %+v %v", first, err)
			}
			second, err := execute(t.Context(), request)
			if err != nil || !second.OK || second.Retryable || !second.IdempotentReplay {
				t.Fatalf("restart replay: %+v %v", second, err)
			}
			data, err := os.ReadFile(counter)
			if err != nil || string(data) != "send\n" {
				t.Fatalf("preflight may execute exactly once: %q %v", data, err)
			}
		})
	}
}
