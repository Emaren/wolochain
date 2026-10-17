package satchelservice

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
)

func testVerifierAuthority(t *testing.T) FinancialProofVerifierConfig {
	p := engineTestPolicy(t)
	return FinancialProofVerifierConfig{Vault: p.Vault, BettingEscrow: p.BettingEscrow, ApprovalPublicKeyHex: hex.EncodeToString(p.WithdrawalApprovalKey), TrustAnchor: satchel.TrustAnchor{Height: 1, Hash: strings.Repeat("1", 64), PeriodSeconds: 600, EvidenceReference: "isolated-test-only"}}
}
func testDepositProofRequest(t *testing.T) DepositProofRequest {
	return DepositProofRequest{Protocol: 1, OwnerID: "owner-1", Sender: testHTTPAddress(t, 99), AmountUWolo: "1000000", Memo: "aoe2war/satchel/deposit/v1/test-intent", CreatedAt: time.Now().Add(-time.Minute).UTC().Format(time.RFC3339Nano), ExpiresAt: time.Now().Add(time.Minute).UTC().Format(time.RFC3339Nano), TxHash: testHTTPHash}
}
func forgedFinancialProof(t *testing.T) FinancialProof {
	r := testDepositProofRequest(t)
	c, _, err := depositContext(r, engineTestPolicy(t).Vault)
	if err != nil {
		t.Fatal(err)
	}
	return FinancialProof{Protocol: 1, ChainID: "wolo-1", Denom: "uwolo", Context: c, ContextDigest: FinancialContextDigest(c), TxHash: testHTTPHash, ReceiptID: "wolo-1:" + testHTTPHash + ":0", Height: 100, BlockHash: strings.Repeat("B", 64), ConsensusAuthenticated: true,
		Proof: satchel.PortableProof{Version: 1, ChainID: "wolo-1", Kind: "deposit", TxHash: testHTTPHash}}
}

func TestFinancialProofCannotAcceptDecodedRestOrSelfAssertedAuthenticity(t *testing.T) {
	p := forgedFinancialProof(t)
	if _, err := VerifyFinancialProof(t.Context(), testVerifierAuthority(t), p.Context, p); err == nil {
		t.Fatal("invented successful JSON and consensus_authenticated flag produced a verified receipt")
	}
	if _, err := financialEnvelope(p.Context, satchel.AuthenticatedEvidence{}, p.Proof); err == nil {
		t.Fatal("zero-value opaque authentication exported a receipt")
	}
	for _, body := range []string{`{}`, `{"consensus_authenticated":true,"credit_authorized":false,"tx_hash":"` + testHTTPHash + `","height":100}`, `{"tx_response":{"code":0,"height":"100","txhash":"` + testHTTPHash + `"}}`} {
		if decoded, err := DecodeFinancialProof([]byte(body)); err == nil {
			if _, verifyErr := VerifyFinancialProof(t.Context(), testVerifierAuthority(t), p.Context, decoded); verifyErr == nil {
				t.Fatal("arbitrary decoded REST JSON authenticated a financial proof")
			}
		}
	}
}

func TestFinancialProofExpectedOwnerEconomicsAndHashMustBeIndependent(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*FinancialProof)
	}{
		{"owner", func(p *FinancialProof) { p.Context.OwnerID = "owner-2" }},
		{"sender", func(p *FinancialProof) { p.Context.Sender = testHTTPAddress(t, 98) }},
		{"recipient", func(p *FinancialProof) { p.Context.Recipient = testHTTPAddress(t, 97) }},
		{"amount", func(p *FinancialProof) { p.Context.AmountUWolo = "1000001" }},
		{"memo", func(p *FinancialProof) { p.Context.Memo += "bad" }},
		{"physical hash", func(p *FinancialProof) { p.TxHash = strings.Repeat("C", 64); p.Context.TxHash = p.TxHash }},
		{"wrong chain", func(p *FinancialProof) { p.ChainID = "invented-chain" }},
		{"wrong denom", func(p *FinancialProof) { p.Denom = "wolo" }},
		{"credit authority", func(p *FinancialProof) { p.CreditAuthorized = true }},
		{"untrusted consensus", func(p *FinancialProof) { p.ConsensusAuthenticated = false }},
		{"wrong message identity", func(p *FinancialProof) { p.MessageIndex = 1 }},
	} {
		t.Run(test.name, func(t *testing.T) {
			p := forgedFinancialProof(t)
			expected := p.Context
			test.mutate(&p)
			p.ContextDigest = FinancialContextDigest(p.Context) // attacker can recompute a plain digest
			if _, err := VerifyFinancialProof(t.Context(), testVerifierAuthority(t), expected, p); err == nil || err.Error() != "financial_proof_context_mismatch" {
				t.Fatalf("changed financial identity reached proof verification: %v", err)
			}
		})
	}
}

