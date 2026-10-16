package satchel

// These are necessary, offline evidence checks, not a trust adapter or a credit
// authority. No caller-supplied observation can make CurrentCapability available.
import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	"github.com/cosmos/btcutil/bech32"
	"google.golang.org/protobuf/proto"
)

const (
	ChainID                = "wolo-1"
	Denom                  = "uwolo"
	maxHeadAge             = 30 * time.Second
	maxClockSkew           = 5 * time.Second
	minConfirmations int64 = 2 // head - inclusion + 1; not a substitute for commit verification
)

type Head struct {
	ChainID               string
	Height                int64
	BlockHash             string
	BlockTime, ObservedAt time.Time
	CatchingUp            *bool
}

type Intent struct {
	OwnerID, Sender, Vault, AmountUWolo, Memo string
	CreatedAt, ExpiresAt                      time.Time
}

type Transfer struct{ Sender, Recipient, Denom, Amount string }

// Observation must eventually be produced by a server-owned authenticated
// adapter verifying inclusion and the signed commit against pinned chain trust.
// IndependentHead must come from a separately operated trust path. Matching
// fields alone do not establish either fact; that adapter is NOT implemented.
type Observation struct {
	ChainID, TxHash, BlockHash string
	TxBytes                    []byte
	Code                       *uint32 // absent execution result must not default to success
	Height                     int64
	BlockTime                  time.Time
	Head, IndependentHead      Head
	// COMPLETE list: existing settlement log-first/split-coin convention;
	// top-level events only when logs contain no transfers. Include every
	// transfer (including fee transfers). Never filter or renumber the list.
	Transfers     []Transfer
	TransferIndex *uint32
}

// ReceiptCandidate has no credit/readiness bit. V1 accepts only one MsgSend,
// one coin and one bank effect, so its canonical bank-transfer ordinal is zero.
// Durable GLOBAL (chain, uppercase hash, ordinal) uniqueness is still required
// across manual betting, challenge and Satchel consumers; this function stores nothing.
type ReceiptCandidate struct {
	ChainID, TxHash string
	TransferIndex   uint32
}

func (r ReceiptCandidate) ID() string {
	return fmt.Sprintf("%s:%s:%d", r.ChainID, strings.ToUpper(r.TxHash), r.TransferIndex)
}

func digest(s string) bool {
	if len(s) != 64 {
		return false
	}
	_, err := hex.DecodeString(s)
	return err == nil && strings.Trim(s, "0") != ""
}

func address(s string) bool {
	if s != strings.ToLower(s) {
		return false
	}
	hrp, words, err := bech32.Decode(s, 90)
	if err != nil || hrp != "wolo" {
		return false
	}
	data, err := bech32.ConvertBits(words, 5, 8, false)
	return err == nil && len(data) == 20
}

