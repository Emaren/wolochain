package satchel

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func portableFixture(t *testing.T, kind string) (*readerFixture, PortableProof, *ProofVerifier) {
	t.Helper()
	f, validators := signedReaderFixture(t)
	primary := trustedFixtureServer(t, f, validators)
	witness := trustedFixtureServer(t, f, validators)
	r := adversarialTrustedReader(t, f, primary, witness, fixtureAnchor(f))
	var proof PortableProof
	var evidence AuthenticatedEvidence
	var err error
	if kind == "deposit" {
		evidence, proof, err = r.ReadDepositProof(context.Background(), f.intent, f.observation.TxHash)
	} else {
		evidence, proof, err = r.ReadTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash)
	}
	if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
		t.Fatalf("capture: %v", err)
	}
	// Verification must work with both sources shut down. The replay transport
	// owns no network path, DNS lookup or caller-configurable HTTP client.
	primary.Close()
	witness.Close()
	verifier, err := NewProofVerifier(fixtureAnchor(f))
	if err != nil {
		t.Fatal(err)
	}
	verifier.now = func() time.Time { return f.now }
	return f, proof, verifier
}

func transferFixtureIntent(f *readerFixture) TransferIntent {
	return TransferIntent{f.intent.Sender, f.intent.Vault, f.intent.AmountUWolo, f.intent.Memo}
}

func clonePortable(t *testing.T, proof PortableProof) PortableProof {
	t.Helper()
	copy, err := copyProof(proof, proof.Kind, proof.TxHash)
	if err != nil {
		t.Fatal(err)
	}
	return copy
}

func mutateResponse(t *testing.T, proof *PortableProof, source, path string, mutate func(map[string]any)) {
	t.Helper()
	matched := false
	for n := range proof.Responses {
		response := &proof.Responses[n]
		if response.Source != source || response.Path != path {
			continue
		}
		var body map[string]any
		if err := json.Unmarshal(response.Body, &body); err != nil {
			t.Fatal(err)
		}
		mutate(body)
		response.Body, _ = json.Marshal(body)
		matched = true
	}
	if !matched {
		t.Fatalf("missing fixture response %s %s", source, path)
	}
}

func assertPortableRefusal(t *testing.T, verifier *ProofVerifier, f *readerFixture, proof PortableProof) {
	t.Helper()
	evidence, err := verifier.VerifyTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash, proof)
	var typed *EvidenceError
	if err == nil || !errors.As(err, &typed) || evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
		t.Fatalf("malicious proof accepted or untyped: %v", err)
	}
}

func TestPortableProofReplaysActualCometAuthenticationOffline(t *testing.T) {
	for _, kind := range []string{"deposit", "transfer"} {
		t.Run(kind, func(t *testing.T) {
			f, proof, verifier := portableFixture(t, kind)
			encoded, err := json.Marshal(proof)
			if err != nil || len(encoded) > MaxPortableProofBytes || bytes.Contains(encoded, []byte("http://")) || bytes.Contains(encoded, []byte("evidence_reference")) {
				t.Fatalf("proof leaked source URLs/root or exceeded envelope: %v", err)
			}
			decoded, err := DecodePortableProof(encoded)
			if err != nil {
				t.Fatal(err)
			}
			var evidence AuthenticatedEvidence
			if kind == "deposit" {
				evidence, err = verifier.VerifyDepositProof(context.Background(), f.intent, f.observation.TxHash, decoded)
			} else {
				evidence, err = verifier.VerifyTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash, decoded)
			}
			if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || evidence.Receipt().TxHash != strings.ToUpper(f.observation.TxHash) {
				t.Fatalf("offline authentication failed: %v", err)
			}
			if CurrentCapability().Available() {
				t.Fatal("portable proof activated custody")
			}
		})
	}
}

