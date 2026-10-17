// wolosatcheld is a separately installed private Satchel custody boundary. It
// never starts a consensus node or the existing 8092/8093 settlement services.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	os.Exit(run(ctx, os.Args[1:], os.Stdout, os.Stderr))
}

// run returns only fixed public diagnostic labels. Sensitive configuration,
// source responses, filesystem paths and keyring errors are never printed.
func run(ctx context.Context, args []string, out, errout io.Writer) int {
	flags := flag.NewFlagSet("wolosatcheld", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	path := flags.String("config", "", "absolute operator-managed config path")
	check := flags.Bool("check", false, "verify configuration and signed permit without opening a keyring or listener")
	if flags.Parse(args) != nil || flags.NArg() != 0 || *path == "" {
		fmt.Fprintln(errout, "satchel: configuration flag required")
		return 2
	}
	cfg, configDigest, err := satchelservice.LoadConfig(*path)
	if err != nil {
		fmt.Fprintln(errout, "satchel: configuration refused")
		return 2
	}
	binaryDigest, err := runningDigest()
	if err != nil {
		fmt.Fprintln(errout, "satchel: executable attestation unavailable")
		return 2
	}
	authorized := func(context.Context) bool { return satchelservice.VerifyPermit(cfg, configDigest, binaryDigest) }
	if !authorized(ctx) {
		fmt.Fprintln(errout, "satchel: HELD independent activation permit unavailable")
		return 2
	}
	trusted, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: cfg.RPC, REST: cfg.REST, WitnessRPC: cfg.WitnessRPC}, cfg.TrustAnchor)
	if err != nil {
		fmt.Fprintln(errout, "satchel: HELD independent chain trust unavailable")
		return 2
	}
	defer trusted.Close()
	if *check {
		fmt.Fprintln(out, "satchel: PERMIT_VALID TRUST_UNCHECKED; no network, keyring, listener or transfer opened")
		return 0
	}
	if trusted.CheckTrust(ctx) != nil {
		fmt.Fprintln(errout, "satchel: HELD authenticated chain trust unavailable")
		return 2
	}
	token, err := satchelservice.ReadPrivateFile(cfg.TokenFile, 4096)
	if err != nil {
		fmt.Fprintln(errout, "satchel: private authentication unavailable")
		return 2
	}
	approvalKey, err := hex.DecodeString(cfg.WithdrawalApprovalKeyHex)
	if err != nil {
		fmt.Fprintln(errout, "satchel: withdrawal authority refused")
		return 2
	}
	policy := satchelservice.Policy{Vault: cfg.Vault, BettingEscrow: cfg.BettingEscrow, ProtectedAddresses: cfg.ProtectedAddresses, MaxAmountUWolo: cfg.MaxAmountUWolo, WithdrawalApprovalKey: approvalKey}
	backend, err := satchelservice.NewKeyringBackend(satchelservice.BackendConfig{RPC: cfg.RPC, REST: cfg.REST, WitnessRPC: cfg.WitnessRPC, Vault: cfg.Vault, PublicKeyHex: cfg.PublicKeyHex, KeyringDir: cfg.KeyringDir, KeyName: cfg.KeyName, PassphraseFile: cfg.PassphraseFile, FeesUWolo: cfg.FeesUWolo, MaxAmountUWolo: strconv.FormatUint(cfg.MaxAmountUWolo, 10), GasLimit: cfg.GasLimit, TimeoutBlocks: cfg.TimeoutBlocks, ApprovedDestinations: []string{cfg.BettingEscrow}, ProtectedAddresses: cfg.ProtectedAddresses, WithdrawalVerifier: policy.VerifyWithdrawal, ConfirmTransaction: func(ctx context.Context, request satchelservice.TransferRequest, signed satchelservice.SignedTransaction) (satchelservice.Confirmation, error) {
		evidence, err := trusted.ReadTransfer(ctx, satchel.TransferIntent{Sender: request.Sender, Recipient: request.Recipient, AmountUWolo: request.AmountUWolo, Memo: request.Memo}, signed.Hash)
		if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
			return satchelservice.Confirmation{Status: "UNKNOWN"}, errors.New("authenticated_confirmation_unavailable")
		}
		observation := evidence.Observation()
		if !bytes.Equal(observation.TxBytes, signed.Bytes) {
			return satchelservice.Confirmation{Status: "UNKNOWN"}, errors.New("authenticated_transaction_mismatch")
		}
		return satchelservice.Confirmation{Status: "CONFIRMED", ReceiptID: evidence.Receipt().ID(), Height: observation.Height, BlockHash: observation.BlockHash}, nil
	}})
	if err != nil {
		fmt.Fprintln(errout, "satchel: isolated signer unavailable")
		return 2
	}
	defer backend.Close()
	guard := &permittedBackend{inner: backend, authorize: authorized, trust: trusted.CheckTrust}
	engine, err := satchelservice.Open(cfg.StatePath, policy, guard)
	if err != nil {
		fmt.Fprintln(errout, "satchel: durable fencing unavailable")
		return 2
	}
	defer engine.Close()
	public, _ := hex.DecodeString(cfg.PublicKeyHex)
	fingerprint := sha256.Sum256(public)
	handler, err := satchelservice.NewHTTPHandler(&serviceEngine{Engine: engine, trusted: trusted}, satchelservice.HTTPConfig{Token: strings.TrimSpace(string(token)), Accepting: true, Authorize: authorized, Health: satchelservice.HTTPHealth{Accepting: true, VaultAddress: cfg.Vault, KeyFingerprint: hex.EncodeToString(fingerprint[:]), BuildSHA256: binaryDigest, ExclusiveAuthorityVerified: true}})
	for i := range token {
		token[i] = 0
	}
	if err != nil {
		fmt.Fprintln(errout, "satchel: private HTTP boundary refused")
		return 2
	}
	server, err := satchelservice.NewPrivateHTTPServer("127.0.0.1:8094", handler)
	if err != nil {
		fmt.Fprintln(errout, "satchel: private listener refused")
		return 2
	}
	stopped := make(chan error, 1)
	go func() { stopped <- server.ListenAndServe() }()
	select {
	case err := <-stopped:
		if !errors.Is(err, http.ErrServerClosed) {
			fmt.Fprintln(errout, "satchel: private listener unavailable")
			return 1
		}
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdown); err != nil {
			_ = server.Close()
			fmt.Fprintln(errout, "satchel: shutdown held pending operations")
			return 1
		}
	}
	return 0
}

