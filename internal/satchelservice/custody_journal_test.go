package satchelservice

import (
	"encoding/json"
	"errors"
	"math"
	"reflect"
	"strconv"
	"strings"
	"testing"

	bolt "go.etcd.io/bbolt"
)

func readTestCustodyJournal(t *testing.T, e *Engine) CustodyJournal {
	t.Helper()
	j, err := e.CustodyJournal()
	if err != nil {
		t.Fatal(err)
	}
	if j.Protocol != 1 || j.Kind != "execution_journal_checkpoint" || j.ChainID != "wolo-1" || j.Denom != "uwolo" || j.BankBalanceAuthenticated || j.CreditAuthorized || j.SolvencyAuthorized || j.CustodyCapability != "UNAVAILABLE" || !nonzeroDigest(j.JournalDigest) || j.PolicyDigest != hashJSON(e.policy) {
		t.Fatalf("execution checkpoint invented financial authority: %+v", j)
	}
	return j
}

func TestCustodyJournalTracksUncertaintyAndRestartWithoutFinancialCalls(t *testing.T) {
	b := &engineTestBackend{confirmationStatus: "CONFIRMED"}
	e, path, p := engineTestOpen(t, b)
	empty := readTestCustodyJournal(t, e)
	r := engineTestWager(t, "1")
	if _, err := e.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	accepted := readTestCustodyJournal(t, e)
	if accepted.JournalDigest == empty.JournalDigest || accepted.OperationsCount != 1 || accepted.UnresolvedCount != 1 || accepted.HeldOutboundUWolo != r.AmountUWolo || accepted.ConfirmedOutboundUWolo != "0" || accepted.OperationStatusCounts["ACCEPTED"] != 1 {
		t.Fatalf("broadcast acceptance lost its full unresolved obligation: %+v", accepted)
	}
	if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
		t.Fatal(err)
	}
	confirmed := readTestCustodyJournal(t, e)
	if confirmed.JournalDigest == accepted.JournalDigest || confirmed.UnresolvedCount != 0 || confirmed.HeldOutboundUWolo != "0" || confirmed.ConfirmedOutboundUWolo != r.AmountUWolo || confirmed.OperationStatusCounts["CONFIRMED"] != 1 {
		t.Fatalf("committed history not classified exactly: %+v", confirmed)
	}
	if b.signs.Load() != 1 || b.broadcasts.Load() != 1 || b.confirmations.Load() != 1 {
		t.Fatal("checkpoint performed financial IO")
	}
	if err := e.Close(); err != nil {
		t.Fatal(err)
	}
	newBackend := &engineTestBackend{}
	reopened, err := Open(path, p, newBackend)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	if got := readTestCustodyJournal(t, reopened); !reflect.DeepEqual(got, confirmed) {
		t.Fatalf("restart changed the same durable checkpoint: %+v / %+v", got, confirmed)
	}
	if newBackend.signs.Load() != 0 || newBackend.broadcasts.Load() != 0 || newBackend.confirmations.Load() != 0 {
		t.Fatal("restart checkpoint transmitted or reconciled a payment")
	}
}

func TestCustodyJournalRetainsUnknownAndObservedPrincipal(t *testing.T) {
	for _, status := range []string{"UNKNOWN", "OBSERVED_NONCREDITING"} {
		t.Run(status, func(t *testing.T) {
			b := &engineTestBackend{confirmationStatus: status}
			e, _, _ := engineTestOpen(t, b)
			r := engineTestWager(t, "1")
			if _, err := e.Submit(t.Context(), r); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
				t.Fatal(err)
			}
			j := readTestCustodyJournal(t, e)
			if j.OperationStatusCounts[status] != 1 || j.UnresolvedCount != 1 || j.HeldOutboundUWolo != r.AmountUWolo || j.ConfirmedOutboundUWolo != "0" {
				t.Fatalf("uncertain money became free: %+v", j)
			}
		})
	}
}