func TestPortableProofRefusesForgedConsensusAndExecution(t *testing.T) {
	f, original, verifier := portableFixture(t, "transfer")
	for _, mode := range []string{"transaction_bytes", "failed_execution", "gas_commitment", "result_commitment", "forged_signature", "forged_validators", "invented_primary_head", "invented_witness_head", "wrong_rest_memo", "extra_transfer", "missing", "unused", "source_role", "query", "wrong_hash", "wrong_version", "wrong_chain", "wrong_kind"} {
		t.Run(mode, func(t *testing.T) {
			proof := clonePortable(t, original)
			switch mode {
			case "transaction_bytes":
				mutateResponse(t, &proof, "primary", "/tx", func(body map[string]any) { body["result"].(map[string]any)["tx"] = "Zm9yZ2Vk" })
			case "failed_execution":
				mutateResponse(t, &proof, "primary", "/tx", func(body map[string]any) { body["result"].(map[string]any)["tx_result"].(map[string]any)["code"] = 7 })
			case "gas_commitment", "result_commitment":
				mutateResponse(t, &proof, "primary", "/block_results", func(body map[string]any) {
					result := body["result"].(map[string]any)["txs_results"].([]any)[0].(map[string]any)
					if mode == "gas_commitment" {
						result["gas_used"] = "123"
					} else {
						result["code"] = 9
					}
				})
			case "forged_signature":
				for _, source := range []string{"primary", "witness"} {
					mutateResponse(t, &proof, source, "/commit", func(body map[string]any) {
						body["result"].(map[string]any)["signed_header"].(map[string]any)["commit"].(map[string]any)["signatures"].([]any)[0].(map[string]any)["signature"] = strings.Repeat("A", 84) + "AA=="
					})
				}
			case "forged_validators":
				mutateResponse(t, &proof, "primary", "/validators", func(body map[string]any) {
					body["result"].(map[string]any)["validators"].([]any)[0].(map[string]any)["voting_power"] = "11"
				})
			case "invented_primary_head", "invented_witness_head":
				source := "primary"
				if mode == "invented_witness_head" {
					source = "witness"
				}
				mutateResponse(t, &proof, source, "/status", func(body map[string]any) {
					body["result"].(map[string]any)["sync_info"].(map[string]any)["latest_block_hash"] = strings.Repeat("F", 64)
				})
			case "wrong_rest_memo":
				mutateResponse(t, &proof, "rest", "/cosmos/tx/v1beta1/txs/"+proof.TxHash, func(body map[string]any) {
					body["tx"].(map[string]any)["body"].(map[string]any)["memo"] = "forged-owner"
				})
			case "extra_transfer":
				mutateResponse(t, &proof, "primary", "/tx", func(body map[string]any) {
					result := body["result"].(map[string]any)["tx_result"].(map[string]any)
					result["events"] = append(result["events"].([]any), result["events"].([]any)[0])
				})
			case "missing":
				proof.Responses = proof.Responses[1:]
			case "unused":
				proof.Responses = append(proof.Responses, proof.Responses[0])
			case "source_role":
				proof.Responses[0].Source = "attacker"
			case "query":
				proof.Responses[0].Query = "height=100"
			case "wrong_hash":
				proof.TxHash = strings.Repeat("F", 64)
			case "wrong_version":
				proof.Version = 2
			case "wrong_chain":
				proof.ChainID = "forged-1"
			case "wrong_kind":
				proof.Kind = "deposit"
			}
			assertPortableRefusal(t, verifier, f, proof)
		})
	}
}

func TestPortableProofIndependentRootAndImmutableIntentRequired(t *testing.T) {
	f, proof, verifier := portableFixture(t, "transfer")
	anchor := fixtureAnchor(f)
	anchor.Hash = fmt.Sprintf("%064x", 42)
	wrongRoot, err := NewProofVerifier(anchor)
	if err != nil {
		t.Fatal(err)
	}
	wrongRoot.now = verifier.now
	assertPortableRefusal(t, wrongRoot, f, proof)
	for _, mode := range []string{"sender", "recipient", "amount", "memo", "hash"} {
		t.Run(mode, func(t *testing.T) {
			intent, hash := transferFixtureIntent(f), f.observation.TxHash
			switch mode {
			case "sender":
				intent.Sender = f.intent.Vault
			case "recipient":
				intent.Recipient = f.intent.Sender
			case "amount":
				intent.AmountUWolo = "1"
			case "memo":
				intent.Memo = "another-obligation"
			case "hash":
				hash = strings.Repeat("E", 64)
			}
			evidence, err := verifier.VerifyTransferProof(context.Background(), intent, hash, proof)
			if err == nil || evidence.ConsensusAuthenticated() {
				t.Fatal("proof satisfied a different immutable obligation")
			}
		})
	}
}

