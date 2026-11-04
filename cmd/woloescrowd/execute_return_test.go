package main

// Transport tests do not establish enrolled custody, native finality, signatures
// or financial authority. The service remains the only execution boundary.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/cosmos/btcutil/bech32"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
	"github.com/stretchr/testify/require"
)

type enrolledReturnTestTransport func(*http.Request) (*http.Response, error)

func (f enrolledReturnTestTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type enrolledReturnClientFixture struct {
	args         []string
	config       satchelservice.Config
	approvalPath string
	token        string
}

func enrolledReturnClientFiles(t *testing.T) enrolledReturnClientFixture {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	require.NoError(t, os.Chmod(dir, 0700))
	address := func(n byte) string {
		a, e := bech32.EncodeFromBase256("wolo", bytes.Repeat([]byte{n}, 20))
		require.NoError(t, e)
		return a
	}
	key := func(n byte) string {
		return hex.EncodeToString(ed25519.NewKeyFromSeed(bytes.Repeat([]byte{n}, 32)).Public().(ed25519.PublicKey))
	}
	cfg := satchelservice.Config{Version: 1, Vault: address(110), BettingEscrow: address(111), ProtectedAddresses: []string{address(111)},
		PublicKeyHex: "02" + strings.Repeat("01", 32), MaxAmountUWolo: 1000000, RPC: "https://primary.invalid", REST: "https://rest.invalid", WitnessRPC: "https://witness.invalid",
		TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("A", 64), PeriodSeconds: 3600, EvidenceReference: "transport-test-only"},
		KeyringDir:  filepath.Join(dir, "unopened-keyring"), KeyName: "unopened", PassphraseFile: filepath.Join(dir, "unopened-unlock"), StatePath: filepath.Join(dir, "unopened-db"),
		PermitFile: filepath.Join(dir, "unopened-permit"), TokenFile: filepath.Join(dir, "token"), FeesUWolo: "2500", GasLimit: 120000, TimeoutBlocks: 20,
		WithdrawalApprovalKeyHex: key(1), WagerApprovalKeyHex: key(2), ActivationAuthorityKeyHex: key(3)}
	configPath, approvalPath := filepath.Join(dir, "config.json"), filepath.Join(dir, "approval.json")
	b, err := json.Marshal(cfg)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(configPath, b, 0600))
	token := strings.Repeat("isolated_transport_only_", 3)
	require.NoError(t, os.WriteFile(cfg.TokenFile, []byte(token+"\n"), 0600))
	// Deliberately no signature: accepting this fixture in a client-side parser
	// grants nothing; actual 8094 must independently reject unsigned approvals.
	require.NoError(t, os.WriteFile(approvalPath, []byte(`{"version":2,"claim_id":"101","owner_id":"owner-1","allocation":{"version":2}}`), 0600))
	return enrolledReturnClientFixture{args: []string{"--config", configPath, "--approval", approvalPath}, config: cfg, approvalPath: approvalPath, token: token}
}

func enrolledReturnHTTPResponse(status int, body string) *http.Response {
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}
}

func enrolledReturnUnknownReply() string {
	return `{"operation_id":"satchel:claim-return:101","status":"UNKNOWN","reason":"broadcast_accepted_unconfirmed","tx_hash":"` + strings.Repeat("A", 64) + `","durable_fenced":true}`
}

func TestExecuteEnrolledReturnFixedAuthenticatedSingleRequestNoncreditingObservation(t *testing.T) {
	f := enrolledReturnClientFiles(t)
	calls := 0
	transport := enrolledReturnTestTransport(func(r *http.Request) (*http.Response, error) {
		calls++
		require.Equal(t, enrolledReturnEndpoint, r.URL.String())
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "Bearer "+f.token, r.Header.Get("Authorization"))
		require.Equal(t, "application/json", r.Header.Get("Content-Type"))
		require.Equal(t, "identity", r.Header.Get("Accept-Encoding"))
		deadline, ok := r.Context().Deadline()
		require.True(t, ok)
		require.LessOrEqual(t, time.Until(deadline), 15*time.Second)
		body, err := io.ReadAll(r.Body)
		require.NoError(t, err)
		expected, err := os.ReadFile(f.approvalPath)
		require.NoError(t, err)
		require.Equal(t, expected, body)
		return enrolledReturnHTTPResponse(http.StatusOK, enrolledReturnUnknownReply()), nil
	})
	var out bytes.Buffer
	require.Zero(t, runExecuteReturnWithTransport(f.args, &out, transport))
	require.Equal(t, 1, calls)
	var reply map[string]any
	require.NoError(t, json.Unmarshal(out.Bytes(), &reply))
	require.Equal(t, false, reply["execution_authorized"])
	require.Equal(t, false, reply["credit_authorized"])
	require.Equal(t, "escrow_return_execution_observed", reply["kind"])
	for _, path := range []string{f.config.KeyringDir, f.config.PassphraseFile, f.config.StatePath, f.config.PermitFile} {
		_, err := os.Stat(path)
		require.True(t, os.IsNotExist(err), "client must not create or open runtime financial state")
	}
}