func TestCustodyJournalUnsignedUnknownRetainsFullPrincipal(t *testing.T) {
	b := &engineTestBackend{signErr: errors.New("isolated signing uncertainty")}
	e, _, _ := engineTestOpen(t, b)
	r := engineTestWager(t, "1")
	if _, err := e.Submit(t.Context(), r); err != nil {
		t.Fatal(err)
	}
	j := readTestCustodyJournal(t, e)
	if j.UnresolvedCount != 1 || j.HeldOutboundUWolo != r.AmountUWolo || j.OperationStatusCounts["UNKNOWN"] != 1 || b.signs.Load() != 1 || b.broadcasts.Load() != 0 || b.confirmations.Load() != 0 {
		t.Fatalf("unsigned uncertainty released a financial obligation: %+v", j)
	}
}

func TestCustodyJournalFailedAndRefusedAreHistoryNotBankHeadroom(t *testing.T) {
	for _, status := range []string{"FAILED", "REFUSED"} {
		t.Run(status, func(t *testing.T) {
			b := &engineTestBackend{confirmationStatus: status}
			if status == "REFUSED" {
				b.signErr = ErrPreSignRefused
			}
			e, _, _ := engineTestOpen(t, b)
			r := engineTestWager(t, "1")
			if _, err := e.Submit(t.Context(), r); err != nil {
				t.Fatal(err)
			}
			if status == "FAILED" {
				if _, err := e.Reconcile(t.Context(), r.OperationID); err != nil {
					t.Fatal(err)
				}
			}
			j := readTestCustodyJournal(t, e)
			if j.OperationStatusCounts[status] != 1 || j.OperationsCount != 1 || j.ConfirmedOutboundUWolo != "0" {
				t.Fatalf("terminal failure rewritten as successful payment: %+v", j)
			}
			wire, _ := json.Marshal(j)
			for _, invented := range []string{"available_uwolo", "bank_balance_uwolo", "free_uwolo", "released_uwolo"} {
				if strings.Contains(string(wire), invented) {
					t.Fatal("journal status inferred bank availability")
				}
			}
		})
	}
}

func TestCustodyJournalCountsExactOwnedReturnReceipts(t *testing.T) {
	e, _, _, _, plan := multiLegFixture(t)
	for i, claim := range []string{"101", "102"} {
		a := multiLegApproval(t, plan, claim, e.policy)
		if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
			t.Fatal(err)
		}
		if err := e.recordReturn(testStoredReturn(t, e, claim), testFaultInjectedReturnReceipt(a, strings.Repeat(strconv.Itoa(i+1), 64), 0)); err != nil {
			t.Fatal(err)
		}
	}
	j := readTestCustodyJournal(t, e)
	if j.ConfirmedReturnReceiptCount != 2 || j.ConfirmedReturnUWolo != "3000000" || j.ConfirmedOutboundUWolo != "2000000" {
		t.Fatalf("payout/refund receipts conflated with funding: %+v", j)
	}
}

func TestCustodyJournalDigestBindsAllBucketBoundariesAndFramedBytes(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	initial := readTestCustodyJournal(t, e)
	if err := e.db.Update(func(tx *bolt.Tx) error { _, err := tx.CreateBucket([]byte("extra")); return err }); err != nil {
		t.Fatal(err)
	}
	emptyBucket := readTestCustodyJournal(t, e)
	if initial.JournalDigest == emptyBucket.JournalDigest {
		t.Fatal("an empty bucket was omitted from the checkpoint")
	}
	if err := e.db.Update(func(tx *bolt.Tx) error { return tx.Bucket([]byte("extra")).Put([]byte("a"), []byte("bc")) }); err != nil {
		t.Fatal(err)
	}
	first := readTestCustodyJournal(t, e)
	if err := e.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte("extra"))
		if err := b.Delete([]byte("a")); err != nil {
			return err
		}
		return b.Put([]byte("ab"), []byte("c"))
	}); err != nil {
		t.Fatal(err)
	}
	if first.JournalDigest == readTestCustodyJournal(t, e).JournalDigest {
		t.Fatal("unframed concatenation collision changed no digest")
	}
}

