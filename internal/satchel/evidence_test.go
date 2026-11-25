package satchel

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
	"time"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	base "cosmossdk.io/api/cosmos/base/v1beta1"
	tx "cosmossdk.io/api/cosmos/tx/v1beta1"
	"github.com/cosmos/btcutil/bech32"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/anypb"
)

func fixtureAddress(t *testing.T, seed byte) string {
	t.Helper()
	s, err := bech32.EncodeFromBase256("wolo", bytes.Repeat([]byte{seed}, 20))
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func marshalFixture(t *testing.T, m proto.Message) []byte {
	t.Helper()
	b, err := proto.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func rewriteBody(t *testing.T, o *Observation, change func(*tx.TxBody)) {
	t.Helper()
	var raw tx.TxRaw
	var body tx.TxBody
	if err := proto.Unmarshal(o.TxBytes, &raw); err != nil {
		t.Fatal(err)
	}
	if err := proto.Unmarshal(raw.BodyBytes, &body); err != nil {
		t.Fatal(err)
	}
	change(&body)
	raw.BodyBytes = marshalFixture(t, &body)
	o.TxBytes = marshalFixture(t, &raw)
	hash := sha256.Sum256(o.TxBytes)
	o.TxHash = hex.EncodeToString(hash[:])
}

func rewriteSend(t *testing.T, o *Observation, change func(*bank.MsgSend)) {
	rewriteBody(t, o, func(body *tx.TxBody) {
		var send bank.MsgSend
		if err := proto.Unmarshal(body.Messages[0].Value, &send); err != nil {
			t.Fatal(err)
		}
		change(&send)
		body.Messages[0].Value = marshalFixture(t, &send)
	})
}

// No keys, RPC, ledger, broadcasts or funds: bytes/signature/head are synthetic.
func depositFixture(t *testing.T) (Intent, Observation, time.Time) {
	t.Helper()
	now := time.Date(2026, 10, 15, 20, 0, 0, 0, time.UTC)
	i := Intent{"owner-a", fixtureAddress(t, 1), fixtureAddress(t, 2), "1000000", "server-intent:unique-nonce", now.Add(-time.Minute), now.Add(time.Minute)}
	send := &bank.MsgSend{FromAddress: i.Sender, ToAddress: i.Vault, Amount: []*base.Coin{{Denom: Denom, Amount: i.AmountUWolo}}}
	body := &tx.TxBody{Memo: i.Memo, Messages: []*anypb.Any{{TypeUrl: "/cosmos.bank.v1beta1.MsgSend", Value: marshalFixture(t, send)}}}
	raw := &tx.TxRaw{BodyBytes: marshalFixture(t, body), AuthInfoBytes: []byte("synthetic-auth"), Signatures: [][]byte{[]byte("synthetic-signature")}}
	b := marshalFixture(t, raw)
	hash := sha256.Sum256(b)
	zero, synced, ordinal := uint32(0), false, uint32(0)
	head := Head{ChainID: ChainID, Height: 102, BlockHash: strings.Repeat("B", 64), BlockTime: now.Add(-time.Second), ObservedAt: now, CatchingUp: &synced}
	o := Observation{ChainID: ChainID, TxHash: hex.EncodeToString(hash[:]), TxBytes: b, Code: &zero, Height: 100,
		BlockHash: strings.Repeat("A", 64), BlockTime: now.Add(-10 * time.Second), Head: head, IndependentHead: head,
		Transfers: []Transfer{{i.Sender, i.Vault, Denom, i.AmountUWolo}}, TransferIndex: &ordinal}
	return i, o, now
}

func TestExactDepositCandidateDoesNotAuthorizeCredit(t *testing.T) {
	i, o, now := depositFixture(t)
	r, err := InspectDeposit(i, o, now)
	if err != nil {
		t.Fatal(err)
	}
	want := ChainID + ":" + strings.ToUpper(o.TxHash) + ":0"
	if r.ID() != want {
		t.Fatalf("unexpected receipt identity %s", r.ID())
	}
	o.TxHash = strings.ToUpper(o.TxHash)
	r2, err := InspectDeposit(i, o, now)
	if err != nil || r2 != r {
		t.Fatalf("hash case split receipt identity: %v", err)
	}
	if CurrentCapability().Available() || CurrentCapability().CreditAuthorized() {
		t.Fatal("candidate enabled funds")
	}
	// Caller-created receipt values cannot create an alternate lowercase ID.
	r.TxHash = strings.ToLower(r.TxHash)
	if r.ID() != want {
		t.Fatal("noncanonical identity")
	}
}

func TestDepositAdversarialEvidence(t *testing.T) {
	tests := map[string]func(*Intent, *Observation, *time.Time){
		"invalid owner encoding": func(i *Intent, o *Observation, n *time.Time) { i.OwnerID = "\xff" },
		"invalid memo encoding":  func(i *Intent, o *Observation, n *time.Time) { i.Memo = "\xfe" },
		"no owner":               func(i *Intent, o *Observation, n *time.Time) { i.OwnerID = "" },
		"wrong sender":           func(i *Intent, o *Observation, n *time.Time) { i.Sender = fixtureAddress(t, 3) },
		"sender is vault":        func(i *Intent, o *Observation, n *time.Time) { i.Vault = i.Sender },
		"invalid checksum":       func(i *Intent, o *Observation, n *time.Time) { i.Vault = i.Vault[:len(i.Vault)-1] + "!" },
		"uppercase address":      func(i *Intent, o *Observation, n *time.Time) { i.Vault = strings.ToUpper(i.Vault) },
		"treasury vault":         func(i *Intent, o *Observation, n *time.Time) { i.Vault = "wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2" },
		"bet escrow vault":       func(i *Intent, o *Observation, n *time.Time) { i.Vault = "wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p" },
		"wrong amount":           func(i *Intent, o *Observation, n *time.Time) { i.AmountUWolo = "999" },
		"expired intent":         func(i *Intent, o *Observation, n *time.Time) { *n = i.ExpiresAt },
		"long intent":            func(i *Intent, o *Observation, n *time.Time) { i.ExpiresAt = i.CreatedAt.Add(time.Hour) },
		"future intent":          func(i *Intent, o *Observation, n *time.Time) { i.CreatedAt = n.Add(time.Second) },
		"missing memo":           func(i *Intent, o *Observation, n *time.Time) { i.Memo = "" },
		"wrong memo": func(i *Intent, o *Observation, n *time.Time) {
			rewriteBody(t, o, func(b *tx.TxBody) { b.Memo = "other" })
		},
		"wrong chain":    func(i *Intent, o *Observation, n *time.Time) { o.ChainID = "wolo-testnet-1" },
		"missing result": func(i *Intent, o *Observation, n *time.Time) { o.Code = nil },
		"failed tx":      func(i *Intent, o *Observation, n *time.Time) { code := uint32(5); o.Code = &code },
		"hash mismatch":  func(i *Intent, o *Observation, n *time.Time) { o.TxHash = strings.Repeat("F", 64) },
		"malformed raw": func(i *Intent, o *Observation, n *time.Time) {
			o.TxBytes = []byte("bad")
			h := sha256.Sum256(o.TxBytes)
			o.TxHash = hex.EncodeToString(h[:])
		},
		"zero height":             func(i *Intent, o *Observation, n *time.Time) { o.Height = 0 },
		"future height":           func(i *Intent, o *Observation, n *time.Time) { o.Height = 103 },
		"unfinalized height":      func(i *Intent, o *Observation, n *time.Time) { o.Height = 102 },
		"no block identity":       func(i *Intent, o *Observation, n *time.Time) { o.BlockHash = "" },
		"stale head":              func(i *Intent, o *Observation, n *time.Time) { o.Head.BlockTime = n.Add(-time.Minute) },
		"future head":             func(i *Intent, o *Observation, n *time.Time) { o.Head.BlockTime = n.Add(time.Minute) },
		"stale observation":       func(i *Intent, o *Observation, n *time.Time) { o.Head.ObservedAt = n.Add(-time.Minute) },
		"future observation":      func(i *Intent, o *Observation, n *time.Time) { o.Head.ObservedAt = n.Add(time.Second) },
		"wrong head chain":        func(i *Intent, o *Observation, n *time.Time) { o.Head.ChainID = "wrong" },
		"catching up":             func(i *Intent, o *Observation, n *time.Time) { yes := true; o.Head.CatchingUp = &yes },
		"unknown sync":            func(i *Intent, o *Observation, n *time.Time) { o.Head.CatchingUp = nil },
		"independent head absent": func(i *Intent, o *Observation, n *time.Time) { o.IndependentHead = Head{} },
		"conflicting heads":       func(i *Intent, o *Observation, n *time.Time) { o.IndependentHead.BlockHash = strings.Repeat("C", 64) },
		"conflicting heights":     func(i *Intent, o *Observation, n *time.Time) { o.IndependentHead.Height++ },
		"pre-intent inclusion":    func(i *Intent, o *Observation, n *time.Time) { o.BlockTime = i.CreatedAt.Add(-time.Second) },
		"post-head inclusion":     func(i *Intent, o *Observation, n *time.Time) { o.BlockTime = *n },
		"wrong denom": func(i *Intent, o *Observation, n *time.Time) {
			rewriteSend(t, o, func(s *bank.MsgSend) { s.Amount[0].Denom = "uother" })
		},
		"multiple coins": func(i *Intent, o *Observation, n *time.Time) {
			rewriteSend(t, o, func(s *bank.MsgSend) { s.Amount = append(s.Amount, &base.Coin{Denom: "uother", Amount: "1"}) })
		},
		"wrong recipient": func(i *Intent, o *Observation, n *time.Time) {
			rewriteSend(t, o, func(s *bank.MsgSend) { s.ToAddress = fixtureAddress(t, 4) })
		},
		"multisend": func(i *Intent, o *Observation, n *time.Time) {
			rewriteBody(t, o, func(b *tx.TxBody) { b.Messages[0].TypeUrl = "/cosmos.bank.v1beta1.MsgMultiSend" })
		},
		"multiple messages": func(i *Intent, o *Observation, n *time.Time) {
			rewriteBody(t, o, func(b *tx.TxBody) { b.Messages = append(b.Messages, b.Messages[0]) })
		},
		"no bank effect":         func(i *Intent, o *Observation, n *time.Time) { o.Transfers = nil },
		"duplicate bank effect":  func(i *Intent, o *Observation, n *time.Time) { o.Transfers = append(o.Transfers, o.Transfers[0]) },
		"unrelated extra effect": func(i *Intent, o *Observation, n *time.Time) { o.Transfers = append(o.Transfers, Transfer{}) },
		"effect differs":         func(i *Intent, o *Observation, n *time.Time) { o.Transfers[0].Amount = "999" },
		"missing ordinal":        func(i *Intent, o *Observation, n *time.Time) { o.TransferIndex = nil },
		"changed ordinal":        func(i *Intent, o *Observation, n *time.Time) { index := uint32(1); o.TransferIndex = &index },
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			i, o, n := depositFixture(t)
			mutate(&i, &o, &n)
			r, err := InspectDeposit(i, o, n)
			if err == nil || r != (ReceiptCandidate{}) {
				t.Fatalf("unsafe candidate accepted: %+v %v", r, err)
			}
		})
	}
	for _, invalid := range []string{"0", "-1", "+1", "01", "1.0", " 1", "1uwolo", "100000000000001", "18446744073709551616"} {
		t.Run("amount_"+invalid, func(t *testing.T) {
			i, o, n := depositFixture(t)
			i.AmountUWolo = invalid
			if _, err := InspectDeposit(i, o, n); err == nil {
				t.Fatal("invalid amount accepted")
			}
		})
	}
}

