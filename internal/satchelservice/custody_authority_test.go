package satchelservice

// Actual encrypted SDK keyring + in-memory SDK execution + signed Comet/IAVL
// evidence. The local validator and two financial reviewer keys are isolated
// test authorities; they do not establish production independence/completeness.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/stretchr/testify/require"
)

type custodyAuthorityFixture struct {
	config                         Config
	path                           string
	engine                         *Engine
	native                         *KeyringBackend
	issuer                         *CustodyAuthority
	reader                         *satchel.TrustedReader
	chain                          *nativeHTTPChain
	request                        TransferRequest
	review                         SignedReserveReview
	accounting, custody            ed25519.PrivateKey
	accountEntered, releaseAccount chan struct{}
	pauseAccount                   atomic.Bool
	SDKSigns                       atomic.Int32
	afterSign                      func()
}
type custodyObservedSDKSigner struct {
	inner   backendSigner
	fixture *custodyAuthorityFixture
}

func (s *custodyObservedSDKSigner) Sign(name string, b []byte, mode signing.SignMode) ([]byte, cryptotypes.PubKey, error) {
	s.fixture.SDKSigns.Add(1)
	sig, pub, err := s.inner.Sign(name, b, mode)
	if s.fixture.afterSign != nil {
		s.fixture.afterSign()
	}
	return sig, pub, err
}
func custodyWrite(t *testing.T, path string, value any) []byte {
	t.Helper()
	b, err := json.Marshal(value)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(path, b, 0600))
	return b
}
func newCustodyAuthorityFixture(t *testing.T) *custodyAuthorityFixture {
	t.Helper()
	backend, old := isolatedBackendConfig(t)
	f := &custodyAuthorityFixture{request: old.request, accountEntered: make(chan struct{}), releaseAccount: make(chan struct{}),
		accounting: ed25519.NewKeyFromSeed(bytes.Repeat([]byte{71}, 32)), custody: ed25519.NewKeyFromSeed(bytes.Repeat([]byte{72}, 32))}
	f.chain = newNativeHTTPChainWithBalance(t, old.signer, 110000000)
	f.chain.commit(t, nil)
	f.chain.commit(t, nil) // actual retained state2, authenticated head3
	primary, witness := f.chain.serve(t, false), f.chain.serve(t, true)
	u, err := url.Parse(primary.URL)
	require.NoError(t, err)
	proxy := httputil.NewSingleHostReverseProxy(u)
	transport := &http.Transport{Proxy: nil}
	proxy.Transport = transport
	t.Cleanup(transport.CloseIdleConnections)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/cosmos/auth/v1beta1/accounts/") && f.pauseAccount.Load() {
			close(f.accountEntered)
			select {
			case <-f.releaseAccount:
			case <-r.Context().Done():
				return
			}
		}
		proxy.ServeHTTP(w, r)
	}))
	t.Cleanup(server.Close)
	dir, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	require.NoError(t, os.Chmod(dir, 0700))
	activation := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, 32))
	f.config = Config{Version: 1, Vault: backend.Vault, PublicKeyHex: backend.PublicKeyHex, BettingEscrow: backend.ApprovedDestinations[0],
		ProtectedAddresses: backend.ApprovedDestinations, MaxAmountUWolo: 1000000000, RPC: server.URL, REST: server.URL, WitnessRPC: witness.URL,
		TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: hex.EncodeToString(f.chain.commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "isolated-custody-issuer-test-validator-only"},
		KeyringDir:  backend.KeyringDir, KeyName: backend.KeyName, PassphraseFile: backend.PassphraseFile, TokenFile: filepath.Join(dir, "token"), StatePath: filepath.Join(dir, "journal.db"),
		FeesUWolo: backend.FeesUWolo, GasLimit: backend.GasLimit, TimeoutBlocks: backend.TimeoutBlocks,
		WithdrawalApprovalKeyHex: hex.EncodeToString(engineTestApprovalKey().Public().(ed25519.PublicKey)), WagerApprovalKeyHex: hex.EncodeToString(engineTestWagerApprovalKey().Public().(ed25519.PublicKey)),
		ActivationAuthorityKeyHex: hex.EncodeToString(activation.Public().(ed25519.PublicKey)), PermitFile: filepath.Join(dir, "permit.json"),
		AccountingReviewerKeyHex: hex.EncodeToString(f.accounting.Public().(ed25519.PublicKey)), CustodyReviewerKeyHex: hex.EncodeToString(f.custody.Public().(ed25519.PublicKey)), ReserveReviewFile: filepath.Join(dir, "review.json")}
	f.path = filepath.Join(dir, "config.json")
	custodyWrite(t, f.path, f.config)
	require.NoError(t, os.WriteFile(f.config.TokenFile, []byte(testHTTPToken), 0600))
	_, digest, err := LoadConfig(f.path)
	require.NoError(t, err)
	binary, err := runtimeCustodyBinaryDigest()
	require.NoError(t, err)
	permit := ExecutionPermit{Version: 1, Scope: "satchel-execution-v1", ConfigSHA256: digest, BinarySHA256: binary, Vault: f.config.Vault,
		IsolationEvidenceSHA256: strings.Repeat("1", 64), AccountingEvidenceSHA256: strings.Repeat("2", 64), RecoveryEvidenceSHA256: strings.Repeat("3", 64),
		Reviewer: "isolated-test-reviewer-only", Reference: "test SDK funds and controlled reviewers; no mainnet authority", IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Unix() + 120}
	permit.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(activation, PermitMessage(permit)))
	custodyWrite(t, f.config.PermitFile, permit)
	f.reader, err = satchel.NewTrustedReader(satchel.SourceConfig{RPC: f.config.RPC, REST: f.config.REST, WitnessRPC: f.config.WitnessRPC}, f.config.TrustAnchor)
	require.NoError(t, err)
	t.Cleanup(f.reader.Close)
	p := Policy{Vault: f.config.Vault, BettingEscrow: f.config.BettingEscrow, ProtectedAddresses: f.config.ProtectedAddresses, MaxAmountUWolo: f.config.MaxAmountUWolo,
		WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
	bc := nativeHTTPBackendConfig(f.config, p)
	bc.AuthorizeSign = func(ctx context.Context, r TransferRequest) bool {
		return f.issuer != nil && f.issuer.AuthorizeSign(ctx, r)
	}
	bc.AuthorizeBroadcast = func(ctx context.Context, s SignedTransaction) bool {
		return f.issuer != nil && f.issuer.AuthorizeBroadcast(ctx, s)
	}
	bc.ConfirmTransaction = func(ctx context.Context, r TransferRequest, s SignedTransaction) (Confirmation, error) {
		e, err := f.reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, s.Hash)
		if err != nil || !e.ConsensusAuthenticated() || !bytes.Equal(e.Observation().TxBytes, s.Bytes) {
			return Confirmation{Status: "UNKNOWN"}, errCustodyUnavailable
		}
		return Confirmation{Status: "CONFIRMED", ReceiptID: e.Receipt().ID(), Height: e.Observation().Height, BlockHash: e.Observation().BlockHash}, nil
	}
	f.native, err = NewKeyringBackend(bc)
	require.NoError(t, err)
	t.Cleanup(f.native.Close)
	f.native.signer = &custodyObservedSDKSigner{inner: f.native.signer, fixture: f}
	f.engine, err = Open(f.config.StatePath, p, f.native)
	require.NoError(t, err)
	t.Cleanup(func() { _ = f.engine.Close() })
	f.issuer, err = NewCustodyAuthority(f.engine, f.native, f.reader, f.path, digest, binary)
	require.NoError(t, err)
	require.NoError(t, f.engine.RequireCustodyAuthority(f.issuer))
	f.refreshReview(t)
	return f
}
func (f *custodyAuthorityFixture) refreshReview(t *testing.T) {
	t.Helper()
	journal, err := f.engine.CustodyJournal()
	require.NoError(t, err)
	bank, _, err := f.reader.ReadCurrentBankProof(t.Context(), f.config.Vault)
	require.NoError(t, err)
	permit, err := os.ReadFile(f.config.PermitFile)
	require.NoError(t, err)
	f.review = SignedReserveReview{Version: 1, Scope: reserveReviewScope, ChainID: "wolo-1", Denom: "uwolo", Vault: f.config.Vault, StateHeight: bank.Height(), CommitBlockHash: bank.BlockHash(), ObservedBankUWolo: bank.BalanceUWolo(),
		ConfirmedLiabilitiesUWolo: "100000000", UncertainMaxLiabilitiesUWolo: "1000000", GasReserveUWolo: "10000", UnencumberedMinimumUWolo: "10000",
		LiabilityInventorySHA256: custodySHA(custodyWrite(t, filepath.Join(filepath.Dir(f.path), "isolated-owner-liabilities.json"), map[string]any{"fixture_only": true, "owner_id": f.request.OwnerID, "known_liability_uwolo": "100000000", "uncertain_upper_bound_uwolo": "1000000"})), JournalSnapshotSHA256: journal.JournalDigest, NonOverlapWitnessSHA256: strings.Repeat("5", 64),
		BuildSHA256: f.issuer.binaryDigest, ConfigSHA256: f.issuer.configDigest, PermitSHA256: custodySHA(permit), AllObligationsCovered: true, UnknownClaimsReserved: true, DedicatedVaultIsolated: true,
		IssuedAt: time.Now().Unix() - 1, ExpiresAt: bank.ExpiresAt().Unix() - 1}
	f.writeReview(t)
}
func (f *custodyAuthorityFixture) writeReview(t *testing.T) {
	t.Helper()
	signReview(&f.review, f.accounting, f.custody)
	custodyWrite(t, f.config.ReserveReviewFile, f.review)
}

