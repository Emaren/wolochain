package satchelservice

// Opt-in CI test of the ACTUAL clean-build production executables. The SDK
// chain, funds and signed permissions are isolated test authorities. It does
// not enroll a production key, use mainnet, or establish physical independence.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"debug/buildinfo"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/stretchr/testify/require"
)

func TestEscrowServiceProductionExecutables(t *testing.T) {
	signerPath, clientPath := os.Getenv("SATCHEL_C01_SIGNER_EXECUTABLE"), os.Getenv("SATCHEL_C01_CLIENT_EXECUTABLE")
	if signerPath == "" && clientPath == "" {
		t.Skip("requires explicit CI-built production executables and isolated loopback8094")
	}
	for _, mode := range []string{"review_outlives_bank", "expired_permission", "stale_bank_root", "revoked_permission", "confirmed_replay"} {
		t.Run(mode, func(t *testing.T) { testEscrowServiceProductionExecutable(t, signerPath, clientPath, mode) })
	}
}

func testEscrowServiceProductionExecutable(t *testing.T, signerPath, clientPath, mode string) {
	require.True(t, filepath.IsAbs(signerPath))
	require.True(t, filepath.IsAbs(clientPath))
	info, err := buildinfo.ReadFile(signerPath)
	require.NoError(t, err)
	var source, modified string
	for _, s := range info.Settings {
		if s.Key == "vcs.revision" {
			source = s.Value
		}
		if s.Key == "vcs.modified" {
			modified = s.Value
		}
	}
	require.Len(t, source, 40)
	require.Equal(t, "false", modified, "actual executable must come from clean exact source")
	clientInfo, err := buildinfo.ReadFile(clientPath)
	require.NoError(t, err)
	var clientSource, clientModified string
	for _, setting := range clientInfo.Settings {
		if setting.Key == "vcs.revision" {
			clientSource = setting.Value
		}
		if setting.Key == "vcs.modified" {
			clientModified = setting.Value
		}
	}
	require.Equal(t, source, clientSource)
	require.Equal(t, "false", clientModified)
	file, err := os.Open(signerPath)
	require.NoError(t, err)
	raw, err := io.ReadAll(io.LimitReader(file, (512<<20)+1))
	require.NoError(t, err)
	require.NoError(t, file.Close())
	require.LessOrEqual(t, len(raw), 512<<20)
	binaryDigest := custodySHA(raw)
	f := newEscrowServiceFixture(t)
	c := f.custody
	// Release both real keyring leases and the original DB handle. Only the
	// child owns the genuine production engine/keyrings during execution.
	f.service.Close()
	require.NoError(t, c.engine.Close())
	c.native.Close()
	enrollment := f.service.enrollment
	enrollment.SourceCommit = source
	c.config.EscrowSignerEnrollmentSHA256 = custodySHA(custodyWrite(t, c.config.EscrowSignerEnrollmentFile, enrollment))
	custodyWrite(t, c.path, c.config)
	_, configDigest, err := LoadConfig(c.path)
	require.NoError(t, err)
	var global ExecutionPermit
	globalBytes, err := os.ReadFile(c.config.PermitFile)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(globalBytes, &global))
	global.ConfigSHA256, global.BinarySHA256 = configDigest, binaryDigest
	global.IssuedAt, global.ExpiresAt = time.Now().Unix()-1, time.Now().Unix()+120
	key := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, 32))
	global.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(key, PermitMessage(global)))
	globalBytes = custodyWrite(t, c.config.PermitFile, global)
	f.bundle.Review.BuildSHA256, f.bundle.Review.ConfigSHA256, f.bundle.Review.PermitSHA256 = binaryDigest, configDigest, custodySHA(globalBytes)
	// A signed review cannot outlive its authentic bank evidence. Extending it
	// to +110s invalidates a maximum-30s bank proof before intent. Derive the
	// test review's deadline from the genuine native evidence, never a waiver.
	bank, _, err := c.reader.ReadCurrentBankProof(t.Context(), c.config.BettingEscrow)
	require.NoError(t, err)
	f.bundle.Review.IssuedAt = time.Now().Unix() - 1
	f.bundle.Review.ExpiresAt = bank.ExpiresAt().Unix() - 1
	require.Greater(t, f.bundle.Review.ExpiresAt, time.Now().Unix())
	require.False(t, time.Unix(f.bundle.Review.ExpiresAt, 0).After(bank.ExpiresAt()))
	reviewBytes := f.reserve.sign(t, &f.bundle)
	require.NoError(t, os.WriteFile(f.reviewPath, reviewBytes, 0600))
	f.permit.SourceCommit, f.permit.BinarySHA256, f.permit.ConfigSHA256 = source, binaryDigest, configDigest
	f.permit.EnrollmentSHA256, f.permit.ReserveReviewSHA256 = c.config.EscrowSignerEnrollmentSHA256, custodySHA(reviewBytes)
	f.permit.IssuedAt, f.permit.ExpiresAt = time.Now().Unix()-1, time.Now().Unix()+100
	f.writePermit(t)
	approvalPath := filepath.Join(filepath.Dir(c.path), "original-return-approval.json")
	custodyWrite(t, approvalPath, f.approval)
	ctx, cancel := context.WithTimeout(t.Context(), 35*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, signerPath, "--config", c.path)
	logPath := filepath.Join(filepath.Dir(c.path), "actual-executor.log")
	log, err := os.OpenFile(logPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	require.NoError(t, err)
	command.Stdout, command.Stderr = log, log
	require.NoError(t, command.Start())
	t.Cleanup(func() { _ = command.Process.Signal(syscall.SIGTERM); _ = command.Wait(); _ = log.Close() })
	client := &http.Client{Timeout: time.Second, Transport: &http.Transport{Proxy: nil, DisableKeepAlives: true}}
	defer client.CloseIdleConnections()
	ready := false
	for deadline := time.Now().Add(8 * time.Second); time.Now().Before(deadline); {
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:8094/satchel/v1/custody/journal", nil)
		req.Header.Set("Authorization", "Bearer "+testHTTPToken)
		response, err := client.Do(req)
		if err == nil {
			_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 64<<10))
			_ = response.Body.Close()
			if response.StatusCode == 200 {
				ready = true
				break
			}
		}
		time.Sleep(30 * time.Millisecond)
	}
	if !ready {
		contents, _ := os.ReadFile(logPath)
		t.Fatalf("actual enrolled executor did not start: %s", contents)
	}
	counts := func() int { c.chain.mu.Lock(); defer c.chain.mu.Unlock(); return c.chain.broadcasts }
	before := counts()
	if mode != "confirmed_replay" {
		expectedBoundary := "owner_verification"
		switch mode {
		case "review_outlives_bank":
			// Reproduce the exact failing executable fixture, with valid test
			// signatures but a review lifetime beyond authentic bank freshness.
			f.bundle.Review.ExpiresAt = time.Now().Unix() + 110
			expectedBoundary = "reserve_review_outlives_bank"
		case "stale_bank_root":
			f.bundle.Review.CommitBlockHash = strings.Repeat("F", 64)
			expectedBoundary = "reserve_inventory"
		case "expired_permission":
			f.permit.IssuedAt, f.permit.ExpiresAt = time.Now().Unix()-60, time.Now().Unix()-1
		case "revoked_permission":
			expectedBoundary = "owner_permission"
		}
		if mode == "review_outlives_bank" || mode == "stale_bank_root" {
			reviewBytes = f.reserve.sign(t, &f.bundle)
			require.NoError(t, os.WriteFile(f.reviewPath, reviewBytes, 0600))
			f.permit.ReserveReviewSHA256 = custodySHA(reviewBytes)
		}
		f.writePermit(t)
		if mode == "revoked_permission" {
			require.NoError(t, os.Remove(f.permitPath))
		}
		cmd := exec.CommandContext(ctx, clientPath, "execute-enrolled-return", "--config", c.path, "--approval", approvalPath)
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		output, err := cmd.Output()
		require.Error(t, err, "real executable must refuse this signed fixture")
		var diagnostic struct {
			Code       string `json:"code"`
			Phase      string `json:"phase"`
			HTTPStatus int    `json:"http_status"`
			Boundary   string `json:"boundary"`
		}
		require.NoError(t, json.Unmarshal(output, &diagnostic), "fixed CLI diagnostic: %s", output)
		require.Equal(t, "ESCROW_RETURN_OUTCOME_UNKNOWN", diagnostic.Code)
		require.Equal(t, "http_status", diagnostic.Phase)
		require.Equal(t, http.StatusConflict, diagnostic.HTTPStatus)
		require.Equal(t, expectedBoundary, diagnostic.Boundary)
		require.Equal(t, before, counts(), "refused subprocess must not broadcast")
		inspection, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:8094/satchel/v1/returns/execution/"+f.approval.ClaimID, nil)
		require.NoError(t, err)
		inspection.Header.Set("Authorization", "Bearer "+testHTTPToken)
		observed, err := client.Do(inspection)
		require.NoError(t, err)
		_, _ = io.Copy(io.Discard, io.LimitReader(observed.Body, 64<<10))
		require.NoError(t, observed.Body.Close())
		require.Equal(t, http.StatusNotFound, observed.StatusCode, "refusal must precede durable intent; absence still never authorizes retry")
		return
	}
	cli := func() EscrowReturnSpendResult {
		cmd := exec.CommandContext(ctx, clientPath, "execute-enrolled-return", "--config", c.path, "--approval", approvalPath)
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		output, err := cmd.Output()
		if err != nil {
			inspection, _ := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:8094/satchel/v1/returns/execution/"+f.approval.ClaimID, nil)
			inspection.Header.Set("Authorization", "Bearer "+testHTTPToken)
			status, observation := 0, []byte(nil)
			if response, readErr := client.Do(inspection); readErr == nil {
				status = response.StatusCode
				observation, _ = io.ReadAll(io.LimitReader(response.Body, 64<<10))
				_ = response.Body.Close()
			}
			var serverLog []byte
			if file, openErr := os.Open(logPath); openErr == nil {
				serverLog, _ = io.ReadAll(io.LimitReader(file, 16<<10))
				_ = file.Close()
			}
			t.Fatalf("actual CLI failed: %v stdout=%s stderr=%s; read-only attempt status=%d body=%s broadcasts_delta=%d; fixed daemon log=%s", err, output, stderr.Bytes(), status, observation, counts()-before, serverLog)
		}
		var observed struct {
			Protocol            int                     `json:"protocol"`
			Kind                string                  `json:"kind"`
			Result              EscrowReturnSpendResult `json:"result"`
			ExecutionAuthorized bool                    `json:"execution_authorized"`
			CreditAuthorized    bool                    `json:"credit_authorized"`
		}
		require.NoError(t, json.Unmarshal(output, &observed))
		require.Equal(t, 1, observed.Protocol)
		require.Equal(t, "escrow_return_execution_observed", observed.Kind)
		require.False(t, observed.ExecutionAuthorized)
		require.False(t, observed.CreditAuthorized)
		return observed.Result
	}
	result := cli()
	require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	require.Equal(t, before+1, counts())
	evidence, err := c.reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: c.config.BettingEscrow, Recipient: c.config.Vault, AmountUWolo: f.approval.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/" + f.approval.ClaimID}, result.TxHash)
	require.NoError(t, err)
	require.True(t, evidence.ConsensusAuthenticated())
	require.False(t, evidence.CreditAuthorized())
	reconcileBody, err := json.Marshal(map[string]any{"approval": f.approval, "tx_hash": result.TxHash})
	require.NoError(t, err)
	reconcileRequest, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://127.0.0.1:8094/satchel/v1/returns/reconcile", bytes.NewReader(reconcileBody))
	require.NoError(t, err)
	reconcileRequest.Header.Set("Authorization", "Bearer "+testHTTPToken)
	reconcileRequest.Header.Set("Content-Type", "application/json")
	reconciled, err := client.Do(reconcileRequest)
	require.NoError(t, err)
	receiptBytes, err := io.ReadAll(io.LimitReader(reconciled.Body, 64<<10))
	require.NoError(t, err)
	require.NoError(t, reconciled.Body.Close())
	require.Equal(t, http.StatusOK, reconciled.StatusCode, "actual reconciliation: %s", receiptBytes)
	var receipt ReturnReceipt
	require.NoError(t, json.Unmarshal(receiptBytes, &receipt))
	require.Equal(t, result.TxHash, receipt.TxHash)
	require.Equal(t, evidence.Receipt().ID(), receipt.ReceiptID)
	require.False(t, receipt.CreditAuthorized)
	require.NoError(t, os.Remove(f.permitPath))
	again := cli()
	require.Equal(t, result, again)
	require.Equal(t, before+1, counts(), "actual executable must not sign/broadcast again after permit revocation")
	// The original signed intent stays UNKNOWN. A CLI receipt never grants HD credit.
	require.Equal(t, "UNKNOWN", again.Status)
	require.True(t, strings.HasPrefix(again.OperationID, "satchel:claim-return:"))
}
