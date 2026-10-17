package cmd

import (
	"encoding/json"
	"testing"

	"github.com/emaren/wolochain/internal/satchelservice"
)

// This is the real existing escrow run normalizer. No service, wallet, signer
// or chain transaction is started; the recipient is a parser-only fixture.
func TestSatchelIndependentLegReturnRunsPreserveExactEscrowContract(t *testing.T) {
	for _, tc := range []struct{ claim, amount string }{{"101", "2000000"}, {"102", "400000"}} {
		t.Run(tc.claim, func(t *testing.T) {
			id := "satchel:claim-return:" + tc.claim
			memo := "aoe2war/satchel/claim-return/v1/" + tc.claim
			run := satchelservice.ReturnRun{SettlementRunID: id, SourceApp: "aoe2hdbets", SourceEventID: "satchel:ticket:17", SignerRole: "escrow", Payouts: []satchelservice.ReturnPayout{{RequestID: id, ToAddress: "wolo1recipienta000000000000000000000000000000", AmountUWolo: tc.amount, Memo: memo}}}
			encoded, err := json.Marshal(run)
			if err != nil {
				t.Fatal(err)
			}
			var wire settlementRunRequest
			if err = json.Unmarshal(encoded, &wire); err != nil {
				t.Fatal(err)
			}
			normalized, result := prepareSettlementRunRequest(wire)
			if result.FailureCode != "" || len(normalized.Payouts) != 1 || normalized.SignerRole != settlementEscrowSignerRole || normalized.SettlementRunID != id || normalized.SourceEventID != "satchel:ticket:17" {
				t.Fatalf("incompatible existing escrow request: %+v", result)
			}
			p := normalized.Payouts[0]
			if p.RequestID != id || p.AmountUWolo != tc.amount || p.Memo != memo || p.ToAddress != run.Payouts[0].ToAddress {
				t.Fatalf("leg refund/payout altered or fee deducted: %+v", p)
			}
		})
	}
}
