package satchelservice

// Native assets and the original funding/paid return below execute in an
// isolated real SDK app. Inventory coverage and both financial reviewer keys
// are controlled TEST authorities, never evidence of production independence.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"cosmossdk.io/collections"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmt "github.com/cometbft/cometbft/types"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	sdk "github.com/cosmos/cosmos-sdk/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	authsign "github.com/cosmos/cosmos-sdk/x/auth/signing"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

type escrowExecutionFixture struct {
	engine              *Engine
	chain               *nativeHTTPChain
	reader              *satchel.TrustedReader
	backend             *KeyringBackend
	signer              *testBackendSigner
	accounting, custody ed25519.PrivateKey
	config              EscrowReturnExecutionConfig
	verifier            *EscrowReturnExecutionVerifier
	plan                ReturnAllocation
	donationHash        string
}

// Additional transfers reuse the committed nativeHTTP fixture's real SDK app,
// consensus commits and RPC/REST evidence. No untracked product fixture is used.
func escrowExecutionSDKSend(t *testing.T, chain *nativeHTTPChain, key *sdksecp.PrivKey, recipient, amount, memo string) string {
	t.Helper()
	chain.mu.Lock()
	defer chain.mu.Unlock()
	address := sdk.AccAddress(key.PubKey().Address())
	ctx := chain.application.NewUncachedContext(false, cmtproto.Header{Height: chain.head})
	account := chain.application.AuthKeeper.GetAccount(ctx, address)
	require.NotNil(t, account)
	to, err := sdk.GetFromBech32(recipient, "wolo")
	require.NoError(t, err)
	n, err := strconv.ParseInt(amount, 10, 64)
	require.NoError(t, err)
	builder := chain.application.TxConfig().NewTxBuilder()
	require.NoError(t, builder.SetMsgs(banktypes.NewMsgSend(address, sdk.AccAddress(to), sdk.NewCoins(sdk.NewInt64Coin("uwolo", n)))))
	builder.SetMemo(memo)
	builder.SetFeeAmount(sdk.NewCoins(sdk.NewInt64Coin("uwolo", 2500)))
	builder.SetGasLimit(200000)
	mode, err := authsign.APISignModeToInternal(chain.application.TxConfig().SignModeHandler().DefaultMode())
	require.NoError(t, err)
	sig := signing.SignatureV2{PubKey: key.PubKey(), Data: &signing.SingleSignatureData{SignMode: mode}, Sequence: account.GetSequence()}
	require.NoError(t, builder.SetSignatures(sig))
	signBytes, err := authsign.GetSignBytesAdapter(t.Context(), chain.application.TxConfig().SignModeHandler(), mode, authsign.SignerData{
		Address: address.String(), ChainID: "wolo-1", AccountNumber: account.GetAccountNumber(), Sequence: account.GetSequence(), PubKey: key.PubKey()}, builder.GetTx())
	require.NoError(t, err)
	sig.Data.(*signing.SingleSignatureData).Signature, err = key.Sign(signBytes)
	require.NoError(t, err)
	require.NoError(t, builder.SetSignatures(sig))
	raw, err := chain.application.TxConfig().TxEncoder()(builder.GetTx())
	require.NoError(t, err)
	result := chain.commit(t, [][]byte{raw})
	require.Len(t, result.TxResults, 1)
	require.Zero(t, result.TxResults[0].Code, result.TxResults[0].Log)
	tx := cmt.Tx(raw)
	hash := strings.ToUpper(hex.EncodeToString(tx.Hash()))
	chain.transaction = &core.ResultTx{Hash: tx.Hash(), Height: chain.head, Index: 0, TxResult: *result.TxResults[0], Tx: tx, Proof: cmt.Txs{tx}.Proof(0)}
	var txRaw txapi.TxRaw
	var body txapi.TxBody
	require.NoError(t, proto.Unmarshal(raw, &txRaw))
	require.NoError(t, proto.Unmarshal(txRaw.BodyBytes, &body))
	encoded, err := protojson.Marshal(&body)
	require.NoError(t, err)
	var bodyObject map[string]any
	require.NoError(t, json.Unmarshal(encoded, &bodyObject))
	encoded, err = json.Marshal(result.TxResults[0])
	require.NoError(t, err)
	var resultObject map[string]any
	require.NoError(t, json.Unmarshal(encoded, &resultObject))
	resultObject["height"], resultObject["txhash"], resultObject["timestamp"], resultObject["logs"] = strconv.FormatInt(chain.head, 10), hash, chain.commits[chain.head].Time.Format(time.RFC3339Nano), []any{}
	delete(resultObject, "code")
	chain.rest = map[string]any{"tx": map[string]any{"body": bodyObject}, "tx_response": resultObject}
	for n := 0; n < 3; n++ {
		chain.commit(t, nil)
	}
	return hash
}

