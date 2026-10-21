package satchelservice

import (
	"strings"
	"testing"
)

func reviewerTestWager() WagerReservation {
	return WagerReservation{Version: 1, OperationID: "satchel:ticket:7",
		OwnerID: "owner-7", AmountUWolo: "12000000",
		FeeUWolo: "1"}
}
func reviewerTestCensus() ReviewerFeeCensus {
	return ReviewerFeeCensus{ChainID:"wolo-1",Denom:"uwolo", OperationID:"satchel:ticket:7",
		BankBalanceUWolo:"100000005",AllOwnerLiabilitiesUWolo:"100000000",
		PendingOperations:[]ReviewerPendingFee{
			{OperationID:"satchel:ticket:1",Stage:"prepared",FeeUWolo:"1"},
			{OperationID:"satchel:withdrawal:2",Stage:"uncertain",FeeUWolo:"1"},
		},
		NewOperationFeeUWolo:"1",MinimumUnencumberedGasUWolo:"2",
		PendingOperationsComplete:true}
}
func TestReviewerFeeBudgetExactBoundaryIsOnlyArithmetic(t *testing.T) {
	got,err:=AssessReviewerFeeBudget(reviewerTestCensus(),reviewerTestWager())
	if err!=nil||got.Status!="BUDGET_SUFFICIENT_NONAUTHORIZING"||
		got.PendingFeeUWolo!="2"||got.RequiredUWolo!="100000005"||got.RemainingUWolo!="0"||
		got.SpendingAuthorized||got.BankAuthenticated||got.OwnerLedgerAuthenticated {
		t.Fatalf("arithmetic result incorrectly authorized: %+v %v",got,err)
	}
}
func TestReviewerFeeBudgetOneUWoloShortCannotTouchOwnerPrincipal(t *testing.T) {
	c:=reviewerTestCensus();c.BankBalanceUWolo="100000004"
	got,err:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if err!=nil||got.Status!="INSUFFICIENT_HEADROOM"||got.RemainingUWolo!=""||got.SpendingAuthorized{
		t.Fatalf("insolvent headroom accepted: %+v %v",got,err)
	}
}
func TestReviewerFeeBudgetIncompleteInventoryHoldsDespiteSurplus(t *testing.T) {
	c:=reviewerTestCensus();c.BankBalanceUWolo="900000000";c.PendingOperationsComplete=false
	got,err:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if err!=nil||got.Status!="CENSUS_INCOMPLETE"||got.RequiredUWolo!=""||
		got.PendingFeeUWolo!="2"||got.SpendingAuthorized{
		t.Fatalf("incomplete census granted authority: %+v %v",got,err)
	}
}
func TestReviewerFeeBudgetUncertainOperationsRemainReserved(t *testing.T){
	c:=reviewerTestCensus()
	got,_:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if got.PendingFeeUWolo!="2"{t.Fatal("forgot unknown transaction gas")}
	c.PendingOperations=c.PendingOperations[:1]
	next,_:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if next.PendingFeeUWolo!="1"{t.Fatal("pending gas arithmetic drift")}
}
func TestReviewerFeeBudgetNeverUsesCallerFlagsForAuthentication(t *testing.T){
	c:=reviewerTestCensus()
	c.PendingOperationsComplete=true
	got,_:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if got.SpendingAuthorized||got.BankAuthenticated||got.OwnerLedgerAuthenticated{
		t.Fatal("a caller-supplied complete flag is not financial authentication")
	}
}
func TestReviewerFeeBudgetRejectsUnboundNewFeeOrGame(t *testing.T){
	c:=reviewerTestCensus();w:=reviewerTestWager()
	for _,mutate:=range []func(*ReviewerFeeCensus){
		func(x *ReviewerFeeCensus){x.NewOperationFeeUWolo="2"},
		func(x *ReviewerFeeCensus){x.OperationID="satchel:ticket:8"},
		func(x *ReviewerFeeCensus){x.ChainID="badchain"},
		func(x *ReviewerFeeCensus){x.Denom="wolo"},
	} {
		x:=c;mutate(&x)
		if _,err:=AssessReviewerFeeBudget(x,w);err==nil {t.Fatal("mismatched operation or fee admitted")}
	}
}
func TestReviewerFeeBudgetRejectsDuplicateAndSelfIncludedPending(t *testing.T){
	for _,pending:=range [][]ReviewerPendingFee{
		{{OperationID:"same",Stage:"prepared",FeeUWolo:"1"},{OperationID:"same",Stage:"uncertain",FeeUWolo:"1"}},
		{{OperationID:"satchel:ticket:7",Stage:"uncertain",FeeUWolo:"1"}},
		{{OperationID:"../../dir",Stage:"prepared",FeeUWolo:"1"}},
		{{OperationID:"abc",Stage:"confirmed",FeeUWolo:"1"}},
	}{
		c:=reviewerTestCensus();c.PendingOperations=pending
		if _,err:=AssessReviewerFeeBudget(c,reviewerTestWager());err==nil {t.Fatalf("unreviewable pending entry accepted: %+v",pending)}
	}
}
func TestReviewerFeeBudgetRejectsNoncanonicalFees(t *testing.T){
	for _,fee:=range []string{"","0","01","-1","1.1","1000001",strings.Repeat("9",25),"NaN"} {
		c:=reviewerTestCensus();c.NewOperationFeeUWolo=fee
		w:=reviewerTestWager();w.FeeUWolo=fee
		if _,err:=AssessReviewerFeeBudget(c,w);err==nil {t.Fatalf("bad new fee %q accepted",fee)}
		c=reviewerTestCensus()
		c.PendingOperations[0].FeeUWolo=fee
		if _,err:=AssessReviewerFeeBudget(c,reviewerTestWager());err==nil{t.Fatalf("bad pending fee %q accepted",fee)}
	}
}
func TestReviewerFeeBudgetRejectsOverflowAndOversizedInventory(t *testing.T){
	c:=reviewerTestCensus()
	c.AllOwnerLiabilitiesUWolo="9223372036854775807"
	if _,err:=AssessReviewerFeeBudget(c,reviewerTestWager());err==nil{t.Fatal("int64 overflow allowed")}
	c=reviewerTestCensus();c.PendingOperations=make([]ReviewerPendingFee,reviewerMaxPendingOperations+1)
	if _,err:=AssessReviewerFeeBudget(c,reviewerTestWager());err==nil{t.Fatal("unbounded inventory accepted")}
	c=reviewerTestCensus();c.BankBalanceUWolo="9223372036854775808"
	if _,err:=AssessReviewerFeeBudget(c,reviewerTestWager());err==nil{t.Fatal("bank out of range accepted")}
}
func TestReviewerFeeBudgetZeroOrMissingInventoryIsNotProof(t *testing.T){
	c:=reviewerTestCensus();c.PendingOperations=nil;c.PendingOperationsComplete=false
	got,err:=AssessReviewerFeeBudget(c,reviewerTestWager())
	if err!=nil||got.Status!="CENSUS_INCOMPLETE"{t.Fatalf("empty incomplete census accepted: %+v %v",got,err)}
}
