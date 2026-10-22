package satchelservice

// This checkpoint describes this executable's durable execution history. It is
// not the HD customer ledger, a bank balance attestation or reserve clearance.
// In particular, failed/refused operations do not prove available custody funds;
// fees and all external liabilities still require independent reconciliation.
import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"hash"
	"math"
	"strconv"
	"strings"

	bolt "go.etcd.io/bbolt"
)

const custodyJournalMaxBytes = 8 << 20
const custodyJournalMaxRecords = 100000
const custodyJournalMaxDepth = 64

type CustodyJournal struct {
	Protocol                    int               `json:"protocol"`
	ChainID                     string            `json:"chain_id"`
	Denom                       string            `json:"denom"`
	Kind                        string            `json:"kind"`
	JournalDigest               string            `json:"journal_digest"`
	PolicyDigest                string            `json:"policy_digest"`
	RecordsRead                 uint64            `json:"records_read"`
	BytesRead                   uint64            `json:"bytes_read"`
	OperationsCount             uint64            `json:"operations_count"`
	OperationStatusCounts       map[string]uint64 `json:"operation_status_counts"`
	UnresolvedCount             uint64            `json:"unresolved_count"`
	HeldOutboundUWolo           string            `json:"held_outbound_uwolo"`
	ConfirmedOutboundUWolo      string            `json:"confirmed_outbound_uwolo"`
	ConfirmedReturnReceiptCount uint64            `json:"confirmed_return_receipt_count"`
	ConfirmedReturnUWolo        string            `json:"confirmed_return_uwolo"`
	BankBalanceAuthenticated    bool              `json:"bank_balance_authenticated"`
	CreditAuthorized            bool              `json:"credit_authorized"`
	SolvencyAuthorized          bool              `json:"solvency_authorized"`
	CustodyCapability           string            `json:"custody_capability"`
}

type custodyJournalScan struct {
	hash           hash.Hash
	bytes, records uint64
}

func (s *custodyJournalScan) read(size int) error {
	if size < 0 || uint64(size) > custodyJournalMaxBytes-s.bytes {
		return errors.New("custody_journal_resource_limit")
	}
	s.bytes += uint64(size)
	return nil
}

func (s *custodyJournalScan) frame(kind byte, key, value []byte) error {
	if len(key) > custodyJournalMaxBytes || len(value) > custodyJournalMaxBytes {
		return errors.New("custody_journal_resource_limit")
	}
	size := uint64(17 + len(key) + len(value))
	if size > custodyJournalMaxBytes-s.bytes || s.records >= custodyJournalMaxRecords {
		return errors.New("custody_journal_resource_limit")
	}
	s.bytes += size
	s.records++
	var header [17]byte
	header[0] = kind
	binary.BigEndian.PutUint64(header[1:9], uint64(len(key)))
	binary.BigEndian.PutUint64(header[9:17], uint64(len(value)))
	s.hash.Write(header[:])
	s.hash.Write(key)
	s.hash.Write(value)
	return nil
}

func (s *custodyJournalScan) bucket(name []byte, b *bolt.Bucket, depth int) error {
	if b == nil || depth > custodyJournalMaxDepth {
		return errors.New("custody_journal_resource_limit")
	}
	if err := s.frame('B', name, nil); err != nil {
		return err
	}
	if err := b.ForEach(func(k, v []byte) error {
		if v == nil {
			return s.bucket(k, b.Bucket(k), depth+1)
		}
		return s.frame('V', k, v)
	}); err != nil {
		return err
	}
	return s.frame('E', nil, nil)
}

func addCustodyJournalAmount(total *uint64, amount uint64) error {
	if amount > math.MaxUint64-*total {
		return errors.New("custody_journal_amount_overflow")
	}
	*total += amount
	return nil
}

// CustodyJournal takes one bounded, consistent Bolt snapshot. It performs only
// local signature/payload validation: no chain reads, signing, broadcasting,
// confirmation requests, writes, pruning or release of any financial hold.
func (e *Engine) CustodyJournal() (CustodyJournal, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.custodyJournalLocked()
}