func newEscrowExecutionFixture(t *testing.T) *escrowExecutionFixture {
	t.Helper()
	f := &escrowExecutionFixture{}
	old := newBackendFixture(t)
	f.signer = old.signer
	f.chain = newNativeHTTPChainWithBalance(t, f.signer, 100000000)
	primary, witness := f.chain.serve(t, false), f.chain.serve(t, true)
	anchor := satchel.TrustAnchor{Height: 1, Hash: hex.EncodeToString(f.chain.commits[1].Header.Hash()), PeriodSeconds: 3600, EvidenceReference: "isolated-escrow-execution-SDK-test-only"}
	var err error
	f.reader, err = satchel.NewTrustedReader(satchel.SourceConfig{RPC: primary.URL, REST: primary.URL, WitnessRPC: witness.URL}, anchor)
	require.NoError(t, err)
	t.Cleanup(f.reader.Close)
	p := Policy{Vault: old.request.Sender, BettingEscrow: old.request.Recipient, ProtectedAddresses: []string{old.request.Recipient}, MaxAmountUWolo: 1000000000,
		WithdrawalApprovalKey: engineTestApprovalKey().Public().(ed25519.PublicKey), WagerApprovalKey: engineTestWagerApprovalKey().Public().(ed25519.PublicKey)}
	bc := old.b.cfg
	bc.RPC, bc.REST, bc.WitnessRPC = primary.URL, primary.URL, witness.URL
	bc.ConfirmTransaction = func(ctx context.Context, r TransferRequest, signed SignedTransaction) (Confirmation, error) {
		evidence, err := f.reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, signed.Hash)
		if err != nil || !evidence.ConsensusAuthenticated() || !bytes.Equal(evidence.Observation().TxBytes, signed.Bytes) {
			return Confirmation{}, ErrBackend
		}
		return Confirmation{Status: "CONFIRMED", ReceiptID: evidence.Receipt().ID(), Height: evidence.Observation().Height, BlockHash: evidence.Observation().BlockHash}, nil
	}
	f.backend, err = newBackend(bc)
	require.NoError(t, err)
	f.backend.signer = f.signer
	t.Cleanup(f.backend.Close)
	dir, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)
	f.engine, err = Open(filepath.Join(dir, "escrow-execution.db"), p, f.backend)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, f.engine.Close()) })
	f.chain.release()
	accepted, err := f.engine.Submit(t.Context(), old.request)
	require.NoError(t, err)
	require.Equal(t, "ACCEPTED", accepted.Status)
	confirmed, err := f.engine.Reconcile(t.Context(), old.request.OperationID)
	require.NoError(t, err)
	require.Equal(t, "CONFIRMED", confirmed.Status)
	f.donationHash = escrowExecutionSDKSend(t, f.chain, f.signer.key, p.BettingEscrow, "2000000", "isolated external escrow assets")
	escrow, err := sdk.GetFromBech32(p.BettingEscrow, "wolo")
	require.NoError(t, err)
	f.chain.bankKey, err = collections.EncodeKeyWithPrefix(banktypes.BalancesPrefix, collections.PairKeyCodec(sdk.AccAddressKey, collections.StringKey), collections.Join(sdk.AccAddress(escrow), "uwolo"))
	require.NoError(t, err)
	bank, _, err := f.reader.ReadCurrentBankProof(t.Context(), p.BettingEscrow)
	require.NoError(t, err)
	require.Equal(t, "9000000", bank.BalanceUWolo())
	at := time.Now().Unix()
	f.plan = ReturnAllocation{Version: 2, AllocationID: "allocation:ticket:7", Revision: 1, OperationID: old.request.OperationID, OwnerID: old.request.OwnerID, TicketID: "7", FundingTxHash: confirmed.TxHash,
		ReturnCapUWolo: "7000000", FundsBudgetID: "isolated-original-budget", FundsAvailableUWolo: "9000000", BankEvidenceDigest: strings.Repeat("E", 64), BankHeight: bank.Height(), BankBlockHash: bank.BlockHash(), IssuedAt: at - 1, ExpiresAt: at + 120,
		Legs: []ReturnLeg{
			{LegID: "desync", MarketID: "502", StakeUWolo: "2000000", Entitlements: []ReturnEntitlement{{EntitlementID: "desync-refund", ClaimID: "102", ClaimKind: "bet_refund", PrincipalUWolo: "2000000", AmountUWolo: "2000000"}}},
			{LegID: "winner", MarketID: "501", StakeUWolo: "5000000", Entitlements: []ReturnEntitlement{{EntitlementID: "winner-payout", ClaimID: "101", ClaimKind: "bet_payout", PrincipalUWolo: "5000000", AmountUWolo: "5000000"}}},
		}}
	testSignAllocation(&f.plan, p)
	f.accounting = ed25519.NewKeyFromSeed(bytes.Repeat([]byte{81}, ed25519.SeedSize))
	f.custody = ed25519.NewKeyFromSeed(bytes.Repeat([]byte{82}, ed25519.SeedSize))
	execution := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{79}, ed25519.SeedSize))
	f.config = EscrowReturnExecutionConfig{Authority: ReserveReviewAuthority{AccountingReviewerKey: f.accounting.Public().(ed25519.PublicKey), CustodyReviewerKey: f.custody.Public().(ed25519.PublicKey),
		ExecutionAuthorityKey: execution.Public().(ed25519.PublicKey), WagerApprovalKey: p.WagerApprovalKey, WithdrawalApprovalKey: p.WithdrawalApprovalKey,
		ExpectedVault: p.BettingEscrow, ExpectedBuildSHA256: strings.Repeat("1", 64), ExpectedConfigSHA256: strings.Repeat("2", 64), ExpectedPermitSHA256: strings.Repeat("3", 64)},
		TrustAnchor: anchor, PaidReturnProofReader: f.reader, ExpectedCustodyPolicySHA256: hashJSON(p), FeeUWolo: "2500", MaximumFeeUWolo: "1000000", MinimumGasReserveUWolo: "2500", MinimumUnencumberedUWolo: "1000"}
	for _, id := range reviewerRequiredReserveProducers {
		f.config.Producers = append(f.config.Producers, EscrowReturnProducerPin{ProducerID: id, SourceSHA256: hashJSON([]string{"test-only-source", id})})
	}
	f.verifier, err = NewEscrowReturnExecutionVerifier(f.engine, f.config)
	require.NoError(t, err)
	return f
}

