package main

// This command is only an authenticated client of the existing protected 8094
// runtime. It never opens a keyring, journal, signer, database or listener.
import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"path/filepath"
	"reflect"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchelservice"
)

const enrolledReturnEndpoint = "http://127.0.0.1:8094/satchel/v1/returns/execute"
const enrolledReturnMaxBytes = 64 << 10

var enrolledReturnClaim = regexp.MustCompile(`^[1-9][0-9]{0,11}$`)
var enrolledReturnHash = regexp.MustCompile(`^[A-F0-9]{64}$`)
var enrolledReturnToken = regexp.MustCompile(`^[A-Za-z0-9_-]{48,512}$`)

func runExecuteReturn(args []string, out io.Writer) int {
	transport := &http.Transport{Proxy: nil,
		DialContext:           (&net.Dialer{Timeout: 2 * time.Second}).DialContext,
		ResponseHeaderTimeout: 3 * time.Second, DisableCompression: true,
		DisableKeepAlives: true, MaxConnsPerHost: 1, MaxResponseHeaderBytes: 8192}
	defer transport.CloseIdleConnections()
	return runExecuteReturnWithTransport(args, out, transport)
}

// The transport seam is private test support. Production dispatch always uses
// the fixed transport above; no environment, argv or request selects a target.
func runExecuteReturnWithTransport(args []string, out io.Writer, transport http.RoundTripper) int {
	fail := func(code string) int { fmt.Fprintln(out, `{"code":"`+code+`"}`); return 2 }
	if len(args) != 4 || transport == nil {
		return fail("ESCROW_RETURN_CLIENT_INPUT_INVALID")
	}
	paths := map[string]string{}
	for i := 0; i < len(args); i += 2 {
		if (args[i] != "--config" && args[i] != "--approval") || paths[args[i]] != "" ||
			!filepath.IsAbs(args[i+1]) || filepath.Clean(args[i+1]) != args[i+1] {
			return fail("ESCROW_RETURN_CLIENT_INPUT_INVALID")
		}
		paths[args[i]] = args[i+1]
	}
	if paths["--config"] == "" || paths["--approval"] == "" {
		return fail("ESCROW_RETURN_CLIENT_INPUT_INVALID")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	cfg, _, err := satchelservice.LoadConfig(paths["--config"])
	if err != nil || ctx.Err() != nil {
		return fail("ESCROW_RETURN_CLIENT_CONFIGURATION_REFUSED")
	}
	raw, err := satchelservice.ReadPrivateFile(paths["--approval"], enrolledReturnMaxBytes)
	var approval satchelservice.ReturnApproval
	if err != nil || !enrolledReturnStrictJSON(raw, &approval) || approval.Version != 2 ||
		!enrolledReturnClaim.MatchString(approval.ClaimID) || approval.ClaimID == "889" || approval.OwnerID == "" || approval.Allocation == nil {
		return fail("ESCROW_RETURN_CLIENT_APPROVAL_REFUSED")
	}
	// The server independently authenticates every approval and current reserve.
	// Local parsing/transport never confers financial or cryptographic authority.
	tokenBytes, err := satchelservice.ReadPrivateFile(cfg.TokenFile, 4096)
	if err != nil {
		return fail("ESCROW_RETURN_CLIENT_AUTHENTICATION_REFUSED")
	}
	token := strings.TrimSpace(string(tokenBytes))
	for i := range tokenBytes {
		tokenBytes[i] = 0
	}
	if !enrolledReturnToken.MatchString(token) || ctx.Err() != nil {
		return fail("ESCROW_RETURN_CLIENT_AUTHENTICATION_REFUSED")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, enrolledReturnEndpoint, bytes.NewReader(raw))
	if err != nil {
		return fail("ESCROW_RETURN_CLIENT_INPUT_INVALID")
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Accept-Encoding", "identity")
	client := &http.Client{Transport: transport, Timeout: 8 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, err := client.Do(request) // Exactly one application request; never retry an ambiguous outcome.
	if err != nil {
		return fail("ESCROW_RETURN_OUTCOME_UNKNOWN")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK || (response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity") {
		return fail("ESCROW_RETURN_OUTCOME_UNKNOWN")
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, enrolledReturnMaxBytes+1))
	var result satchelservice.EscrowReturnSpendResult
	if err != nil || len(body) > enrolledReturnMaxBytes || !enrolledReturnStrictJSON(body, &result) || ctx.Err() != nil ||
		result.OperationID != "satchel:claim-return:"+approval.ClaimID || result.Status != "UNKNOWN" || !result.DurableFenced ||
		!enrolledReturnReason(result.Reason) || (result.TxHash != "" && (!enrolledReturnHash.MatchString(result.TxHash) || result.TxHash == strings.Repeat("0", 64))) {
		return fail("ESCROW_RETURN_OUTCOME_UNKNOWN")
	}
	// A valid reply means only that the existing runtime reports a fenced
	// UNKNOWN. CheckTx acceptance, transport success and this DTO never credit HD.
	reply := struct {
		Protocol            int                                    `json:"protocol"`
		Kind                string                                 `json:"kind"`
		Result              satchelservice.EscrowReturnSpendResult `json:"result"`
		ExecutionAuthorized bool                                   `json:"execution_authorized"`
		CreditAuthorized    bool                                   `json:"credit_authorized"`
	}{1, "escrow_return_execution_observed", result, false, false}
	if json.NewEncoder(out).Encode(reply) != nil {
		return 2
	}
	return 0
}

func enrolledReturnReason(reason string) bool {
	switch reason {
	case "intent_persisted", "pre_sign_permit_revoked", "signing_started", "signing_uncertain", "invalid_signed_bytes_unknown",
		"signed_bytes_persisted", "signed_permit_revoked_unknown", "broadcast_started", "broadcast_uncertain", "broadcast_accepted_unconfirmed":
		return true
	}
	return false
}

func enrolledReturnStrictJSON(data []byte, target any) bool {
	if len(data) == 0 || !utf8.Valid(data) || !chainjson.ValidFolded(data) || !enrolledReturnExactFields(data, reflect.TypeOf(target).Elem()) {
		return false
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	return d.Decode(target) == nil && d.Decode(new(any)) == io.EOF
}

// encoding/json alone permits case aliases. Require exact published names at
// each nested approval/partition level as well as folded-duplicate rejection.
func enrolledReturnExactFields(data []byte, shape reflect.Type) bool {
	for shape.Kind() == reflect.Pointer {
		shape = shape.Elem()
	}
	if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return true
	}
	switch shape.Kind() {
	case reflect.Struct:
		fields, ok := chainjson.Object(data)
		if !ok {
			return false
		}
		allowed := map[string]reflect.Type{}
		for i := 0; i < shape.NumField(); i++ {
			field := shape.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			if name != "" && name != "-" {
				allowed[name] = field.Type
			}
		}
		for name, raw := range fields {
			typeOf, ok := allowed[name]
			if !ok || !enrolledReturnExactFields(raw, typeOf) {
				return false
			}
		}
	case reflect.Slice:
		var items []json.RawMessage
		if json.Unmarshal(data, &items) != nil {
			return false
		}
		for _, raw := range items {
			if !enrolledReturnExactFields(raw, shape.Elem()) {
				return false
			}
		}
	}
	return true
}
