package satchelservice

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

type escrowBankHTTPFixture struct{ bankHTTPFixture }

func (b *escrowBankHTTPFixture) EscrowBankProof(ctx context.Context) (satchel.BankProof, error) {
	return b.BankProof(ctx)
}

func TestEscrowBankHTTPHasFixedProtectedRoleAndNoExecution(t *testing.T) {
	cfg := testHTTPConfig(t)
	cfg.Authorize = func(context.Context) bool { return false }
	cfg.EscrowAddress = testHTTPAddress(t, 103)
	b := &escrowBankHTTPFixture{bankHTTPFixture{vault: cfg.EscrowAddress}}
	h := testHTTPHandler(t, b, cfg)
	for _, body := range []string{`{}`, `{"protocol":2}`, `{"protocol":1,"account":"caller"}`, `{"protocol":1,"height":123}`, `{"protocol":1,"protocol":1}`} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, testHTTPRequest("POST", "/satchel/v1/proofs/escrow-bank", body))
		if w.Code != 400 || b.calls != 0 {
			t.Fatal("caller chose bank authority", w.Code, b.calls)
		}
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest("POST", "/satchel/v1/proofs/escrow-bank", `{"protocol":1}`))
	var proof satchel.BankProof
	if w.Code != 200 || json.Unmarshal(w.Body.Bytes(), &proof) != nil || proof.Address != cfg.EscrowAddress || b.submissions.Load() != 0 || b.reconciliations.Load() != 0 || b.lookups.Load() != 0 {
		t.Fatal("escrow bank read executed funds", w.Code, w.Body.String())
	}
	wire, _ := json.Marshal(proof)
	if !bytes.Equal(wire, w.Body.Bytes()) {
		t.Fatal("transcript was not canonical compact Go JSON")
	}
	b.vault = cfg.VaultAddress
	w = httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest("POST", "/satchel/v1/proofs/escrow-bank", `{"protocol":1}`))
	if w.Code != 503 {
		t.Fatal("vault proof accepted for escrow", w.Code)
	}
	r := testHTTPRequest("POST", "/satchel/v1/proofs/escrow-bank", `{"protocol":1}`)
	r.Header.Del("Authorization")
	w = httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 401 || b.calls != 2 {
		t.Fatal("unauthenticated escrow read", w.Code, b.calls)
	}
}

func TestEscrowBankUsesGenuineFeePayingSDKStateAndCurrentHPlusOne(t *testing.T) {
	f := newBackendFixture(t)
	chain := newNativeHTTPChainWithBalance(t, f.signer, 100000000)
	primary, witness := chain.serve(t, false), chain.serve(t, true)
	config := f.b.cfg
	config.RPC, config.REST, config.WitnessRPC = primary.URL, primary.URL, witness.URL
	backend, err := newBackend(config)
	if err != nil {
		t.Fatal(err)
	}
	defer backend.Close()
	backend.signer = f.signer
	signed, err := backend.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	if err = backend.ValidateSigned(f.request, signed); err != nil {
		t.Fatal(err)
	}
	executed := chain.commit(t, [][]byte{signed.Bytes})
	if len(executed.TxResults) != 1 || executed.TxResults[0].Code != 0 {
		t.Fatal("actual SDK transaction refused", executed.TxResults)
	}
	for n := 0; n < 3; n++ {
		chain.commit(t, nil)
	}
	anchor := satchel.TrustAnchor{Height: 1, Hash: hex.EncodeToString(chain.commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "isolated-escrow-bank-SDK-only"}
	reader, err := satchel.NewTrustedReader(satchel.SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL}, anchor)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	e := &Engine{policy: Policy{Vault: testHTTPAddress(t, 119), BettingEscrow: config.Vault}}
	proof, err := e.EscrowBankProof(t.Context(), reader)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := satchel.NewProofVerifier(anchor)
	if err != nil {
		t.Fatal(err)
	}
	bank, err := verifier.VerifyBankProof(t.Context(), config.Vault, proof.Height, proof)
	if err != nil || !bank.CurrentAt(time.Now()) || bank.BalanceUWolo() != "92997500" || bank.CommitHeight() != chain.head || bank.Height() != chain.head-1 {
		t.Fatal("fee-paying native escrow state was not authenticated", bank.BalanceUWolo(), err)
	}
	if _, err = verifier.VerifyBankProof(t.Context(), e.policy.Vault, proof.Height, proof); err == nil {
		t.Fatal("vault/escrow role substitution accepted")
	}
	if _, err = verifier.VerifyBankProof(t.Context(), config.Vault, proof.Height+1, proof); err == nil {
		t.Fatal("future state height accepted")
	}
	wrongAnchor := anchor
	wrongAnchor.Hash = strings.Repeat("F", 64)
	wrongVerifier, err := satchel.NewProofVerifier(wrongAnchor)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = wrongVerifier.VerifyBankProof(t.Context(), config.Vault, proof.Height, proof); err == nil {
		t.Fatal("different trust root accepted")
	}
	chain.commit(t, nil)
	old, _, err := reader.ReadBankProof(t.Context(), config.Vault, proof.Height)
	if err == nil && old.CurrentAt(time.Now()) {
		t.Fatal("known newer head made old state current")
	}
	current, err := e.EscrowBankProof(t.Context(), reader)
	if err != nil || current.Height != chain.head-1 {
		t.Fatal("current collector did not reselect H", err)
	}
	if f.signer.calls.Load() != 1 || chain.broadcasts != 0 {
		t.Fatal("bank observation signed or broadcast")
	}
}