// Caller owns the execution mutex. Qualification must precede the first new
// intent write without reacquiring that mutex or weakening the snapshot checks.
func (e *Engine) custodyJournalLocked() (CustodyJournal, error) {
	out := CustodyJournal{Protocol: 1, ChainID: "wolo-1", Denom: "uwolo", Kind: "execution_journal_checkpoint",
		CustodyCapability: "UNAVAILABLE", OperationStatusCounts: map[string]uint64{
			"UNKNOWN": 0, "ACCEPTED": 0, "OBSERVED_NONCREDITING": 0, "CONFIRMED": 0, "FAILED": 0, "REFUSED": 0}}
	err := e.db.View(func(tx *bolt.Tx) error {
		if tx.Bucket(meta) == nil || tx.Bucket(operations) == nil || tx.Bucket(effects) == nil || string(tx.Bucket(meta).Get([]byte("policy"))) != hashJSON(e.policy) {
			return errors.New("custody_journal_unverifiable")
		}
		scan := custodyJournalScan{hash: sha256.New()}
		scan.hash.Write([]byte("aoe2war/satchel/execution-journal/v1\x00"))
		// Bolt iteration is lexicographic. Bucket and end markers, plus explicit
		// lengths, bind every bucket boundary, key and exact stored value bytes.
		if err := tx.ForEach(func(name []byte, b *bolt.Bucket) error { return scan.bucket(name, b, 0) }); err != nil {
			return err
		}
		out.JournalDigest = hex.EncodeToString(scan.hash.Sum(nil))
		out.PolicyDigest = hashJSON(e.policy)
		out.RecordsRead = scan.records
		var held, confirmed, returned uint64
		returnClaims := make(map[string][]ReturnApproval)
		expectedEffects := make(map[string]string)
		consumeEffect := func(hash, owner string) error {
			key := "wolo-1:" + hash
			if _, exists := expectedEffects[key]; exists {
				return errors.New("custody_journal_unverifiable")
			}
			expectedEffects[key] = owner
			return nil
		}
		if err := tx.Bucket(operations).ForEach(func(id, value []byte) error {
			if err := scan.read(len(id) + 2*len(value)); err != nil {
				return err
			}
			if value == nil {
				return errors.New("custody_journal_unverifiable")
			}
			r, err := load(tx, string(id))
			if err != nil || r.Request.ChainID != "wolo-1" || r.Request.Denom != "uwolo" || r.Request.Sender != e.policy.Vault || !validAddress(r.Request.Recipient) || r.Request.Recipient == e.policy.Vault || (r.Request.Kind != "wager" && r.Request.Kind != "withdrawal") {
				return errors.New("custody_journal_unverifiable")
			}
			n, ok := positive(r.Request.AmountUWolo, e.policy.MaxAmountUWolo)
			if !ok || (len(r.Signed.Bytes) > 0 && e.backend.ValidateSigned(r.Request, r.Signed) != nil) {
				return errors.New("custody_journal_unverifiable")
			}
			out.OperationsCount++
			out.OperationStatusCounts[r.Result.Status]++
			switch r.Result.Status {
			case "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING":
				out.UnresolvedCount++
				return addCustodyJournalAmount(&held, n)
			case "CONFIRMED", "FAILED":
				if !nonzeroDigest(r.Confirmation.BlockHash) || !nonzeroDigest(r.Signed.Hash) || r.Signed.Hash != strings.ToUpper(r.Signed.Hash) {
					return errors.New("custody_journal_unverifiable")
				}
				if err := consumeEffect(r.Signed.Hash, string(id)); err != nil {
					return err
				}
				if r.Result.Status == "CONFIRMED" {
					return addCustodyJournalAmount(&confirmed, n)
				}
			}
			return nil
		}); err != nil {
			return err
		}
		if b := tx.Bucket(returns); b != nil {
			if err := b.ForEach(func(id, value []byte) error {
				var r returnRecord
				if err := scan.read(len(id) + len(value)); err != nil {
					return err
				}
				if value == nil || json.Unmarshal(value, &r) != nil || r.Approval.ClaimID != string(id) || r.Fingerprint != returnFingerprint(r.Approval) {
					return errors.New("custody_journal_unverifiable")
				}
				if err := scan.read(len(tx.Bucket(operations).Get([]byte(r.Approval.OperationID)))); err != nil {
					return err
				}
				if e.validateReturnAt(tx, r.Approval, false) != nil {
					return errors.New("custody_journal_unverifiable")
				}
				returnClaims[r.Approval.OperationID] = append(returnClaims[r.Approval.OperationID], r.Approval)
				if r.Receipt == nil {
					return nil
				}
				if !validReturnReceipt(r, *r.Receipt) {
					return errors.New("custody_journal_unverifiable")
				}
				n, ok := positive(r.Receipt.AmountUWolo, 50000000000)
				if !ok {
					return errors.New("custody_journal_unverifiable")
				}
				if err := consumeEffect(r.Receipt.TxHash, "return:"+string(id)); err != nil {
					return err
				}
				out.ConfirmedReturnReceiptCount++
				return addCustodyJournalAmount(&returned, n)
			}); err != nil {
				return err
			}
		}
		if err := e.validateCustodyReturnBudgets(tx, &scan, returnClaims); err != nil {
			return err
		}
		if err := tx.Bucket(effects).ForEach(func(key, owner []byte) error {
			if err := scan.read(len(key) + len(owner)); err != nil {
				return err
			}
			if owner == nil || expectedEffects[string(key)] != string(owner) {
				return errors.New("custody_journal_unverifiable")
			}
			delete(expectedEffects, string(key))
			return nil
		}); err != nil {
			return err
		}
		if len(expectedEffects) != 0 {
			return errors.New("custody_journal_unverifiable")
		}
		out.HeldOutboundUWolo = strconv.FormatUint(held, 10)
		out.ConfirmedOutboundUWolo = strconv.FormatUint(confirmed, 10)
		out.ConfirmedReturnUWolo = strconv.FormatUint(returned, 10)
		out.BytesRead = scan.bytes
		return nil
	})
	if err != nil {
		return CustodyJournal{}, err
	}
	return out, nil
}