func TestExecuteEnrolledReturnActualTransportWaitsBeyondEightSecondsWithoutRetry(t *testing.T) {
	f := enrolledReturnClientFiles(t)
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		select {
		case <-time.After(9000 * time.Millisecond):
		case <-r.Context().Done():
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, enrolledReturnUnknownReply())
	}))
	defer server.Close()
	transport := newExecuteReturnTransport()
	defer transport.CloseIdleConnections()
	// Map only this test socket. Production argv/config cannot change8094.
	transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		return (&net.Dialer{Timeout: time.Second}).DialContext(ctx, network, server.Listener.Addr().String())
	}
	var out bytes.Buffer
	require.Zero(t, runExecuteReturnWithTransport(f.args, &out, transport), out.String())
	require.EqualValues(t, 1, calls.Load(), "a delayed header must never cause a retry")
}

func TestExecuteEnrolledReturnAmbiguousOrForgedHTTPNeverRetriesOrEchoes(t *testing.T) {
	f := enrolledReturnClientFiles(t)
	valid := enrolledReturnUnknownReply()
	cases := map[string]func() (*http.Response, error){
		"timeout":          func() (*http.Response, error) { return nil, context.DeadlineExceeded },
		"transport secret": func() (*http.Response, error) { return nil, errors.New("sensitive-transport-fixture") },
		"refused": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusForbidden, "sensitive-transport-fixture"), nil
		},
		"redirect": func() (*http.Response, error) {
			r := enrolledReturnHTTPResponse(http.StatusTemporaryRedirect, "")
			r.Header.Set("Location", "http://127.0.0.1:8092/settlement/v1/runs")
			return r, nil
		},
		"oversized": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Repeat("x", enrolledReturnMaxBytes+1)), nil
		},
		"compressed": func() (*http.Response, error) {
			r := enrolledReturnHTTPResponse(http.StatusOK, valid)
			r.Header.Set("Content-Encoding", "gzip")
			return r, nil
		},
		"other claim": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, "return:101", "return:102", 1)), nil
		},
		"confirmed DTO": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, "UNKNOWN", "CONFIRMED", 1)), nil
		},
		"not fenced": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, `"durable_fenced":true`, `"durable_fenced":false`, 1)), nil
		},
		"duplicate": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.TrimSuffix(valid, "}")+`,"status":"UNKNOWN"}`), nil
		},
		"case alias": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, `"status"`, `"Status"`, 1)), nil
		},
		"credit flag": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.TrimSuffix(valid, "}")+`,"credit_authorized":true}`), nil
		},
		"zero hash": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, strings.Repeat("A", 64), strings.Repeat("0", 64), 1)), nil
		},
		"unknown reason": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, strings.Replace(valid, "broadcast_accepted_unconfirmed", "sensitive-transport-fixture", 1)), nil
		},
		"truncated": func() (*http.Response, error) {
			return enrolledReturnHTTPResponse(http.StatusOK, valid[:len(valid)-1]), nil
		},
	}
	for name, response := range cases {
		t.Run(name, func(t *testing.T) {
			calls := 0
			transport := enrolledReturnTestTransport(func(*http.Request) (*http.Response, error) { calls++; return response() })
			var out bytes.Buffer
			require.Equal(t, 2, runExecuteReturnWithTransport(f.args, &out, transport))
			var diagnostic struct {
				Code       string `json:"code"`
				Phase      string `json:"phase"`
				HTTPStatus int    `json:"http_status"`
				Boundary   string `json:"boundary"`
			}
			require.NoError(t, json.Unmarshal(out.Bytes(), &diagnostic))
			require.Equal(t, "ESCROW_RETURN_OUTCOME_UNKNOWN", diagnostic.Code)
			require.NotEmpty(t, diagnostic.Phase)
			require.Equal(t, "unclassified", diagnostic.Boundary)
			require.NotContains(t, out.String(), "sensitive-transport-fixture")
			require.Equal(t, 1, calls, "no retry or legacy redirect")
		})
	}
}