func amount(s string) bool {
	if s == "" || s[0] < '1' || s[0] > '9' {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	// The chain fixed supply is 100,000,000 WOLO. Bound parsing and reject
	// amounts that no canonical transfer on this chain could deliver.
	n, err := strconv.ParseUint(s, 10, 64)
	return err == nil && n <= 100000000000000
}

func validHead(h Head, now time.Time) bool {
	return !now.IsZero() && h.ChainID == ChainID && h.Height > 0 && digest(h.BlockHash) && h.CatchingUp != nil && !*h.CatchingUp &&
		!h.BlockTime.IsZero() && !h.ObservedAt.IsZero() &&
		!h.BlockTime.After(now.Add(maxClockSkew)) && !h.ObservedAt.After(now) &&
		!h.BlockTime.Before(now.Add(-maxHeadAge)) && !h.ObservedAt.Before(now.Add(-maxHeadAge)) &&
		!h.BlockTime.After(h.ObservedAt.Add(maxClockSkew))
}

// InspectDeposit checks caller-supplied candidate shape. It proves no inclusion,
// signature, finality, ownership or independent custody and grants no credit.
// A trusted adapter and durable global receipt claim remain unimplemented.
func InspectDeposit(i Intent, o Observation, now time.Time) (ReceiptCandidate, error) {
	return inspectDeposit(i, o, now, true)
}

func validIntent(i Intent, now time.Time) bool {
	return !now.IsZero() && strings.TrimSpace(i.OwnerID) != "" && len(i.OwnerID) <= 128 && utf8.ValidString(i.OwnerID) && utf8.ValidString(i.Memo) && address(i.Sender) && address(i.Vault) &&
		i.Sender != i.Vault && !IsKnownRoleAddress(i.Vault) && amount(i.AmountUWolo) &&
		len(i.Memo) > 0 && len(i.Memo) <= 256 && !i.CreatedAt.IsZero() && !i.CreatedAt.After(now) &&
		i.ExpiresAt.After(i.CreatedAt) && i.ExpiresAt.Sub(i.CreatedAt) <= 30*time.Minute && now.Before(i.ExpiresAt)
}

// The network reader can inspect a primary-only NONCREDITING observation
// without inventing an independent head. The public C2 contract still requires
// both heads; neither path authenticates consensus or grants custody authority.
func inspectDeposit(i Intent, o Observation, now time.Time, requireWitness bool) (ReceiptCandidate, error) {
	refuse := func(reason string) (ReceiptCandidate, error) { return ReceiptCandidate{}, errors.New(reason) }
	if !validIntent(i, now) {
		return refuse("invalid_or_expired_owner_intent")
	}
	if o.ChainID != ChainID || o.Code == nil || *o.Code != 0 || !digest(o.TxHash) ||
		len(o.TxBytes) == 0 || len(o.TxBytes) > 65536 {
		return refuse("invalid_chain_or_transaction_result")
	}
	hash := sha256.Sum256(o.TxBytes)
	if !strings.EqualFold(hex.EncodeToString(hash[:]), o.TxHash) {
		return refuse("transaction_hash_mismatch")
	}
	if !validHead(o.Head, now) || (requireWitness && (!validHead(o.IndependentHead, now) ||
		o.Head.Height != o.IndependentHead.Height || !strings.EqualFold(o.Head.BlockHash, o.IndependentHead.BlockHash) ||
		!o.Head.BlockTime.Equal(o.IndependentHead.BlockTime))) || o.Height <= 0 ||
		o.Height > o.Head.Height || o.Head.Height-o.Height+1 < minConfirmations || !digest(o.BlockHash) ||
		o.BlockTime.Before(i.CreatedAt) || !o.BlockTime.Before(i.ExpiresAt) || o.BlockTime.After(o.Head.BlockTime) {
		return refuse("unbound_or_unfinalized_chain_observation")
	}
	if !exactSend(o.TxBytes, i.Sender, i.Vault, i.AmountUWolo, i.Memo) {
		return refuse("exact_bank_send_required")
	}
	if len(o.Transfers) != 1 || o.TransferIndex == nil || *o.TransferIndex != 0 ||
		o.Transfers[0] != (Transfer{i.Sender, i.Vault, Denom, i.AmountUWolo}) {
		return refuse("unique_exact_bank_effect_required")
	}
	return ReceiptCandidate{ChainID, strings.ToUpper(o.TxHash), 0}, nil
}

// Structural message parity only; signature validity, account sequence, chain
// sign-doc binding and authenticated execution still require the future adapter.
func exactSend(data []byte, sender, recipient, amountUWolo, memo string) bool {
	var raw tx.TxRaw
	var body tx.TxBody
	if proto.Unmarshal(data, &raw) != nil || len(raw.ProtoReflect().GetUnknown()) != 0 ||
		len(raw.Signatures) != 1 || len(raw.Signatures[0]) == 0 || len(raw.AuthInfoBytes) == 0 ||
		proto.Unmarshal(raw.BodyBytes, &body) != nil || len(body.ProtoReflect().GetUnknown()) != 0 ||
		len(body.Messages) != 1 || len(body.ExtensionOptions) != 0 || len(body.NonCriticalExtensionOptions) != 0 || body.Memo != memo {
		return false
	}
	return exactSendBody(&body, sender, recipient, amountUWolo, memo)
}

func exactSendBody(body *tx.TxBody, sender, recipient, amountUWolo, memo string) bool {
	if body == nil || len(body.ProtoReflect().GetUnknown()) != 0 || len(body.Messages) != 1 || len(body.ExtensionOptions) != 0 || len(body.NonCriticalExtensionOptions) != 0 || body.Memo != memo {
		return false
	}
	message := body.Messages[0]
	var send bank.MsgSend
	return message != nil && message.TypeUrl == "/cosmos.bank.v1beta1.MsgSend" && len(message.ProtoReflect().GetUnknown()) == 0 &&
		proto.Unmarshal(message.Value, &send) == nil && len(send.ProtoReflect().GetUnknown()) == 0 &&
		send.FromAddress == sender && send.ToAddress == recipient && len(send.Amount) == 1 && send.Amount[0] != nil &&
		send.Amount[0].Denom == Denom && send.Amount[0].Amount == amountUWolo && len(send.Amount[0].ProtoReflect().GetUnknown()) == 0
}

// ReserveEvidence binds the artifacts that an independent auditor must inspect.
// Digests identify evidence, they do NOT attest truth or completeness. No reserve
// arithmetic or solvency certification is returned by this shape check.
type ReserveEvidence struct {
	Vault                                                                                string
	Head                                                                                 Head
	BankSnapshotDigest, CompleteLiabilityManifestDigest, IndependentReconciliationDigest string
	Sources                                                                              []ReserveSource
}

type ReserveSource struct {
	Receipt ReceiptCandidate
	// Approval must prove the source funds are unencumbered, including existing
	// betting/refund/claim/staking liabilities; a wallet label is not that proof.
	UnencumberedSourceReviewDigest string
}

// InspectReserveProvenance checks artifact references supplied by the caller.
// It certifies neither content/completeness nor solvency or key control.
// Success cannot change CurrentCapability or authorize use of any collateral.
func InspectReserveProvenance(e ReserveEvidence, now time.Time) error {
	if !address(e.Vault) || IsKnownRoleAddress(e.Vault) || !validHead(e.Head, now) ||
		!digest(e.BankSnapshotDigest) || !digest(e.CompleteLiabilityManifestDigest) || !digest(e.IndependentReconciliationDigest) || len(e.Sources) == 0 {
		return errors.New("reserve_provenance_incomplete")
	}
	seen := map[string]bool{}
	for _, s := range e.Sources {
		if s.Receipt.ChainID != ChainID || s.Receipt.TransferIndex != 0 || !digest(s.Receipt.TxHash) || !digest(s.UnencumberedSourceReviewDigest) {
			return errors.New("unreviewed_reserve_source")
		}
		key := fmt.Sprintf("%s:%s:%d", ChainID, strings.ToUpper(s.Receipt.TxHash), s.Receipt.TransferIndex)
		if seen[key] {
			return errors.New("duplicate_reserve_source")
		}
		seen[key] = true
	}
	return nil
}