func TestPortableProofZeroCodeOmissionAndDeterministicConcurrentRetries(t *testing.T) {
	f, proof, verifier := portableFixture(t, "transfer")
	for n := range proof.Responses {
		var body any
		_ = json.Unmarshal(proof.Responses[n].Body, &body)
		var omitZero func(any)
		omitZero = func(value any) {
			switch object := value.(type) {
			case map[string]any:
				if code, ok := object["code"]; ok && (code == float64(0) || code == "0") {
					delete(object, "code")
				}
				for _, child := range object {
					omitZero(child)
				}
			case []any:
				for _, child := range object {
					omitZero(child)
				}
			}
		}
		omitZero(body)
		proof.Responses[n].Body, _ = json.Marshal(body)
	}
	var group sync.WaitGroup
	for n := 0; n < 8; n++ {
		group.Add(1)
		go func() {
			defer group.Done()
			evidence, err := verifier.VerifyTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash, proof)
			if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
				t.Errorf("read-only retry differed: %v", err)
			}
		}()
	}
	group.Wait()
}

func TestPortableProofCaptureDoesNotMutateSharedReader(t *testing.T) {
	f, validators := signedReaderFixture(t)
	reader := trustedFixture(t, f, validators, fixtureAnchor(f))
	originalClient := reader.reader.client
	originalTransport := originalClient.Transport
	var group sync.WaitGroup
	for n := 0; n < 6; n++ {
		group.Add(1)
		go func(capture bool) {
			defer group.Done()
			if capture {
				evidence, proof, err := reader.ReadTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash)
				if err != nil || !evidence.ConsensusAuthenticated() || len(proof.Responses) == 0 {
					t.Errorf("concurrent capture failed: %v", err)
				}
				return
			}
			evidence, err := readTrustedFixture(reader, f)
			if err != nil || !evidence.ConsensusAuthenticated() {
				t.Errorf("concurrent normal read failed: %v", err)
			}
		}(n%2 == 0)
	}
	group.Wait()
	if reader.reader.proof != nil || reader.reader.client != originalClient || originalClient.Transport != originalTransport {
		t.Fatal("proof capture changed live reader transport or capture state")
	}
}

func TestPortableProofFreshnessAndCancellationRemainLocal(t *testing.T) {
	f, proof, verifier := portableFixture(t, "transfer")
	verifier.now = func() time.Time { return f.now.Add(31 * time.Second) }
	assertPortableRefusal(t, verifier, f, proof)
	verifier.now = func() time.Time { return f.now }
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if evidence, err := verifier.VerifyTransferProof(ctx, transferFixtureIntent(f), f.observation.TxHash, proof); err == nil || evidence.ConsensusAuthenticated() {
		t.Fatal("canceled proof authenticated")
	}
	if _, err := NewProofVerifier(TrustAnchor{}); err == nil {
		t.Fatal("missing operator root accepted")
	}
}

func TestPortableProofCannotExpireDuringReplayOrExportCompletion(t *testing.T) {
	for _, mode := range []string{"head", "anchor", "deposit_intent"} {
		t.Run(mode, func(t *testing.T) {
			kind := "transfer"
			if mode == "deposit_intent" {
				kind = "deposit"
			}
			f, proof, verifier := portableFixture(t, kind)
			if mode == "anchor" {
				verifier.anchor.PeriodSeconds = 60
			}
			intent := f.intent
			intent.ExpiresAt = f.now.Add(time.Second)
			var calls atomic.Int32
			verifier.now = func() time.Time { calls.Add(1); return f.now }
			verify := func() error {
				if kind == "deposit" {
					_, err := verifier.VerifyDepositProof(context.Background(), intent, f.observation.TxHash, proof)
					return err
				}
				_, err := verifier.VerifyTransferProof(context.Background(), transferFixtureIntent(f), f.observation.TxHash, proof)
				return err
			}
			if err := verify(); err != nil {
				t.Fatal(err)
			}
			last := calls.Load()
			calls.Store(0)
			advance := 28 * time.Second
			want := StaleHead
			if mode == "anchor" {
				advance, want = 52*time.Second, UntrustedConsensus
			} else if mode == "deposit_intent" {
				advance, want = 2*time.Second, InvalidIntent
			}
			verifier.now = func() time.Time {
				if calls.Add(1) >= last {
					return f.now.Add(advance)
				}
				return f.now
			}
			var typed *EvidenceError
			if err := verify(); !errors.As(err, &typed) || typed.Code != want {
				t.Fatalf("expiration at final verification boundary was ignored: %v", err)
			}
		})
	}
}