func (f *custodyAuthorityFixture) privateHTTP(t *testing.T) string {
	t.Helper()
	public, err := hex.DecodeString(f.config.PublicKeyHex)
	require.NoError(t, err)
	handler, err := NewHTTPHandler(f.engine, HTTPConfig{Token: testHTTPToken, Accepting: true,
		Authorize: func(ctx context.Context) bool {
			return VerifyPermit(f.config, f.issuer.configDigest, f.issuer.binaryDigest)
		}, CustodyCapability: f.issuer.Capability,
		Health: HTTPHealth{Accepting: true, VaultAddress: f.config.Vault, KeyFingerprint: custodySHA(public), BuildSHA256: f.issuer.binaryDigest, ExclusiveAuthorityVerified: true}})
	require.NoError(t, err)
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	return server.URL
}

func TestRuntimeCustodyAuthorityHealthIsDerivedAndImmediatelyRevocable(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	url := f.privateHTTP(t)
	status, raw, err := nativeHTTPWire(t, url, "/satchel/v1/health", nil, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status)
	var health map[string]any
	require.NoError(t, json.Unmarshal(raw, &health))
	require.Equal(t, "AVAILABLE", health["custody_capability"])
	require.Equal(t, true, health["accepting"])
	require.Equal(t, "war-satchel-runtime-custody-v1", health["custody_capability_version"])
	require.NoError(t, os.Remove(f.config.PermitFile))
	status, raw, err = nativeHTTPWire(t, url, "/satchel/v1/health", nil, testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status)
	require.NoError(t, json.Unmarshal(raw, &health))
	require.Equal(t, "UNAVAILABLE", health["custody_capability"])
	require.Equal(t, false, health["accepting"])
	status, _, err = nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(f.request), testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusServiceUnavailable, status)
	require.Zero(t, f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
}

