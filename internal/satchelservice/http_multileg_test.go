package satchelservice

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPrivateHTTPMultiLegSchemaRejectsNestedAliases(t *testing.T) {
	for _, mode := range []string{"leg_case", "leg_unknown", "entitlement_case", "entitlement_unknown"} {
		t.Run(mode, func(t *testing.T) {
			a := testReturnApproval(t, "satchel:ticket:1", "101")
			raw, _ := json.Marshal(a)
			var body map[string]any
			if err := json.Unmarshal(raw, &body); err != nil {
				t.Fatal(err)
			}
			leg := body["allocation"].(map[string]any)["legs"].([]any)[0].(map[string]any)
			entry := leg["entitlements"].([]any)[0].(map[string]any)
			switch mode {
			case "leg_case":
				leg["LEG_ID"] = leg["leg_id"]
				delete(leg, "leg_id")
			case "leg_unknown":
				leg["new_signer"] = "escrow"
			case "entitlement_case":
				entry["CLAIM_ID"] = entry["claim_id"]
				delete(entry, "claim_id")
			case "entitlement_unknown":
				entry["owner_id"] = "another-owner"
			}
			data, _ := json.Marshal(body)
			b := &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, vault: testHTTPAddress(t, 100)}
			h := testHTTPHandler(t, b, testHTTPConfig(t))
			w := httptest.NewRecorder()
			h.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/prepare", string(data)))
			if w.Code != http.StatusBadRequest || b.prepareCalls.Load() != 0 || b.submissions.Load() != 0 {
				t.Fatalf("nested alias escaped exact wire schema: status=%d body=%s", w.Code, w.Body.String())
			}
		})
	}
}
func TestPrivateHTTPMultiLegReceiptCannotRetargetEntitlement(t *testing.T) {
	for _, tc := range []struct {
		name   string
		mutate func(*ReturnReceipt)
	}{
		{"version", func(r *ReturnReceipt) { r.Version = 1 }},
		{"ticket", func(r *ReturnReceipt) { r.TicketID = "2" }},
		{"market", func(r *ReturnReceipt) { r.MarketID = "502" }},
		{"leg", func(r *ReturnReceipt) { r.LegID = "desync" }},
		{"entitlement", func(r *ReturnReceipt) { r.EntitlementID = "other-claim" }},
		{"allocation", func(r *ReturnReceipt) { r.AllocationID = "other-allocation" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			a := testReturnApproval(t, "satchel:ticket:1", "101")
			b := &httpTestReturnBackend{httpTestBackend: &httpTestBackend{}, vault: testHTTPAddress(t, 100)}
			r, err := b.ReconcileClaimReturn(t.Context(), a, testHTTPHash)
			if err != nil {
				t.Fatal(err)
			}
			tc.mutate(&r)
			b.receipt = &r
			data, _ := json.Marshal(map[string]any{"approval": a, "tx_hash": testHTTPHash})
			h := testHTTPHandler(t, b, testHTTPConfig(t))
			w := httptest.NewRecorder()
			h.ServeHTTP(w, testHTTPRequest(http.MethodPost, "/satchel/v1/returns/reconcile", string(data)))
			if w.Code != http.StatusServiceUnavailable || b.submissions.Load() != 0 {
				t.Fatalf("wrong bound entitlement returned as verified: status=%d body=%s", w.Code, w.Body.String())
			}
		})
	}
}