func reserveFixture(t *testing.T) (ReserveEvidence, time.Time) {
	i, o, n := depositFixture(t)
	r, err := InspectDeposit(i, o, n)
	if err != nil {
		t.Fatal(err)
	}
	return ReserveEvidence{Vault: i.Vault, Head: o.Head, BankSnapshotDigest: strings.Repeat("A", 64), CompleteLiabilityManifestDigest: strings.Repeat("B", 64), IndependentReconciliationDigest: strings.Repeat("C", 64), Sources: []ReserveSource{{r, strings.Repeat("D", 64)}}}, n
}

func TestReserveProvenanceRequiredAndNonCertifying(t *testing.T) {
	e, n := reserveFixture(t)
	if err := InspectReserveProvenance(e, n); err != nil {
		t.Fatal(err)
	}
	if CurrentCapability().Available() {
		t.Fatal("artifact digests certified reserves")
	}
	for name, mutate := range map[string]func(*ReserveEvidence){
		"no vault":                      func(e *ReserveEvidence) { e.Vault = "" },
		"staking custody":               func(e *ReserveEvidence) { e.Vault = "wolo18v9ugfdrnz2ll2ah5z2yqzm5kzlg3e7l7jy6rn" },
		"no bank snapshot":              func(e *ReserveEvidence) { e.BankSnapshotDigest = "" },
		"no complete liabilities":       func(e *ReserveEvidence) { e.CompleteLiabilityManifestDigest = "" },
		"no independent reconciliation": func(e *ReserveEvidence) { e.IndependentReconciliationDigest = "" },
		"no sources":                    func(e *ReserveEvidence) { e.Sources = nil },
		"unreviewed funding":            func(e *ReserveEvidence) { e.Sources[0].UnencumberedSourceReviewDigest = "" },
		"foreign chain source":          func(e *ReserveEvidence) { e.Sources[0].Receipt.ChainID = "other" },
		"missing tx identity":           func(e *ReserveEvidence) { e.Sources[0].Receipt.TxHash = "" },
		"alternate collateral ordinal":  func(e *ReserveEvidence) { e.Sources[0].Receipt.TransferIndex = 1 },
		"duplicate normalized collateral": func(e *ReserveEvidence) {
			s := e.Sources[0]
			s.Receipt.TxHash = strings.ToLower(s.Receipt.TxHash)
			e.Sources = append(e.Sources, s)
		},
		"stale snapshot": func(e *ReserveEvidence) { e.Head.BlockTime = n.Add(-time.Hour) },
	} {
		t.Run(name, func(t *testing.T) {
			e, n := reserveFixture(t)
			mutate(&e)
			if InspectReserveProvenance(e, n) == nil {
				t.Fatal("incomplete provenance accepted")
			}
		})
	}
}