func TestRuntimeCustodyAuthorityActualBankJournalAndRevocation(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	cap := f.issuer.Capability(t.Context())
	require.True(t, cap.Available(t.Context()))
	require.False(t, satchel.CurrentCapability().Available(), "dormant source capability must stay unavailable")
	for _, mode := range []string{"review", "permit", "config", "token", "unlock", "unlock_permissions", "keyring_permissions", "journal_permissions"} {
		t.Run(mode, func(t *testing.T) {
			path := map[string]string{"review": f.config.ReserveReviewFile, "permit": f.config.PermitFile, "config": f.path, "token": f.config.TokenFile, "unlock": f.config.PassphraseFile, "unlock_permissions": f.config.PassphraseFile, "keyring_permissions": filepath.Join(f.config.KeyringDir, "keyring-file"), "journal_permissions": f.config.StatePath}[mode]
			if strings.HasSuffix(mode, "permissions") {
				info, err := os.Stat(path)
				require.NoError(t, err)
				require.NoError(t, os.Chmod(path, info.Mode().Perm()|0044))
				defer os.Chmod(path, info.Mode().Perm())
			} else {
				original, err := os.ReadFile(path)
				require.NoError(t, err)
				changed := append(append([]byte(nil), original...), ' ')
				if mode == "review" {
					changed = []byte(`{}`)
				}
				require.NoError(t, os.WriteFile(path, changed, 0600))
				defer os.WriteFile(path, original, 0600)
			}
			require.False(t, cap.Available(t.Context()), "retained capability survived authority rotation")
			require.False(t, f.issuer.Capability(t.Context()).Available(t.Context()))
		})
	}
	require.True(t, cap.Available(t.Context()))
	require.Zero(t, f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
	wrong := f.issuer.binaryDigest
	f.issuer.binaryDigest = strings.Repeat("a", 64)
	require.False(t, cap.Available(t.Context()))
	f.issuer.binaryDigest = wrong
	f.native.Close()
	require.False(t, cap.Available(t.Context()))
}

func TestRuntimeCustodyAuthorityCannotSpendCoveredCustomerLiabilitiesWithoutEquity(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	// Assets110WOLO exactly cover known108.98 + unknown1 + gas0.01 + floor0.01.
	// Even dual approval cannot assume an atomic discharge of any liability.
	f.review.ConfirmedLiabilitiesUWolo = "108980000"
	f.writeReview(t)
	require.False(t, f.issuer.Capability(t.Context()).Available(t.Context()))
	_, err := f.engine.Submit(t.Context(), f.request)
	require.ErrorIs(t, err, errCustodyUnavailable)
	require.Zero(t, f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
}

func TestRuntimeCustodyAuthoritySerialConservationAndRecovery(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	cap := f.issuer.Capability(t.Context())
	require.True(t, cap.Available(t.Context()))
	f.chain.release()
	url := f.privateHTTP(t)
	status, raw, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(f.request), testHTTPToken)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, status, string(raw))
	var result Result
	require.NoError(t, json.Unmarshal(raw, &result))
	require.NoError(t, err)
	require.Equal(t, "ACCEPTED", result.Status)
	require.Equal(t, int32(1), f.SDKSigns.Load())
	require.Equal(t, 1, f.chain.broadcasts)
	require.False(t, cap.Available(t.Context()), "journal mutation must revoke the prior positive capability")
	require.False(t, f.issuer.Capability(t.Context()).Available(t.Context()), "pending broadcast cannot qualify new spending")
	for i := 0; i < 3; i++ {
		again, err := f.engine.Submit(t.Context(), f.request)
		require.NoError(t, err)
		require.Equal(t, result, again)
	}
	confirmed, err := f.engine.Reconcile(t.Context(), f.request.OperationID)
	require.NoError(t, err)
	require.Equal(t, "CONFIRMED", confirmed.Status)
	require.False(t, f.issuer.Capability(t.Context()).Available(t.Context()), "old journal and bank review renewed itself")
	f.refreshReview(t)
	require.True(t, f.issuer.Capability(t.Context()).Available(t.Context()))
	second := f.request
	second.OperationID = "satchel:ticket:8"
	second.Memo = "AoE2HDBets bet ticket v1 · ticket 8"
	second.Reservation = testWagerReservation(t, second, f.engine.policy, time.Now())
	_, err = f.engine.Submit(t.Context(), second)
	require.ErrorIs(t, err, errCustodyUnavailable, "7WOLO exceeds remaining free margin after reserves")
	require.Equal(t, int32(1), f.SDKSigns.Load())
	require.Equal(t, 1, f.chain.broadcasts)
	require.NoError(t, f.engine.Close())
	require.False(t, cap.Available(t.Context()))
}