func TestFinancialProofJournalSnapshotSurvivesRestartWithoutRetry(t *testing.T) {
	backend := &engineTestBackend{broadcastErr: errors.New("uncertain broadcast")}
	e, path, policy := engineTestOpen(t, backend)
	r := engineTestWithdrawal(t)
	original, err := e.Submit(t.Context(), r)
	if err != nil || original.Status != "UNKNOWN" {
		t.Fatalf("missing uncertain fence: %+v %v", original, err)
	}
	before, expected, err := e.operationProofRecord(r.OperationID)
	if err != nil || expected.TxHash != original.TxHash || expected.OwnerID != r.OwnerID || expected.OwnerMandate == nil {
		t.Fatal("journal did not bind actual owner/signed transaction")
	}
	if err := e.Close(); err != nil {
		t.Fatal(err)
	}
	secondBackend := &engineTestBackend{}
	reopened, err := Open(path, policy, secondBackend)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	after, actual, err := reopened.operationProofRecord(r.OperationID)
	if err != nil || FinancialContextDigest(actual) != FinancialContextDigest(expected) || after.Result != before.Result {
		t.Fatalf("restart replaced economic context: %v", err)
	}
	if _, err := reopened.OperationProof(t.Context(), r.OperationID, nil); err == nil {
		t.Fatal("missing authenticated reader exported a proof")
	}
	if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 || secondBackend.signs.Load() != 0 || secondBackend.broadcasts.Load() != 0 || secondBackend.confirmations.Load() != 0 {
		t.Fatal("read-only proof retried a financial operation")
	}
}

func TestFinancialProofRefusesOwnerlessWagerAndUnreconciledReturn(t *testing.T) {
	e, _, p, _, r := testReturnEngine(t)
	if _, _, err := e.operationProofRecord(r.OperationID); err == nil || err.Error() != "operation_owner_binding_unavailable" {
		t.Fatal("ownerless legacy wager adopted an owner")
	}
	a := testReturnApproval(t, r.OperationID, "101")
	if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
		t.Fatal(err)
	}
	if _, _, err := e.returnProofRecord("101"); err == nil {
		t.Fatal("unpaid entitlement exported as paid")
	}
	if _, err := e.ReturnProof(t.Context(), "889", nil); err == nil {
		t.Fatal("founder claim historical hold bypassed")
	}
	c := FinancialProofContext{Protocol: 1, Kind: "claim_return", OwnerID: a.OwnerID, OperationID: a.OperationID, Sender: p.BettingEscrow, Recipient: p.Vault, AmountUWolo: a.AmountUWolo, Memo: "aoe2war/satchel/claim-return/v1/101", TxHash: testHTTPHash, FundedAmountUWolo: r.AmountUWolo, ReturnApproval: &a}
	if err := verifyReturnContext(c, p); err != nil {
		t.Fatalf("valid v2 independent attribution refused: %v", err)
	}
	a.Allocation.Legs[0].Entitlements[0].AmountUWolo = "980000"
	a.AmountUWolo = "980000"
	c.AmountUWolo = "980000"
	testSignAllocation(a.Allocation, p)
	a.AllocationDigest = AllocationDigest(*a.Allocation, p)
	testSignReturnApproval(&a, p)
	if err := verifyReturnContext(c, p); err == nil {
		t.Fatal("signed 98-percent unmatched refund escaped shared conservation validator")
	}
}

type httpProofTestBackend struct {
	*httpTestBackend
	calls atomic.Int32
	proof FinancialProof
	err   error
}

func (b *httpProofTestBackend) DepositProof(context.Context, DepositProofRequest) (FinancialProof, error) {
	b.calls.Add(1)
	return b.proof, b.err
}
func (b *httpProofTestBackend) OperationProof(context.Context, string) (FinancialProof, error) {
	b.calls.Add(1)
	return b.proof, b.err
}
func (b *httpProofTestBackend) ReturnProof(context.Context, string) (FinancialProof, error) {
	b.calls.Add(1)
	return b.proof, b.err
}