func (f *escrowExecutionFixture) bundle(t *testing.T, claim string) (ReturnApproval, satchel.AuthenticatedBankEvidence, satchel.BankProof, CustodyJournal, EscrowReturnExecutionBundle) {
	t.Helper()
	a := multiLegApproval(t, f.plan, claim, f.engine.policy)
	bank, proof, err := f.reader.ReadCurrentBankProof(t.Context(), f.engine.policy.BettingEscrow)
	require.NoError(t, err)
	journal := readTestCustodyJournal(t, f.engine)
	body := EscrowReturnExecutionBody{Protocol: 1, Scope: EscrowReturnExecutionScope, Escrow: f.engine.policy.BettingEscrow, Vault: f.engine.policy.Vault, OperationID: a.OperationID, ClaimID: a.ClaimID, OwnerID: a.OwnerID,
		TicketID: a.TicketID, MarketID: a.MarketID, LegID: a.LegID, EntitlementID: a.EntitlementID, ClaimKind: a.ClaimKind, AmountUWolo: a.AmountUWolo, AllocationDigest: a.AllocationDigest,
		OriginalBankEvidenceDigest: a.Allocation.BankEvidenceDigest, FundsBudgetID: a.Allocation.FundsBudgetID, JournalSHA256: journal.JournalDigest, PolicySHA256: journal.PolicyDigest,
		Producers: []EscrowReturnExecutionProducer{}, NonOverlap: []ReviewerReserveNonOverlap{}}
	var confirmed uint64
	for _, pin := range f.verifier.config.Producers {
		producer := EscrowReturnExecutionProducer{ProducerID: pin.ProducerID, SourceSHA256: pin.SourceSHA256, CheckpointSHA256: hashJSON([]string{"controlled-test-external-checkpoint", pin.ProducerID, journal.JournalDigest}), Obligations: []ReviewerReserveObligation{}, PendingFees: []ReviewerPendingFee{}}
		if pin.ProducerID == reviewerOwnerLedgerProducer {
			for _, leg := range f.plan.Legs {
				for _, ent := range leg.Entitlements {
					var paid bool
					require.NoError(t, f.engine.db.View(func(tx *bolt.Tx) error {
						if b := tx.Bucket(returns); b != nil {
							if raw := b.Get([]byte(ent.ClaimID)); raw != nil {
								var r returnRecord
								if err := json.Unmarshal(raw, &r); err != nil {
									return err
								}
								paid = r.Receipt != nil
							}
						}
						return nil
					}))
					if !paid {
						producer.Obligations = append(producer.Obligations, ReviewerReserveObligation{EconomicKey: escrowReturnClaimKey(ent.ClaimID), Kind: "confirmed", AmountUWolo: ent.AmountUWolo})
						n, _ := strconv.ParseUint(ent.AmountUWolo, 10, 64)
						confirmed += n
					}
				}
			}
		}
		if pin.ProducerID == "hd_manual_and_founder_obligations" {
			producer.Obligations = append(producer.Obligations, ReviewerReserveObligation{EconomicKey: "fixture-unknown-exposure", Kind: "unknown", AmountUWolo: "1"})
		}
		sort.Slice(producer.Obligations, func(i, j int) bool { return producer.Obligations[i].EconomicKey < producer.Obligations[j].EconomicKey })
		body.Producers = append(body.Producers, producer)
	}
	review := SignedReserveReview{Version: 1, Scope: reserveReviewScope, ChainID: "wolo-1", Denom: "uwolo", Vault: f.engine.policy.BettingEscrow, StateHeight: bank.Height(), CommitBlockHash: bank.BlockHash(), ObservedBankUWolo: bank.BalanceUWolo(),
		ConfirmedLiabilitiesUWolo: strconv.FormatUint(confirmed, 10), UncertainMaxLiabilitiesUWolo: "1", GasReserveUWolo: "2500", UnencumberedMinimumUWolo: "1000", JournalSnapshotSHA256: journal.JournalDigest,
		BuildSHA256: f.config.Authority.ExpectedBuildSHA256, ConfigSHA256: f.config.Authority.ExpectedConfigSHA256, PermitSHA256: f.config.Authority.ExpectedPermitSHA256,
		AllObligationsCovered: true, UnknownClaimsReserved: true, DedicatedVaultIsolated: true, IssuedAt: time.Now().Unix() - 1, ExpiresAt: time.Now().Unix() + 15}
	bundle := EscrowReturnExecutionBundle{Version: 1, Review: review, Body: body}
	f.sign(t, &bundle)
	return a, bank, proof, journal, bundle
}