type permittedBackend struct {
	inner     satchelservice.Backend
	authorize func(context.Context) bool
	trust     func(context.Context) error
}

// The return observer is fixed by server configuration; callers cannot supply
// another RPC, trust anchor or receipt verifier for a claimed refund.
type serviceEngine struct {
	*satchelservice.Engine
	trusted *satchel.TrustedReader
}

func (e *serviceEngine) ReconcileClaimReturn(ctx context.Context, a satchelservice.ReturnApproval, hash string) (satchelservice.ReturnReceipt, error) {
	return e.Engine.ReconcileReturn(ctx, a, hash, e.trusted)
}

func (b *permittedBackend) Sign(ctx context.Context, r satchelservice.TransferRequest) (satchelservice.SignedTransaction, error) {
	if b.authorize == nil || !b.authorize(ctx) {
		return satchelservice.SignedTransaction{}, satchelservice.ErrPreSignRefused
	}
	if b.trust == nil || b.trust(ctx) != nil {
		return satchelservice.SignedTransaction{}, satchelservice.ErrPreSignRefused
	}
	return b.inner.Sign(ctx, r)
}
func (b *permittedBackend) ValidateSigned(r satchelservice.TransferRequest, s satchelservice.SignedTransaction) error {
	return b.inner.ValidateSigned(r, s)
}
func (b *permittedBackend) Broadcast(ctx context.Context, s satchelservice.SignedTransaction) (satchelservice.BroadcastResult, error) {
	if b.authorize == nil || !b.authorize(ctx) {
		return satchelservice.BroadcastResult{Status: "UNKNOWN"}, errors.New("activation_held")
	}
	return b.inner.Broadcast(ctx, s)
}
func (b *permittedBackend) Confirm(ctx context.Context, r satchelservice.TransferRequest, s satchelservice.SignedTransaction) (satchelservice.Confirmation, error) {
	return b.inner.Confirm(ctx, r, s)
}

func runningDigest() (string, error) {
	path, err := os.Executable()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "linux" {
		path = "/proc/self/exe"
	}
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > 512<<20 {
		return "", errors.New("executable_refused")
	}
	hash := sha256.New()
	n, err := io.Copy(hash, io.LimitReader(file, (512<<20)+1))
	if err != nil || n > 512<<20 {
		return "", errors.New("executable_refused")
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