func TestPrivateFinancialProofReadOnlyAfterPermitExpiryAndCannotRetarget(t *testing.T) {
	for _, tc := range []struct {
		name, path, body string
		status           int
		calls            int32
	}{
		{"operation unavailable", "/satchel/v1/proofs/operation", `{"operation_id":"satchel:ticket:1"}`, 409, 1},
		{"retarget operation", "/satchel/v1/proofs/operation", `{"operation_id":"satchel:ticket:1","tx_hash":"` + testHTTPHash + `"}`, 400, 0},
		{"caller node", "/satchel/v1/proofs/operation", `{"operation_id":"satchel:ticket:1","rpc":"http://evil"}`, 400, 0},
		{"case alias", "/satchel/v1/proofs/operation", `{"Operation_ID":"satchel:ticket:1"}`, 400, 0},
		{"return unavailable", "/satchel/v1/proofs/return", `{"claim_id":"101"}`, 409, 1},
		{"claim889", "/satchel/v1/proofs/return", `{"claim_id":"889"}`, 400, 0},
		{"retarget claim owner", "/satchel/v1/proofs/return", `{"claim_id":"101","owner_id":"other"}`, 400, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			b := &httpProofTestBackend{httpTestBackend: &httpTestBackend{}, err: &satchel.EvidenceError{Code: satchel.UntrustedConsensus, Source: "trust", Operation: "test"}}
			cfg := testHTTPConfig(t)
			cfg.Authorize = func(context.Context) bool { return false }
			h := testHTTPHandler(t, b, cfg)
			w := httptest.NewRecorder()
			h.ServeHTTP(w, testHTTPRequest(http.MethodPost, tc.path, tc.body))
			if w.Code != tc.status || b.calls.Load() != tc.calls || b.submissions.Load() != 0 || b.reconciliations.Load() != 0 {
				t.Fatalf("read-only route contract: status=%d body=%s", w.Code, w.Body.String())
			}
			if tc.calls > 0 && testHTTPRead(t, w)["reason"] != string(satchel.UntrustedConsensus) {
				t.Fatal("typed chain failure lost")
			}
		})
	}
}

func TestFinancialProofDecodersRejectAliasesDuplicatesAndUnknownAuthority(t *testing.T) {
	for _, body := range []string{`{"protocol":1,"Protocol":1}`, `{"protocol":1,"protocol":1}`, `{"protocol":1,"rpc":"http://evil"}`, `{"protocol":1,"owner_mandate":{"challenge":{"ID":"alias"}}}`} {
		if _, err := DecodeFinancialProofContext([]byte(body)); err == nil {
			t.Fatalf("aliased or unknown trusted context accepted: %s", body)
		}
	}
	config, _ := json.Marshal(testVerifierAuthority(t))
	if _, err := DecodeFinancialProofVerifierConfig(config); err != nil {
		t.Fatal(err)
	}
	config = append(config[:len(config)-1], []byte(`,"rpc":"http://evil"}`)...)
	if _, err := DecodeFinancialProofVerifierConfig(config); err == nil {
		t.Fatal("proof-supplied source authority accepted")
	}
}

func TestFinancialProofSupportsExistingHDDotOwnerUIDContract(t *testing.T) {
	r := testDepositProofRequest(t)
	r.OwnerID = "owner.with.dot"
	c, _, err := depositContext(r, engineTestPolicy(t).Vault)
	if err != nil || c.OwnerID != r.OwnerID {
		t.Fatalf("HD-compatible owner UID refused: %v", err)
	}
	b := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, b)
	wager := engineTestWager(t, "1")
	wager.OwnerID = r.OwnerID
	if _, err := e.Submit(t.Context(), wager); err != nil {
		t.Fatalf("HD owner field refused by wager contract: %v", err)
	}
	_, context, err := e.operationProofRecord(wager.OperationID)
	if err != nil || context.OwnerID != r.OwnerID {
		t.Fatalf("journal-derived HD owner proof refused: %v", err)
	}
	p := forgedFinancialProof(t)
	p.Context.OwnerID = r.OwnerID
	p.ContextDigest = FinancialContextDigest(p.Context)
	if _, err := VerifyFinancialProof(t.Context(), testVerifierAuthority(t), p.Context, p); err != nil && err.Error() == "financial_proof_context_mismatch" {
		t.Fatal("verifier rejects owner UID before checking its actual chain proof")
	}
	for _, invalid := range []string{"owner with space", "owner\n", strings.Repeat("x", 101)} {
		r.OwnerID = invalid
		if _, _, err := depositContext(r, e.policy.Vault); err == nil {
			t.Fatal("HD-incompatible owner UID admitted")
		}
	}
}