func TestPortableProofStrictWireAndResourceBounds(t *testing.T) {
	f, proof, verifier := portableFixture(t, "transfer")
	encoded, _ := json.Marshal(proof)
	for _, wire := range [][]byte{[]byte(`{}`), []byte(`null`), append(append([]byte(nil), encoded...), []byte(`{}`)...), bytes.Replace(encoded, []byte(`"version":1`), []byte(`"version":1,"VERSION":1`), 1), bytes.Replace(encoded, []byte(`"version":1`), []byte(`"version":1,"anchor":{"height":1}`), 1), bytes.Replace(encoded, []byte(`"source":"primary"`), []byte(`"source":"primary","ſource":"witness"`), 1), bytes.Repeat([]byte(" "), MaxPortableProofBytes+1)} {
		if _, err := DecodePortableProof(wire); err == nil {
			t.Fatal("malformed or ambiguous wire accepted")
		}
	}
	for _, mode := range []string{"large_response", "too_many", "html_expansion", "large_query", "write_path"} {
		t.Run(mode, func(t *testing.T) {
			bad := clonePortable(t, proof)
			switch mode {
			case "large_response":
				bad.Responses[0].Body = []byte(`{"padding":"` + strings.Repeat("x", maxResponseBytes) + `"}`)
			case "too_many":
				for len(bad.Responses) <= maxProofResponses {
					bad.Responses = append(bad.Responses, bad.Responses[0])
				}
			case "html_expansion":
				bad.Responses = nil
				for n := 0; n < 4; n++ {
					bad.Responses = append(bad.Responses, ProofResponse{"primary", "/status", "", []byte(`{"padding":"` + strings.Repeat("<", maxResponseBytes-32) + `"}`)})
				}
			case "large_query":
				bad.Responses[0].Query = "height=" + strings.Repeat("1", 600)
			case "write_path":
				bad.Responses[0].Path = "/broadcast_tx_sync"
			}
			assertPortableRefusal(t, verifier, f, bad)
		})
	}
}

func TestPortableDepositAcceptsOnlyExactSignedFeeAndCanonicalMessageIdentity(t *testing.T) {
	for _, mode := range []string{"fee_before_send", "logs_without_fee", "wrong_fee", "extra", "reordered_logs", "duplicate_fee", "foreign_fee_sender", "foreign_fee_recipient"} {
		t.Run(mode, func(t *testing.T) {
			f, validators := feeFixture(t, mode)
			if mode == "duplicate_fee" {
				f.tx.TxResult.Events = append(f.tx.TxResult.Events, f.tx.TxResult.Events[0])
			} else if mode == "foreign_fee_sender" {
				f.tx.TxResult.Events[0].Attributes[0].Value = f.intent.Vault
			} else if mode == "foreign_fee_recipient" {
				f.tx.TxResult.Events[0].Attributes[1].Value = f.intent.Vault
			}
			f.results.TxsResults[0].Events = f.tx.TxResult.Events
			f.rest["tx_response"].(map[string]any)["events"] = transferEvents(f.tx.TxResult.Events)
			reader := trustedFixture(t, f, validators, fixtureAnchor(f))
			evidence, proof, err := reader.ReadDepositProof(context.Background(), f.intent, f.observation.TxHash)
			if mode != "fee_before_send" && mode != "logs_without_fee" {
				if err == nil || evidence.ConsensusAuthenticated() {
					t.Fatal("ambiguous fee-paying deposit authenticated")
				}
				return
			}
			if err != nil || evidence.Receipt().TransferIndex != 0 {
				t.Fatalf("valid fee-paying deposit failed: %v", err)
			}
			verifier, _ := NewProofVerifier(fixtureAnchor(f))
			verifier.now = func() time.Time { return f.now }
			verified, err := verifier.VerifyDepositProof(context.Background(), f.intent, f.observation.TxHash, proof)
			if err != nil || !verified.ConsensusAuthenticated() || verified.Receipt().ID() != evidence.Receipt().ID() || verified.Receipt().TransferIndex != 0 {
				t.Fatalf("portable fee-paying deposit failed: %v", err)
			}
		})
	}
}