func (e *Engine) validateCustodyReturnBudgets(tx *bolt.Tx, scan *custodyJournalScan, claims map[string][]ReturnApproval) error {
	var reserved uint64
	var identity string
	var available uint64
	if b := tx.Bucket(allocationBucket); b != nil {
		if err := b.ForEach(func(id, value []byte) error {
			if err := scan.read(len(id) + len(value)); err != nil {
				return err
			}
			var state allocationState
			group := claims[string(id)]
			if value == nil || len(group) == 0 || json.Unmarshal(value, &state) != nil || state.Plan.OperationID != string(id) || state.Digest != AllocationDigest(state.Plan, e.policy) {
				return errors.New("custody_journal_unverifiable")
			}
			// Reuse the existing signed-plan economics and owner/funding checks.
			current := group[0]
			current.Allocation, current.AllocationDigest = &state.Plan, state.Digest
			if err := scan.read(len(tx.Bucket(operations).Get(id))); err != nil {
				return err
			}
			if _, err := e.validateAllocation(tx, current, false); err != nil {
				return errors.New("custody_journal_unverifiable")
			}
			var total uint64
			for _, claim := range group {
				if claim.Allocation == nil || claim.Allocation.Revision > state.Plan.Revision || !allocationsExtend(*claim.Allocation, state.Plan, e.policy) || (claim.Allocation.Revision == state.Plan.Revision && claim.AllocationDigest != state.Digest) {
					return errors.New("custody_journal_unverifiable")
				}
				n, ok := positive(claim.AmountUWolo, 50000000000)
				if !ok {
					return errors.New("custody_journal_unverifiable")
				}
				if err := addCustodyJournalAmount(&total, n); err != nil {
					return err
				}
			}
			if total != state.Reserved {
				return errors.New("custody_journal_unverifiable")
			}
			if err := addCustodyJournalAmount(&reserved, total); err != nil {
				return err
			}
			planIdentity := fundsIdentity(state.Plan, e.policy)
			planAvailable, _ := positive(state.Plan.FundsAvailableUWolo, 100000000000000)
			if identity != "" && (identity != planIdentity || available != planAvailable) {
				return errors.New("custody_journal_unverifiable")
			}
			identity, available = planIdentity, planAvailable
			delete(claims, string(id))
			return nil
		}); err != nil {
			return err
		}
	}
	if len(claims) != 0 {
		return errors.New("custody_journal_unverifiable")
	}
	data := tx.Bucket(meta).Get(fundsKey)
	if err := scan.read(len(data)); err != nil {
		return err
	}
	if identity == "" && data == nil {
		return nil
	}
	var funds returnFundsState
	if data == nil || json.Unmarshal(data, &funds) != nil || identity == "" || funds.Identity != identity || funds.Available != available || funds.Reserved != reserved || funds.Reserved > funds.Available {
		return errors.New("custody_journal_unverifiable")
	}
	return nil
}
