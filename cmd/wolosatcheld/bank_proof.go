package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

// These commands return before service startup: no activation permit, Cosmos
// keyring, journal, listener, signing or broadcasting is involved. The offline
// verifier cannot choose a trust root from the supplied untrusted transcript.
func bankProofCommand(ctx context.Context, mode string, args []string, out, errout io.Writer) int {
	fail := func() int {
		fmt.Fprintln(errout, "satchel: bank proof UNVERIFIABLE; no solvency or spending authorized")
		return 2
	}
	flags := flag.NewFlagSet(mode, flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	authorityPath := flags.String("authority", "", "existing operator-owned public financial authority")
	height := flags.Int64("height", 0, "exact SDK state height H, authenticated by header H+1")
	var proofPath, rpc, rest, witness string
	if mode == "verify-bank-proof" {
		flags.StringVar(&proofPath, "proof", "", "untrusted bounded bank transcript")
	} else if mode == "read-bank-proof" {
		flags.StringVar(&rpc, "rpc", "", "operator-pinned primary RPC")
		flags.StringVar(&rest, "rest", "", "operator-pinned REST source")
		flags.StringVar(&witness, "witness-rpc", "", "independently provisioned witness RPC")
	} else {
		return fail()
	}
	if ctx == nil || ctx.Err() != nil || flags.Parse(args) != nil || flags.NArg() != 0 || *authorityPath == "" || *height <= 0 {
		return fail()
	}
	raw, err := readProofFile(*authorityPath, 64<<10)
	if err != nil {
		return fail()
	}
	authority, err := satchelservice.DecodeFinancialProofVerifierConfig(raw)
	if err != nil {
		return fail()
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	if mode == "read-bank-proof" {
		reader, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: rpc, REST: rest, WitnessRPC: witness}, authority.TrustAnchor)
		if err != nil {
			return fail()
		}
		defer reader.Close()
		evidence, proof, err := reader.ReadBankProof(ctx, authority.Vault, *height)
		if err != nil || !evidence.FreshAt(time.Now()) || ctx.Err() != nil {
			return fail()
		}
		if json.NewEncoder(out).Encode(proof) != nil {
			return fail()
		}
		return 0
	}
	if proofPath == "" {
		return fail()
	}
	raw, err = readProofFile(proofPath, satchel.MaxPortableProofBytes)
	if err != nil {
		return fail()
	}
	proof, err := satchel.DecodeBankProof(raw)
	if err != nil {
		return fail()
	}
	verifier, err := satchel.NewProofVerifier(authority.TrustAnchor)
	if err != nil {
		return fail()
	}
	evidence, err := verifier.VerifyBankProof(ctx, authority.Vault, *height, proof)
	if err != nil || !evidence.FreshAt(time.Now()) || ctx.Err() != nil {
		return fail()
	}
	// All fields below derive from opaque authenticated evidence. This is an
	// asset observation, never a complete customer-liability or gas certificate.
	result := struct {
		Protocol               int    `json:"protocol"`
		Status                 string `json:"status"`
		ChainID                string `json:"chain_id"`
		Denom                  string `json:"denom"`
		Vault                  string `json:"vault"`
		BalanceUWolo           string `json:"balance_uwolo"`
		Height                 int64  `json:"height"`
		CommitHeight           int64  `json:"commit_height"`
		BlockHash              string `json:"block_hash"`
		AppHash                string `json:"app_hash"`
		HeadHeight             int64  `json:"head_height"`
		HeadBlockHash          string `json:"head_block_hash"`
		HeadTime               string `json:"head_time"`
		AuthenticatedExpiresAt string `json:"authenticated_expires_at"`
		CreditAuthorized       bool   `json:"credit_authorized"`
		SpendingAuthorized     bool   `json:"spending_authorized"`
		SolvencyAuthorized     bool   `json:"solvency_authorized"`
	}{1, "AUTHENTICATED_BANK_NONAUTHORIZING", evidence.ChainID(), evidence.Denom(), evidence.VaultAddress(), evidence.BalanceUWolo(), evidence.Height(), evidence.CommitHeight(), evidence.BlockHash(), evidence.AppHash(), evidence.HeadHeight(), evidence.HeadBlockHash(), evidence.HeadTime().UTC().Format(time.RFC3339Nano), evidence.ExpiresAt().UTC().Format(time.RFC3339Nano), false, false, false}
	if json.NewEncoder(out).Encode(result) != nil {
		return fail()
	}
	return 0
}