func (f *escrowExecutionFixture) sign(t *testing.T, b *EscrowReturnExecutionBundle) []byte {
	t.Helper()
	b.Body.NonOverlap = []ReviewerReserveNonOverlap{}
	for _, producer := range b.Body.Producers {
		for _, obligation := range producer.Obligations {
			b.Body.NonOverlap = append(b.Body.NonOverlap, ReviewerReserveNonOverlap{EconomicKey: obligation.EconomicKey, ProducerID: producer.ProducerID})
		}
		for _, fee := range producer.PendingFees {
			b.Body.NonOverlap = append(b.Body.NonOverlap, ReviewerReserveNonOverlap{EconomicKey: "fee:" + fee.OperationID, ProducerID: producer.ProducerID})
		}
	}
	sort.Slice(b.Body.NonOverlap, func(i, j int) bool { return b.Body.NonOverlap[i].EconomicKey < b.Body.NonOverlap[j].EconomicKey })
	b.Review.LiabilityInventorySHA256 = EscrowReturnExecutionBodyDigest(b.Body)
	b.Review.NonOverlapWitnessSHA256 = EscrowReturnExecutionNonOverlapDigest(b.Body.NonOverlap)
	signReview(&b.Review, f.accounting, f.custody)
	raw, err := json.Marshal(b)
	require.NoError(t, err)
	return raw
}