func TestCustodyJournalRejectsCorruptStateWithoutPartialAuthority(t *testing.T) {
	for _, mode := range []string{"fingerprint", "amount", "signed-bytes", "missing-effect", "policy", "return-receipt", "allocation-budget", "funds-budget"} {
		t.Run(mode, func(t *testing.T) {
			e, _, _, _, request := testOwnedReturnEngine(t)
			a := testOwnedReturnApproval(t, request.OperationID, "101")
			if mode == "return-receipt" || mode == "allocation-budget" || mode == "funds-budget" {
				if _, err := e.PrepareReturnRun(t.Context(), a); err != nil {
					t.Fatal(err)
				}
			}
			if err := e.db.Update(func(tx *bolt.Tx) error {
				if mode == "policy" {
					return tx.Bucket(meta).Put([]byte("policy"), []byte("false"))
				}
				r, err := load(tx, request.OperationID)
				if err != nil {
					return err
				}
				switch mode {
				case "fingerprint":
					r.Fingerprint = strings.Repeat("0", 64)
				case "amount":
					r.Request.AmountUWolo = "18446744073709551616"
					r.Fingerprint = fingerprint(r.Request)
				case "signed-bytes":
					r.Signed.Bytes[0] ^= 1
				case "missing-effect":
					return tx.Bucket(effects).Delete([]byte("wolo-1:" + r.Signed.Hash))
				case "allocation-budget":
					var state allocationState
					bucket := tx.Bucket(allocationBucket)
					if err := json.Unmarshal(bucket.Get([]byte(request.OperationID)), &state); err != nil {
						return err
					}
					state.Reserved--
					data, _ := json.Marshal(state)
					return bucket.Put([]byte(request.OperationID), data)
				case "funds-budget":
					var state returnFundsState
					if err := json.Unmarshal(tx.Bucket(meta).Get(fundsKey), &state); err != nil {
						return err
					}
					state.Reserved--
					data, _ := json.Marshal(state)
					return tx.Bucket(meta).Put(fundsKey, data)
				case "return-receipt":
					var rr returnRecord
					if err := json.Unmarshal(tx.Bucket(returns).Get([]byte(a.ClaimID)), &rr); err != nil {
						return err
					}
					p := testFaultInjectedReturnReceipt(a, testHTTPHash, 0)
					p.OwnerID = "other-owner"
					rr.Receipt = &p
					data, _ := json.Marshal(rr)
					return tx.Bucket(returns).Put([]byte(a.ClaimID), data)
				}
				return save(tx, r)
			}); err != nil {
				t.Fatal(err)
			}
			j, err := e.CustodyJournal()
			if err == nil || !reflect.DeepEqual(j, CustodyJournal{}) {
				t.Fatalf("corruption returned a financial-looking partial result: %+v %v", j, err)
			}
		})
	}
}

func TestCustodyJournalRejectsResourceAndArithmeticExhaustion(t *testing.T) {
	for _, mode := range []string{"bytes", "records", "depth"} {
		t.Run(mode, func(t *testing.T) {
			e, _, _ := engineTestOpen(t, &engineTestBackend{})
			if err := e.db.Update(func(tx *bolt.Tx) error {
				b, err := tx.CreateBucket([]byte("extra"))
				if err != nil {
					return err
				}
				switch mode {
				case "bytes":
					return b.Put([]byte("huge"), make([]byte, custodyJournalMaxBytes))
				case "records":
					for i := 0; i <= custodyJournalMaxRecords; i++ {
						if err := b.Put([]byte(strconv.Itoa(i)), []byte("x")); err != nil {
							return err
						}
					}
				case "depth":
					for i := 0; i <= custodyJournalMaxDepth; i++ {
						b, err = b.CreateBucket([]byte("nested"))
						if err != nil {
							return err
						}
					}
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			j, err := e.CustodyJournal()
			if err == nil || err.Error() != "custody_journal_resource_limit" || !reflect.DeepEqual(j, CustodyJournal{}) {
				t.Fatalf("unbounded or partial checkpoint: %+v %v", j, err)
			}
		})
	}
	total := uint64(math.MaxUint64)
	if err := addCustodyJournalAmount(&total, 1); err == nil || total != math.MaxUint64 {
		t.Fatal("overflow invented an aggregate amount")
	}
	if err := addCustodyJournalAmount(new(uint64), 1); err != nil {
		t.Fatal(err)
	}
}
