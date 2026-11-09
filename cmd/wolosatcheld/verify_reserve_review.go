package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

// The operator retains authority separately from the supplied review and proof.
// This command returns before any service config, keyring, journal, or RPC opens.
func verifyReserveReviewCommand(ctx context.Context, args []string, out, errout io.Writer) int {
	flags := flag.NewFlagSet("verify-reserve-review", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	authorityPath := flags.String("authority", "", "operator-owned public trust and audited evidence pins")
	reviewPath := flags.String("review", "", "existing dual-signed Satchel reserve review")
	bankProofPath := flags.String("bank-proof", "", "untrusted native bank proof transcript")
	refuse := func() int {
		fmt.Fprintln(errout, "satchel: reserve review UNVERIFIABLE; no financial authority")
		return 2
	}
	if ctx == nil || ctx.Err() != nil || flags.Parse(args) != nil || flags.NArg() != 0 ||
		*authorityPath == "" || *reviewPath == "" || *bankProofPath == "" {
		return refuse()
	}
	authority, err := satchelservice.ReadPrivateFile(*authorityPath, 16<<10)
	if err != nil {
		return refuse()
	}
	review, err := satchelservice.ReadPrivateFile(*reviewPath, 16<<10)
	if err != nil {
		return refuse()
	}
	proof, err := readProofFile(*bankProofPath, satchel.MaxPortableProofBytes)
	if err != nil {
		return refuse()
	}
	receipt, err := satchelservice.VerifyPortableReserveReview(ctx, authority, review, proof)
	if err != nil || json.NewEncoder(out).Encode(receipt) != nil {
		return refuse()
	}
	return 0
}