func TestEscrowReturnExecutionRealSDKAssetsBookPrincipalOnceWithoutSigning(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	a, bank, proof, journal, bundle := f.bundle(t, "101")
	before := readTestCustodyJournal(t, f.engine)
	signs, broadcasts := f.signer.calls.Load(), f.chain.broadcasts
	qualified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &bundle))
	require.NoError(t, err)
	require.True(t, qualified.CurrentFor(t.Context(), a))
	require.False(t, qualified.ExpiresAt().IsZero())
	assets, _ := reviewerAmount(bank.BalanceUWolo(), math.MaxInt64, true)
	selected, _ := reviewerAmount(a.AmountUWolo, math.MaxInt64, true)
	confirmed, _ := reviewerAmount(bundle.Review.ConfirmedLiabilitiesUWolo, math.MaxInt64, true)
	require.Less(t, assets, confirmed+selected, "fixture must catch requiring booked payout principal twice")
	require.Equal(t, before, readTestCustodyJournal(t, f.engine))
	require.Equal(t, signs, f.signer.calls.Load())
	require.Equal(t, broadcasts, f.chain.broadcasts)
	wire, err := json.Marshal(qualified)
	require.NoError(t, err)
	require.Equal(t, "{}", string(wire))
	var forged VerifiedEscrowReturnExecution
	require.NoError(t, json.Unmarshal(wire, &forged))
	require.False(t, forged.CurrentFor(t.Context(), a))
}

func TestEscrowReturnExecutionRejectsSignedButIncompleteOrRetargetedInventory(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	for _, name := range []string{"owner", "root", "height", "source_changed", "missing_producer", "missing_leg", "underreserve", "external_fee", "zero_unknown", "original_bank_redefined", "future", "stale", "role_signature", "build", "policy"} {
		t.Run(name, func(t *testing.T) {
			a, bank, proof, journal, b := f.bundle(t, "101")
			switch name {
			case "owner":
				b.Body.OwnerID = "different-owner"
			case "root":
				b.Review.CommitBlockHash = strings.Repeat("F", 64)
			case "height":
				b.Review.StateHeight++
			case "source_changed":
				b.Body.Producers[0].SourceSHA256 = strings.Repeat("f", 64)
			case "missing_producer":
				b.Body.Producers = b.Body.Producers[1:]
			case "missing_leg", "underreserve":
				for i := range b.Body.Producers {
					if b.Body.Producers[i].ProducerID == reviewerOwnerLedgerProducer {
						b.Body.Producers[i].Obligations = b.Body.Producers[i].Obligations[:1]
					}
				}
				b.Review.ConfirmedLiabilitiesUWolo = "5000000"
			case "external_fee":
				b.Body.Producers[0].PendingFees = []ReviewerPendingFee{{OperationID: "external:pending:1", Stage: "uncertain", FeeUWolo: "1000000"}}
			case "zero_unknown":
				b.Review.UncertainMaxLiabilitiesUWolo = "0"
			case "original_bank_redefined":
				b.Body.OriginalBankEvidenceDigest = bank.BlockHash()
			case "future":
				b.Review.IssuedAt = time.Now().Unix() + 2
			case "stale":
				b.Review.IssuedAt = time.Now().Unix() - 20
				b.Review.ExpiresAt = time.Now().Unix() - 1
			case "build":
				b.Review.BuildSHA256 = strings.Repeat("f", 64)
			case "policy":
				b.Body.PolicySHA256 = strings.Repeat("f", 64)
			}
			raw := f.sign(t, &b)
			if name == "role_signature" {
				b.Review.AccountingReviewerSignature = b.Review.CustodyReviewerSignature
				raw, _ = json.Marshal(b)
			}
			got, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, raw)
			require.ErrorIs(t, err, ErrEscrowReturnExecution)
			require.False(t, got.CurrentFor(t.Context(), a))
		})
	}
}