func TestExecuteEnrolledReturnRejectsUnsafePrivateInputBeforeTransport(t *testing.T) {
	for _, mode := range []string{"approval_permissions", "approval_symlink", "approval_oversize", "duplicate", "case_alias", "nested_case_alias", "unknown_field", "historical_claim", "config_permissions", "invalid_config", "token_permissions"} {
		t.Run(mode, func(t *testing.T) {
			f := enrolledReturnClientFiles(t)
			switch mode {
			case "approval_permissions":
				require.NoError(t, os.Chmod(f.approvalPath, 0644))
			case "approval_symlink":
				alias := filepath.Join(filepath.Dir(f.approvalPath), "alias.json")
				require.NoError(t, os.Symlink(f.approvalPath, alias))
				f.args[3] = alias
			case "approval_oversize":
				require.NoError(t, os.WriteFile(f.approvalPath, bytes.Repeat([]byte("x"), enrolledReturnMaxBytes+1), 0600))
			case "duplicate":
				require.NoError(t, os.WriteFile(f.approvalPath, []byte(`{"version":2,"version":2}`), 0600))
			case "case_alias":
				require.NoError(t, os.WriteFile(f.approvalPath, []byte(`{"Version":2,"claim_id":"101","owner_id":"owner-1","allocation":{}}`), 0600))
			case "nested_case_alias":
				require.NoError(t, os.WriteFile(f.approvalPath, []byte(`{"version":2,"claim_id":"101","owner_id":"owner-1","allocation":{"Version":2}}`), 0600))
			case "unknown_field":
				require.NoError(t, os.WriteFile(f.approvalPath, []byte(`{"version":2,"claim_id":"101","owner_id":"owner-1","allocation":{},"sender":"arbitrary"}`), 0600))
			case "historical_claim":
				require.NoError(t, os.WriteFile(f.approvalPath, []byte(`{"version":2,"claim_id":"889","owner_id":"owner-1","allocation":{}}`), 0600))
			case "config_permissions":
				require.NoError(t, os.Chmod(f.args[1], 0644))
			case "invalid_config":
				require.NoError(t, os.WriteFile(f.args[1], []byte(`{}`), 0600))
			case "token_permissions":
				require.NoError(t, os.Chmod(f.config.TokenFile, 0644))
			}
			calls := 0
			transport := enrolledReturnTestTransport(func(*http.Request) (*http.Response, error) { calls++; return nil, errors.New("must not be called") })
			var out bytes.Buffer
			require.Equal(t, 2, runExecuteReturnWithTransport(f.args, &out, transport))
			require.Zero(t, calls)
			require.NotContains(t, out.String(), f.approvalPath)
			require.NotContains(t, out.String(), f.token)
		})
	}
}

func TestExecuteEnrolledReturnRejectsTargetSignerAndRuntimeOverrides(t *testing.T) {
	f := enrolledReturnClientFiles(t)
	for _, args := range [][]string{nil, {"--config", f.args[1]}, {"--config", "relative", "--approval", f.approvalPath},
		{"--config", f.args[1], "--config", f.args[1]},
		append(append([]string{}, f.args...), "--node", "http://127.0.0.1:8092"),
		{"--sender", "arbitrary", "--approval", f.approvalPath},
		{"--signer", "arbitrary", "--approval", f.approvalPath},
		{"--destination", "arbitrary", "--approval", f.approvalPath}} {
		var out bytes.Buffer
		calls := 0
		transport := enrolledReturnTestTransport(func(*http.Request) (*http.Response, error) { calls++; return nil, errors.New("must not be called") })
		require.Equal(t, 2, runExecuteReturnWithTransport(args, &out, transport))
		require.Equal(t, `{"code":"ESCROW_RETURN_CLIENT_INPUT_INVALID"}`+"\n", out.String())
		require.Zero(t, calls)
	}
	var out bytes.Buffer
	require.Equal(t, 2, run([]string{"execute-enrolled-return"}, &out))
	require.Equal(t, `{"code":"ESCROW_RETURN_CLIENT_INPUT_INVALID"}`+"\n", out.String(), "new dispatch must preserve a bounded refusal")
}

func TestExecuteEnrolledReturnSafeBoundaryDiagnosticWithoutRetry(t *testing.T) {
	f := enrolledReturnClientFiles(t)
	for _, boundary := range []string{"reserve_review_outlives_bank", "sensitive-transport-fixture"} {
		calls := 0
		transport := enrolledReturnTestTransport(func(*http.Request) (*http.Response, error) {
			calls++
			r := enrolledReturnHTTPResponse(http.StatusConflict, "sensitive-transport-fixture")
			r.Header.Set("X-Wolo-Escrow-Boundary", boundary)
			return r, nil
		})
		var out bytes.Buffer
		require.Equal(t, 2, runExecuteReturnWithTransport(f.args, &out, transport))
		require.Equal(t, 1, calls)
		require.Contains(t, out.String(), `"phase":"http_status"`)
		require.Contains(t, out.String(), `"http_status":409`)
		require.Contains(t, out.String(), `"boundary":"`+satchelservice.EscrowReturnBoundaryName(boundary)+`"`)
		require.NotContains(t, out.String(), "sensitive-transport-fixture")
	}
}
