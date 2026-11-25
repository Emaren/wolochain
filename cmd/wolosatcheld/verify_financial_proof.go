package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"github.com/emaren/wolochain/internal/satchelservice"
)

// This offline command deliberately returns before the normal service startup:
// no activation config, keyring, network transport, listener or journal opens.
// HD must use a pinned verified executable and fixed argv, never a shell, with
// operator-owned authority and its own durable expected context files.
func verifyFinancialProofCommand(ctx context.Context, args []string, out, errout io.Writer) int {
	flags := flag.NewFlagSet("verify-financial-proof", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	authorityPath := flags.String("authority", "", "operator-provisioned public trust and approval authority")
	contextPath := flags.String("expected", "", "trusted durable economic and owner context")
	proofPath := flags.String("proof", "", "untrusted exported financial proof")
	fail := func() int {
		fmt.Fprintln(errout, "satchel: financial proof UNVERIFIABLE; no credit authorized")
		return 2
	}
	if flags.Parse(args) != nil || flags.NArg() != 0 || *authorityPath == "" || *contextPath == "" || *proofPath == "" {
		return fail()
	}
	authorityBytes, err := readProofFile(*authorityPath, 64<<10)
	if err != nil {
		return fail()
	}
	expectedBytes, err := readProofFile(*contextPath, 64<<10)
	if err != nil {
		return fail()
	}
	proofBytes, err := readProofFile(*proofPath, satchelservice.MaxFinancialProofBytes)
	if err != nil {
		return fail()
	}
	authority, err := satchelservice.DecodeFinancialProofVerifierConfig(authorityBytes)
	if err != nil {
		return fail()
	}
	expected, err := satchelservice.DecodeFinancialProofContext(expectedBytes)
	if err != nil {
		return fail()
	}
	proof, err := satchelservice.DecodeFinancialProof(proofBytes)
	if err != nil {
		return fail()
	}
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	receipt, err := satchelservice.VerifyFinancialProof(ctx, authority, expected, proof)
	if err != nil {
		return fail()
	}
	if json.NewEncoder(out).Encode(receipt) != nil {
		return fail()
	}
	return 0
}

func readProofFile(path string, maximum int) ([]byte, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, errors.New("proof_file_refused")
	}
	real, err := filepath.EvalSymlinks(path)
	if err != nil || real != path {
		return nil, errors.New("proof_file_refused")
	}
	file, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, errors.New("proof_file_refused")
	}
	defer file.Close()
	before, err := file.Stat()
	if err != nil || !before.Mode().IsRegular() || before.Mode().Perm()&0022 != 0 || before.Size() <= 0 || before.Size() > int64(maximum) {
		return nil, errors.New("proof_file_refused")
	}
	data, err := io.ReadAll(io.LimitReader(file, int64(maximum)+1))
	after, statErr := file.Stat()
	if err != nil || statErr != nil || len(data) > maximum || len(data) != int(before.Size()) || !os.SameFile(before, after) || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return nil, errors.New("proof_file_refused")
	}
	return data, nil
}
