package satchelservice

import (
	"testing"
	"time"
)

func TestReviewerCanonicalTicketMemoIsDistinctFromExecutionID(t *testing.T) {
	issuer, source, policy, _ := setupIssuer(t)
	// The durable operation belongs to execution 7. The existing ticket is
	// independently numbered 891; VerifyReviewerHDOrigin binds its exact memo
	// to the immutable ticketId, not to the executionId.
	source.original.Memo = "AoE2HDBets bet ticket v1 · ticket 891"
	reply := issuer.ReviewOne(t.Context(), "satchel:ticket:7")
	if reply.Status != "SIGNED" || reply.Approval == nil || reply.Approval.Memo != source.original.Memo {
		t.Fatalf("valid original ticket was confused with execution suffix: %+v", reply)
	}
	request := TransferRequest{OperationID: reply.OperationID, Kind: "wager", OwnerID: reply.Approval.OwnerID,
		ChainID: "wolo-1", Denom: "uwolo", Sender: policy.Vault, Recipient: policy.BettingEscrow,
		AmountUWolo: reply.Approval.AmountUWolo, Memo: reply.Approval.Memo, Reservation: reply.Approval}
	if err := policy.verifyWager(request, time.Now()); err != nil {
		t.Fatalf("signer refused canonical ticket: %v", err)
	}
	request.Memo = "AoE2HDBets bet ticket v1 · ticket 892"
	if err := policy.verifyWager(request, time.Now()); err == nil {
		t.Fatal("approval accepted a different ticket memo")
	}
	source.original.Memo = request.Memo
	if changed := issuer.ReviewOne(t.Context(), "satchel:ticket:7"); changed.Approval != nil {
		t.Fatal("changed original ticket reissued approval")
	}
}

func TestReviewerCanonicalMemoAndNilContextFailClosed(t *testing.T) {
	for _, memo := range []string{"", "AoE2HDBets bet ticket v1 · ticket 0", "AoE2HDBets bet ticket v1 · ticket 01", "ticket 7", "AoE2HDBets bet ticket v1 · ticket 7\n"} {
		issuer, source, _, _ := setupIssuer(t)
		source.original.Memo = memo
		if got := issuer.ReviewOne(t.Context(), "satchel:ticket:7"); got.Approval != nil {
			t.Fatalf("noncanonical ticket approved: %q", memo)
		}
	}
	issuer, _, _, _ := setupIssuer(t)
	if got := issuer.ReviewOne(nil, "satchel:ticket:7"); got.Approval != nil {
		t.Fatal("nil context yielded grant")
	}
}