func TestEscrowReturnExecutionGenuinePaidLegDischargeKeepsOriginalAllocation(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	winner := multiLegApproval(t, f.plan, "101", f.engine.policy)
	_, err := f.engine.PrepareReturnRun(t.Context(), winner)
	require.NoError(t, err)
	escrowKey := &sdksecp.PrivKey{Key: bytes.Repeat([]byte{9}, 32)}
	hash := escrowExecutionSDKSend(t, f.chain, escrowKey, f.engine.policy.Vault, winner.AmountUWolo, "aoe2war/satchel/claim-return/v1/101")
	paid, err := f.engine.ReconcileReturn(t.Context(), winner, hash, f.reader)
	require.NoError(t, err)
	require.Equal(t, hash, paid.TxHash)
	a, bank, proof, journal, b := f.bundle(t, "102")
	require.Greater(t, bank.Height(), a.Allocation.BankHeight)
	require.Equal(t, f.plan.BankEvidenceDigest, b.Body.OriginalBankEvidenceDigest)
	require.Equal(t, "2000000", b.Review.ConfirmedLiabilitiesUWolo)
	before := readTestCustodyJournal(t, f.engine)
	qualified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.NoError(t, err)
	require.True(t, qualified.CurrentFor(t.Context(), a))
	require.Equal(t, before, readTestCustodyJournal(t, f.engine))
	// A paid selected claim cannot acquire another execution qualification.
	a, bank, proof, journal, b = f.bundle(t, "101")
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
}

func TestEscrowReturnExecutionPreparedUnknownFeeNeverDisappearsFromInventory(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	refund := multiLegApproval(t, f.plan, "102", f.engine.policy)
	_, err := f.engine.PrepareReturnRun(t.Context(), refund)
	require.NoError(t, err)
	a, bank, proof, journal, b := f.bundle(t, "101")
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.ErrorIs(t, err, ErrEscrowReturnExecution, "an unsigned/UNKNOWN return still needs fee headroom")
	for i := range b.Body.Producers {
		if b.Body.Producers[i].ProducerID == reviewerPendingFeesProducer {
			b.Body.Producers[i].PendingFees = []ReviewerPendingFee{{OperationID: escrowReturnClaimKey("102"), Stage: "uncertain", FeeUWolo: "1000000"}}
		}
	}
	b.Review.GasReserveUWolo = "1002500" // pending UNKNOWN + distinct new return fee
	qualified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.NoError(t, err)
	require.True(t, qualified.CurrentFor(t.Context(), a))
	// Lowering either the known fee or its reserve cannot manufacture equity.
	b.Review.GasReserveUWolo = "1002499"
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
}

func TestEscrowReturnExecutionOpaqueResultCannotAdoptUnreviewedAllocationRevision(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	// Leave one unit of principal/return cap for a later append-only review.
	// The selected claim economics and original funds identity stay unchanged.
	f.plan.ReturnCapUWolo = "7000001"
	f.plan.Legs[1].Entitlements[0].PrincipalUWolo = "4999999"
	testSignAllocation(&f.plan, f.engine.policy)
	a, bank, proof, journal, b := f.bundle(t, "101")
	qualified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.NoError(t, err)
	raw, err := json.Marshal(f.plan)
	require.NoError(t, err)
	var next ReturnAllocation
	require.NoError(t, json.Unmarshal(raw, &next))
	next.Revision++
	next.Legs[1].Entitlements = append(next.Legs[1].Entitlements, ReturnEntitlement{EntitlementID: "winner-payout-z", ClaimID: "103", ClaimKind: "bet_payout", PrincipalUWolo: "1", AmountUWolo: "1"})
	testSignAllocation(&next, f.engine.policy)
	changed := multiLegApproval(t, next, "101", f.engine.policy)
	require.Equal(t, returnFingerprint(a), returnFingerprint(changed), "economic replay identity deliberately excludes plan revisions")
	require.NotEqual(t, a.AllocationDigest, changed.AllocationDigest)
	require.NoError(t, f.engine.db.View(func(tx *bolt.Tx) error { return f.engine.validateReturnAt(tx, changed, true) }))
	require.False(t, qualified.CurrentFor(t.Context(), changed), "newly allocated liabilities need their own complete inventory review")
}

