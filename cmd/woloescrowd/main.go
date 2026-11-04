// woloescrowd validates held policy/portable evidence and can submit an exact
// approved return to the protected 8094 boundary. It never opens a signer,
// listener or execution journal; the existing runtime owns those authorities.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/epochescrow/nativeverifier"
	"github.com/emaren/wolochain/internal/satchelservice"
)

func run(args []string, out io.Writer) int {
	return runWithIO(args, os.Stdin, out)
}

func runWithIO(args []string, in io.Reader, out io.Writer) int {
	if len(args) > 0 && args[0] == "execute-enrolled-return" {
		return runExecuteReturn(args[1:], out)
	}
	if portableArguments(args) {
		return runPortable(args, in, out, portableDependencies{
			loadPins: nativeverifier.LoadProtectedPinsContext,
			identity: nativeverifier.RuntimeIdentityContext,
			verify:   nativeverifier.Verify,
			timeout:  4 * time.Second,
		})
	}
	return runPolicy(args, out)
}

// This dispatch intentionally has no configuration, path or environment
// override. The HD subprocess gets one read-only operation and fixed pins.
func portableArguments(args []string) bool {
	return len(args) == 2 && ((args[0] == "--verify-epoch-v3-portable-proof" && args[1] == "--json-stdin") || (args[1] == "--verify-epoch-v3-portable-proof" && args[0] == "--json-stdin"))
}

type portableDependencies struct {
	loadPins func(context.Context) (nativeverifier.Pins, error)
	identity func(context.Context) (nativeverifier.Identity, error)
	verify   func(context.Context, nativeverifier.Pins, nativeverifier.Identity, []byte) (nativeverifier.Verdict, error)
	timeout  time.Duration
}

type portableResult struct {
	data   []byte
	status int
}

func portableError(code string) portableResult {
	// Errors are stable codes, never an underlying path, request or RPC error.
	for _, c := range code {
		if (c < 'A' || c > 'Z') && (c < '0' || c > '9') && c != '_' {
			code = "NATIVE_VERIFIER_INVALID"
			break
		}
	}
	if len(code) == 0 || len(code) > 80 {
		code = "NATIVE_VERIFIER_INVALID"
	}
	return portableResult{data: []byte(`{"code":"` + code + `"}` + "\n"), status: 2}
}

func runPortable(args []string, in io.Reader, out io.Writer, deps portableDependencies) int {
	if !portableArguments(args) {
		result := portableError("EPOCH_POLICY_INVALID")
		_, _ = out.Write(result.data)
		return result.status
	}
	ctx, cancel := context.WithTimeout(context.Background(), deps.timeout)
	defer cancel()
	completed := make(chan portableResult, 1)
	go func() {
		completed <- verifyPortableInput(ctx, in, deps)
	}()
	var result portableResult
	select {
	case result = <-completed:
		if ctx.Err() != nil {
			result = portableError("NATIVE_VERIFIER_TIMEOUT")
		}
	case <-ctx.Done():
		result = portableError("NATIVE_VERIFIER_TIMEOUT")
	}
	_, _ = out.Write(result.data)
	return result.status
}

func verifyPortableInput(ctx context.Context, in io.Reader, deps portableDependencies) portableResult {
	pins, err := deps.loadPins(ctx)
	if err != nil {
		return portableError("PRODUCTION_TRUST_ENROLLMENT_REQUIRED")
	}
	identity, err := deps.identity(ctx)
	if err != nil {
		return portableError("NATIVE_VERIFIER_IDENTITY_MISMATCH")
	}
	data, err := io.ReadAll(io.LimitReader(in, nativeverifier.MaxBundleBytes+1))
	if err != nil || len(data) == 0 || !utf8.Valid(data) {
		return portableError("NATIVE_VERIFIER_INPUT_INVALID")
	}
	if len(data) > nativeverifier.MaxBundleBytes {
		return portableError("NATIVE_VERIFIER_INPUT_TOO_LARGE")
	}
	if ctx.Err() != nil {
		return portableError("NATIVE_VERIFIER_TIMEOUT")
	}
	verdict, err := deps.verify(ctx, pins, identity, data)
	if err != nil {
		return portableError(nativeverifier.ErrorCode(err))
	}
	encoded, err := json.Marshal(verdict)
	if err != nil || len(encoded)+1 > 256*1024 {
		return portableError("NATIVE_VERIFIER_OUTPUT_INVALID")
	}
	return portableResult{data: append(encoded, '\n'), status: 0}
}

func runPolicy(args []string, out io.Writer) int {
	flags := flag.NewFlagSet("woloescrowd", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	config := flags.String("config", "", "absolute protected policy path")
	check := flags.Bool("check", false, "read-only structural policy check")
	if flags.Parse(args) != nil || flags.NArg() != 0 || *config == "" {
		fmt.Fprintln(out, `{"code":"EPOCH_POLICY_INVALID"}`)
		return 2
	}
	data, e := satchelservice.ReadPrivateFile(*config, 65536)
	var policy epochescrow.Policy
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if e != nil || !json.Valid(data) || decoder.Decode(&policy) != nil {
		fmt.Fprintln(out, `{"code":"EPOCH_POLICY_INVALID"}`)
		return 2
	}
	// ReadPrivateFile pins the descriptor; strict duplicate-key validation is
	// shared with the existing protected configuration decoder below.
	if e = validatePolicyJSON(data); e != nil {
		fmt.Fprintln(out, `{"code":"EPOCH_POLICY_INVALID"}`)
		return 2
	}
	if e = policy.Validate(); e != nil {
		var blocker *epochescrow.Blocker
		if errors.As(e, &blocker) {
			_ = json.NewEncoder(out).Encode(blocker)
		} else {
			fmt.Fprintln(out, `{"code":"EPOCH_POLICY_INVALID"}`)
		}
		return 2
	}
	if *check {
		fmt.Fprintln(out, `{"status":"STRUCTURAL_REVIEW_ONLY","signing_authorized":false,"broadcast_authorized":false}`)
		return 0
	}
	_ = json.NewEncoder(out).Encode(epochescrow.UnavailableExecution())
	return 2
}
func main() { os.Exit(run(os.Args[1:], os.Stdout)) }

func validatePolicyJSON(data []byte) error {
	if !chainjson.ValidFolded(data) {
		return errors.New("policy_json_invalid")
	}
	return nil
}