func TestRuntimeCustodyAuthorityConcurrentHTTPReservationsCannotReuseReview(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	f.chain.release()
	url := f.privateHTTP(t)
	second := f.request
	second.OperationID = "satchel:ticket:8"
	second.Memo = "AoE2HDBets bet ticket v1 · ticket 8"
	second.Reservation = testWagerReservation(t, second, f.engine.policy, time.Now())
	second.Reservation.FeeUWolo = f.config.FeesUWolo
	second.Reservation.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(engineTestWagerApprovalKey(), WagerReservationMessage(*second.Reservation)))
	done := make(chan int, 2)
	start := make(chan struct{})
	for _, r := range []TransferRequest{f.request, second} {
		go func() {
			<-start
			status, _, err := nativeHTTPWire(t, url, "/satchel/v2/one-shot", nativeHTTPWager(r), testHTTPToken)
			if err != nil {
				done <- 0
				return
			}
			done <- status
		}()
	}
	close(start)
	first, other := <-done, <-done
	require.True(t, (first == http.StatusOK && other >= 400) || (other == http.StatusOK && first >= 400), "two requests reused one exact reserve/journal review: %d/%d", first, other)
	require.Equal(t, int32(1), f.SDKSigns.Load())
	require.Equal(t, 1, f.chain.broadcasts)
}

