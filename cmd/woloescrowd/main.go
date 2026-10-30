// woloescrowd validates the held independent v3 policy. It intentionally cannot
// open a signer, listener or execution journal until real authority enrollment
// and off-host nonce reservation have an independently reviewed implementation.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/satchelservice"
)

func run(args []string, out io.Writer) int {
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
