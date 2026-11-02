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
	"errors"
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
	bolt "go.etcd.io/bbolt"
)

func TestEscrowServiceProductionExecutables(t *testing.T) {
	signerPath, clientPath := os.Getenv("SATCHEL_C01_SIGNER_EXECUTABLE"), os.Getenv("SATCHEL_C01_CLIENT_EXECUTABLE")
	if signerPath == "" && clientPath == "" {
		t.Skip("requires explicit CI-built production executables and isolated loopback8094")
	}
	for _, mode := range []string{"review_outlives_bank", "expired_permission", "stale_bank_root", "revoked_permission", "confirmed_replay", "interrupted_broadcast_restart"} {
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
	client := &http.Client{Timeout: time.Second, Transport: &http.Transport{Proxy: nil, DisableKeepAlives: true}}
	defer client.CloseIdleConnections()
	type actualDaemon struct {
		command *exec.Cmd
		done    chan struct{}
		waitErr error
		logPath string
	}
	// Wait and log close happen exactly once, including after an actual kill.
	// Cleanup and the restart boundary only observe that shared completion.
	startDaemon := func(label string) *actualDaemon {
		p := &actualDaemon{command: exec.CommandContext(ctx, signerPath, "--config", c.path), done: make(chan struct{}),
			logPath: filepath.Join(filepath.Dir(c.path), "actual-executor-"+label+".log")}
		log, openErr := os.OpenFile(p.logPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		require.NoError(t, openErr)
		p.command.Stdout, p.command.Stderr = log, log
		if startErr := p.command.Start(); startErr != nil {
			_ = log.Close()
			require.NoError(t, startErr)
		}
		go func() { p.waitErr = p.command.Wait(); _ = log.Close(); close(p.done) }()
		t.Cleanup(func() {
			_ = p.command.Process.Signal(syscall.SIGTERM)
			select {
			case <-p.done:
			case <-time.After(2 * time.Second):
				_ = p.command.Process.Kill()
				select {
				case <-p.done:
				case <-time.After(2 * time.Second):
					t.Error("isolated actual daemon did not exit after kill")
				}
			}
		})
		ready := false
		for deadline := time.Now().Add(8 * time.Second); time.Now().Before(deadline) && ctx.Err() == nil; {
			req, _ := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:8094/satchel/v1/custody/journal", nil)
			req.Header.Set("Authorization", "Bearer "+testHTTPToken)
			response, readErr := client.Do(req)
			if readErr == nil {
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
			contents, _ := os.ReadFile(p.logPath)
			t.Fatalf("actual enrolled executor did not start: %s", contents)
		}
		return p
	}
	child := startDaemon("initial")
	logPath := child.logPath
	counts := func() int { c.chain.mu.Lock(); defer c.chain.mu.Unlock(); return c.chain.broadcasts }
	before := counts()
	if mode != "confirmed_replay" && mode != "interrupted_broadcast_restart" {
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
	// Inspect only after the isolated child has exited and released Bolt. This
	// cannot sign or repair history and is never a second execution authority.
	readSpend := func() ([]byte, escrowReturnSpendRecord) {
		db, openErr := bolt.Open(c.config.StatePath, 0600, &bolt.Options{ReadOnly: true, Timeout: 100 * time.Millisecond})
		require.NoError(t, openErr)
		defer db.Close()
		var raw []byte
		var state escrowReturnSpendRecord
		require.NoError(t, db.View(func(tx *bolt.Tx) error {
			bucket := tx.Bucket(escrowReturnSpendBucket)
			if bucket == nil {
				return ErrEscrowReturnSpend
			}
			raw = append([]byte(nil), bucket.Get([]byte(f.approval.ClaimID))...)
			return json.Unmarshal(raw, &state)
		}))
		return raw, state
	}
	var result EscrowReturnSpendResult
	var interruptedRecord []byte
	if mode == "interrupted_broadcast_restart" {
		type committedReturn struct {
			bytes      []byte
			broadcasts int
			status     int
			killErr    error
		}
		committed := make(chan committedReturn, 1)
		initialChild := child
		// This parent-side hook runs AFTER the unmodified native SDK upstream
		// commits the actual signed MsgSend, and BEFORE its ACK reaches custody.
		// Kill only our isolated production daemon; never substitute SDK effects.
		hook := func(response *http.Response) error {
			c.broadcastResponseHook.Store(nil)
			c.chain.mu.Lock()
			seen := committedReturn{bytes: append([]byte(nil), c.chain.transaction.Tx...), broadcasts: c.chain.broadcasts, status: response.StatusCode}
			c.chain.mu.Unlock()
			seen.killErr = initialChild.command.Process.Kill()
			committed <- seen
			return errors.New("isolated_sdk_commit_ack_withheld")
		}
		c.broadcastResponseHook.Store(&hook)
		t.Cleanup(func() { c.broadcastResponseHook.Store(nil) })
		command := exec.CommandContext(ctx, clientPath, "execute-enrolled-return", "--config", c.path, "--approval", approvalPath)
		var stderr bytes.Buffer
		command.Stderr = &stderr
		output, cliErr := command.Output()
		require.Error(t, cliErr, "the actual first CLI cannot know a killed daemon's financial outcome")
		var diagnostic struct {
			Code string `json:"code"`
		}
		require.NoError(t, json.Unmarshal(output, &diagnostic), "actual interrupted CLI: %s stderr=%s", output, stderr.Bytes())
		require.Equal(t, "ESCROW_RETURN_OUTCOME_UNKNOWN", diagnostic.Code)
		var seen committedReturn
		select {
		case seen = <-committed:
		case <-time.After(2 * time.Second):
			t.Fatal("actual SDK broadcast never reached the committed-before-ACK crash boundary")
		}
		require.NoError(t, seen.killErr)
		require.Equal(t, http.StatusOK, seen.status)
		require.Equal(t, before+1, seen.broadcasts)
		select {
		case <-initialChild.done:
		case <-time.After(2 * time.Second):
			t.Fatal("killed isolated daemon did not release its journal/keyring leases")
		}
		require.Error(t, initialChild.waitErr)
		var state escrowReturnSpendRecord
		interruptedRecord, state = readSpend()
		require.Equal(t, 1, state.Version)
		require.Equal(t, "UNKNOWN", state.Result.Status)
		require.Equal(t, "broadcast_started", state.Result.Reason)
		require.True(t, state.Result.DurableFenced)
		require.Equal(t, "satchel:claim-return:"+f.approval.ClaimID, state.Result.OperationID)
		require.Equal(t, state.Result.OperationID, state.Request.OperationID)
		require.NotNil(t, state.Request.ReturnApproval)
		require.Equal(t, f.approval, *state.Request.ReturnApproval)
		require.Equal(t, c.config.BettingEscrow, state.Request.Sender)
		require.Equal(t, c.config.Vault, state.Request.Recipient)
		require.Equal(t, hashJSON(state.Request), state.ApprovalHash)
		require.Equal(t, seen.bytes, state.Signed.Bytes)
		require.Equal(t, strings.ToUpper(custodySHA(seen.bytes)), state.Signed.Hash)
		require.Equal(t, state.Signed.Hash, state.Result.TxHash)
		require.Equal(t, f.permit.Nonce, state.OperationNonce)
		ownerPermit, readErr := os.ReadFile(f.permitPath)
		require.NoError(t, readErr)
		require.Equal(t, ownerPermit, state.OperationPermitRaw)
		require.Equal(t, custodySHA(ownerPermit), state.OperationPermitSHA256)
		require.Equal(t, reviewBytes, state.ReserveReviewRaw)
		require.NoError(t, os.Remove(f.permitPath))
		// Reopen the SAME actual journal and both SDK keyring leases with the
		// original owner permission absent. Startup/recovery grants no new spend.
		child = startDaemon("recovered")
		logPath = child.logPath
		inspection, readErr := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:8094/satchel/v1/returns/execution/"+f.approval.ClaimID, nil)
		require.NoError(t, readErr)
		inspection.Header.Set("Authorization", "Bearer "+testHTTPToken)
		response, readErr := client.Do(inspection)
		require.NoError(t, readErr)
		body, readErr := io.ReadAll(io.LimitReader(response.Body, 64<<10))
		require.NoError(t, readErr)
		require.NoError(t, response.Body.Close())
		require.Equal(t, http.StatusOK, response.StatusCode, "actual durable recovery: %s", body)
		require.NoError(t, json.Unmarshal(body, &result))
		require.Equal(t, state.Result, result)
		require.Equal(t, before+1, counts(), "restart and GET must never rebroadcast")
	} else {
		result = cli()
		require.Equal(t, "broadcast_accepted_unconfirmed", result.Reason)
	}
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
	if mode == "confirmed_replay" {
		require.NoError(t, os.Remove(f.permitPath))
	}
	again := cli()
	require.Equal(t, result, again)
	require.Equal(t, before+1, counts(), "actual executable must not sign/broadcast again after permit revocation")
	// The original signed intent stays UNKNOWN. A CLI receipt never grants HD credit.
	require.Equal(t, "UNKNOWN", again.Status)
	require.True(t, strings.HasPrefix(again.OperationID, "satchel:claim-return:"))
	if mode == "interrupted_broadcast_restart" {
		require.NoError(t, child.command.Process.Signal(syscall.SIGTERM))
		select {
		case <-child.done:
		case <-time.After(2 * time.Second):
			t.Fatal("recovered isolated daemon did not stop")
		}
		require.NoError(t, child.waitErr)
		after, state := readSpend()
		require.Equal(t, interruptedRecord, after, "restart, reconciliation and explicit duplicate observation must preserve signed bytes, nonce and broadcast_started history")
		require.Equal(t, result, state.Result)
	}
}
