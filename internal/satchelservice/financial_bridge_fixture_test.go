package satchelservice

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"
)

func financialBridgeWireFixture(t *testing.T) any {
	t.Helper()
	p := engineTestPolicy(t)
	r := engineTestWithdrawal(t)
	approval := testReturnApproval(t, "satchel:ticket:1", "101")
	text, err := WithdrawalChallengeText(r.OwnerMandate.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	ownerBytes, err := WithdrawalOwnerSignBytes(r.OwnerMandate.Challenge)
	if err != nil {
		t.Fatal(err)
	}
	return map[string]any{
		"fixture_only": true, "mainnet_authority": false,
		"approval_public_key_hex": hex.EncodeToString(p.WithdrawalApprovalKey),
		"vault":                   p.Vault, "betting_escrow": p.BettingEscrow,
		"owner_challenge_text": text, "owner_adr36_sign_bytes": string(ownerBytes),
		"owner_mandate_digest": OwnerMandateDigest(*r.OwnerMandate), "withdrawal_hold_digest": r.Approval.HoldDigest,
		"withdrawal_request":             httpWithdrawal{Protocol: 1, OperationID: r.OperationID, ChainID: r.ChainID, Sender: r.Sender, Recipient: r.Recipient, Amount: httpCoin{Denom: r.Denom, Amount: r.AmountUWolo}, Memo: r.Memo, OwnerID: r.OwnerID, Approval: r.Approval, OwnerMandate: r.OwnerMandate},
		"withdrawal_approval_sign_bytes": string(ApprovalMessage(*r.Approval, p.Vault)),
		"allocation":                     approval.Allocation, "allocation_digest": approval.AllocationDigest, "allocation_sign_bytes": string(AllocationMessage(*approval.Allocation, p)),
		"return_approval": approval, "return_approval_sign_bytes": string(ReturnApprovalMessage(approval, p)),
	}
}

func TestFinancialBridgeExactSignedByteFixture(t *testing.T) {
	expected, err := json.MarshalIndent(financialBridgeWireFixture(t), "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	actual, err := os.ReadFile("testdata/financial-bridge-v1.json")
	if err != nil {
		t.Fatalf("FIXTURE_BEGIN\n%s\nFIXTURE_END", expected)
	}
	var canonical any
	if json.Unmarshal(actual, &canonical) != nil {
		t.Fatal("invalid fixture JSON")
	}
	canonicalBytes, _ := json.MarshalIndent(canonical, "", "  ")
	var expectedCanonical any
	if json.Unmarshal(expected, &expectedCanonical) != nil {
		t.Fatal("invalid source fixture JSON")
	}
	expectedBytes, _ := json.MarshalIndent(expectedCanonical, "", "  ")
	if string(canonicalBytes) != string(expectedBytes) {
		t.Fatal("published cross-language financial fixture drifted from source signing bytes")
	}
}