type escrowExecutionPaidTranscript struct{ proof satchel.PortableProof }

func (p escrowExecutionPaidTranscript) ReadTransferProof(context.Context, satchel.TransferIntent, string) (satchel.AuthenticatedEvidence, satchel.PortableProof, error) {
	return satchel.AuthenticatedEvidence{}, p.proof, nil
}

func TestEscrowReturnExecutionForgedDurablePaidReceiptRequiresActualReturnProof(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	_, donation, err := f.reader.ReadTransferProof(t.Context(), satchel.TransferIntent{Sender: f.engine.policy.Vault, Recipient: f.engine.policy.BettingEscrow, AmountUWolo: "2000000", Memo: "isolated external escrow assets"}, f.donationHash)
	require.NoError(t, err)
	refund := multiLegApproval(t, f.plan, "102", f.engine.policy)
	_, err = f.engine.PrepareReturnRun(t.Context(), refund)
	require.NoError(t, err)
	// Fault injection mimics valid-shaped unkeyed journal corruption. The real
	// SDK transaction is the reverse transfer, NOT payment of this claim.
	receipt := testFaultInjectedReturnReceipt(refund, f.donationHash, 1)
	receipt.Height = f.chain.transaction.Height
	receipt.BlockHash = strings.ToUpper(hex.EncodeToString(f.chain.commits[receipt.Height].Header.Hash()))
	require.NoError(t, f.engine.recordReturn(testStoredReturn(t, f.engine, "102"), receipt))
	f.verifier.config.PaidReturnProofReader = escrowExecutionPaidTranscript{proof: donation}
	a, bank, proof, journal, b := f.bundle(t, "101")
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, f.sign(t, &b))
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
}

func TestEscrowReturnExecutionRejectsCrossRootStaleJournalExpiryAndDTO(t *testing.T) {
	f := newEscrowExecutionFixture(t)
	a, bank, proof, journal, b := f.bundle(t, "101")
	raw := f.sign(t, &b)
	wrong := f.config
	wrong.TrustAnchor.Hash = strings.Repeat("F", 64)
	verifier, err := NewEscrowReturnExecutionVerifier(f.engine, wrong)
	require.NoError(t, err)
	_, err = verifier.Verify(t.Context(), a, bank, proof, journal, raw)
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
	for _, body := range [][]byte{[]byte(`{"version":1,"complete":true}`), append([]byte(`{"Version":1,`), raw[1:]...), bytes.Repeat([]byte(" "), escrowReturnExecutionMaxBytes+1)} {
		_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, body)
		require.ErrorIs(t, err, ErrEscrowReturnExecution)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err = f.verifier.Verify(ctx, a, bank, proof, journal, raw)
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
	qualified, err := f.verifier.Verify(t.Context(), a, bank, proof, journal, raw)
	require.NoError(t, err)
	require.NoError(t, f.engine.db.Update(func(tx *bolt.Tx) error {
		bucket, err := tx.CreateBucket([]byte("source-changed"))
		if err != nil {
			return err
		}
		return bucket.Put([]byte("checkpoint"), []byte("changed"))
	}))
	require.False(t, qualified.CurrentFor(t.Context(), a))
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, raw)
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
	f.verifier.now = func() time.Time { return time.Now().Add(40 * time.Second) }
	_, err = f.verifier.Verify(t.Context(), a, bank, proof, journal, raw)
	require.ErrorIs(t, err, ErrEscrowReturnExecution)
	// Read paths must not have changed the original durable funding record.
	var stored record
	require.NoError(t, f.engine.db.View(func(tx *bolt.Tx) error { var err error; stored, err = load(tx, a.OperationID); return err }))
	require.Equal(t, "CONFIRMED", stored.Result.Status)
	require.Equal(t, "7000000", stored.Request.AmountUWolo)
	require.False(t, reflect.DeepEqual(qualified, VerifiedEscrowReturnExecution{}))
	require.True(t, errors.Is(err, ErrEscrowReturnExecution))
}