func TestRuntimeCustodyAuthorityRevokedAfterAccountIOBeforeSDKSign(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	require.True(t, f.issuer.Capability(t.Context()).Available(t.Context()))
	f.pauseAccount.Store(true)
	done := make(chan Result, 1)
	go func() { r, _ := f.engine.Submit(t.Context(), f.request); done <- r }()
	select {
	case <-f.accountEntered:
	case <-time.After(5 * time.Second):
		t.Fatal("actual native account I/O not reached")
	}
	require.NoError(t, os.Remove(f.config.PermitFile))
	close(f.releaseAccount)
	select {
	case result := <-done:
		require.Equal(t, "REFUSED", result.Status)
	case <-time.After(5 * time.Second):
		t.Fatal("revoked signing did not finish")
	}
	require.Zero(t, f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
}

func TestRuntimeCustodyAuthoritySignedButRevokedNeverBroadcastsOrRetries(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	f.afterSign = func() { require.NoError(t, os.Remove(f.config.ReserveReviewFile)) }
	result, err := f.engine.Submit(t.Context(), f.request)
	require.NoError(t, err)
	require.Equal(t, "UNKNOWN", result.Status)
	require.NotEmpty(t, result.TxHash)
	for i := 0; i < 3; i++ {
		again, err := f.engine.Submit(t.Context(), f.request)
		require.NoError(t, err)
		require.Equal(t, result, again)
	}
	require.Equal(t, int32(1), f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
	require.False(t, f.issuer.Capability(t.Context()).Available(t.Context()))
}

func TestRuntimeCustodyAuthorityExpiresDuringNativeIO(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	f.review.ExpiresAt = time.Now().Unix() + 4
	f.writeReview(t)
	require.True(t, f.issuer.Capability(t.Context()).Available(t.Context()))
	f.pauseAccount.Store(true)
	done := make(chan Result, 1)
	go func() { r, _ := f.engine.Submit(t.Context(), f.request); done <- r }()
	select {
	case <-f.accountEntered:
	case <-time.After(5 * time.Second):
		t.Fatal("actual native account I/O not reached")
	}
	time.Sleep(time.Until(time.Unix(f.review.ExpiresAt, 0).Add(10 * time.Millisecond)))
	close(f.releaseAccount)
	select {
	case result := <-done:
		require.Equal(t, "REFUSED", result.Status)
	case <-time.After(5 * time.Second):
		t.Fatal("expired signing did not finish")
	}
	require.Zero(t, f.SDKSigns.Load())
	require.Zero(t, f.chain.broadcasts)
}
