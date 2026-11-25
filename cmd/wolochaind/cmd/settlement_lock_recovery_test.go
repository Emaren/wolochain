package cmd

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// These tests never contact a real chain or signer. Expiring the on-disk
// timestamp must not give a second process the first process's payment lock.
func TestSettlementExpiredLiveLockCannotBroadcastTwice(t *testing.T) {
	for _, role := range []string{settlementSignerRole, settlementEscrowSignerRole} {
		t.Run(role, func(t *testing.T) {
			balances := map[string]string{c4Signer: "10000000", c4EscrowSigner: "10000000"}
			cfg := newTestSettlementConfig(t, c4Signer, balances)
			cfg.EscrowKeyName, cfg.EscrowAddress = "escrow", c4EscrowSigner
			cfg.HealthTimeout = time.Minute
			cfg.ConfirmTimeout = 50 * time.Millisecond
			entered, resume := make(chan struct{}), make(chan struct{})
			defer func() {
				select {
				case <-resume:
				default:
					close(resume)
				}
			}()
			var first atomic.Bool
			chain := newMockSettlementChainHandler(balances)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == "/status" && first.CompareAndSwap(false, true) {
					close(entered)
					select {
					case <-resume:
					case <-r.Context().Done():
						return
					}
				}
				chain.ServeHTTP(w, r)
			}))
			defer server.Close()
			cfg.RPCHTTP, cfg.RESTURL = server.URL, server.URL
			fake := writeFakeSettlementExecutableWithTxsAndKeys(t,
				map[string]string{"payout": c4Signer, "escrow": c4EscrowSigner},
				map[string]string{c4Recipient: c4TxHash})
			counter := filepath.Join(t.TempDir(), "broadcasts")
			wrapper := filepath.Join(t.TempDir(), "cli.sh")
			if err := os.WriteFile(wrapper, []byte("#!/bin/sh\nif [ \"$1\" = tx ]; then printf 'send\\n' >> '"+counter+"'; fi\nexec /bin/sh '"+fake+"' \"$@\"\n"), 0o700); err != nil {
				t.Fatal(err)
			}
			cfg.ExecutablePath, cfg.ExecutableInterpreter = wrapper, "/bin/sh"
			request := settlementExecuteRequest{RequestID: "expired-live-" + role, ToAddress: c4Recipient, AmountUWolo: "700", Memo: c4Memo}
			execute := cfg.executeSettlement
			if role == settlementEscrowSignerRole {
				execute = cfg.executeEscrowTransfer
			}
			type execution struct {
				response settlementExecuteResponse
				err      error
			}
			done := make(chan execution, 1)
			go func() { response, err := execute(t.Context(), request); done <- execution{response, err} }()
			select {
			case <-entered:
			case <-time.After(5 * time.Second):
				t.Fatal("first request did not enter preflight")
			}
			old := time.Now().Add(-24 * time.Hour)
			lock := cfg.requestLockPath(request.RequestID)
			if err := os.Chtimes(lock, old, old); err != nil {
				t.Fatal(err)
			}
			second, err := execute(t.Context(), request)
			// Release first preflight before assertions/cleanup. Its request was
			// never dead, even though its lock timestamp was old.
			close(resume)
			firstResult := <-done
			if err != nil || second.FailureCode != "REQUEST_IN_PROGRESS" || second.OK {
				t.Errorf("old timestamp stole an active payment lock: response=%+v err=%v", second, err)
			}
			if firstResult.err != nil || !firstResult.response.OK {
				t.Fatalf("first request: %+v", firstResult)
			}
			calls, err := os.ReadFile(counter)
			if err != nil || string(calls) != "send\n" {
				t.Fatalf("exactly one synthetic bank send required; calls=%q err=%v", calls, err)
			}
		})
	}
}

func TestSettlementAbandonedLocksNeverGrantReplayAuthority(t *testing.T) {
	t.Parallel()
	cfg := settlementConfig{StateDir: t.TempDir(), ChainID: settlementCanonicalChainID, RequestLockTTL: time.Second}
	for _, kind := range []string{"request", "run", "challenge"} {
		t.Run(kind, func(t *testing.T) {
			path := cfg.requestLockPath("abandoned")
			if kind == "run" {
				path = cfg.runLockPath("abandoned")
			}
			if kind == "challenge" {
				path = cfg.challengeLockPath("abandoned")
			}
			if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
				t.Fatal(err)
			}
			const original = "original interruption evidence\n"
			if err := os.WriteFile(path, []byte(original), 0o600); err != nil {
				t.Fatal(err)
			}
			old := time.Now().Add(-24 * time.Hour)
			if err := os.Chtimes(path, old, old); err != nil {
				t.Fatal(err)
			}
			called := false
			var code string
			var err error
			switch kind {
			case "request":
				var r settlementExecuteResponse
				r, err = cfg.withRequestLock("abandoned", settlementSignerRole, func() (settlementExecuteResponse, error) { called = true; return settlementExecuteResponse{}, nil })
				code = r.FailureCode
			case "run":
				var r settlementRunResponse
				r, err = cfg.withRunLock("abandoned", settlementSignerRole, func() (settlementRunResponse, error) { called = true; return settlementRunResponse{}, nil })
				code = r.FailureCode
			case "challenge":
				var r settlementChallengeResponse
				r, err = cfg.withChallengeLock("abandoned", func() (settlementChallengeResponse, error) { called = true; return settlementChallengeResponse{}, nil })
				code = r.FailureCode
			}
			if err != nil || called || !strings.HasSuffix(code, "_IN_PROGRESS") {
				t.Errorf("abandoned %s lock reopened execution: called=%v code=%q err=%v", kind, called, code, err)
			}
			data, err := os.ReadFile(path)
			if err != nil || string(data) != original {
				t.Errorf("%s interruption evidence changed: %q %v", kind, data, err)
			}
		})
	}
}
