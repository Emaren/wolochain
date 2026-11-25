package cmd

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestSettlementRunHTTPInspectionIsExactAuthenticatedAndNonexecuting(t *testing.T) {
	id := "satchel:claim-return:101"
	cfg := settlementConfig{StateDir: t.TempDir(), AuthToken: "isolated-inspection-token"}
	request := normalizedSettlementRunRequest{SettlementRunID: id, SourceApp: "aoe2hdbets", SourceEventID: "satchel:ticket:1", SignerRole: "escrow",
		Payouts: []normalizedSettlementPayout{{Index: 0, RequestID: id, ToAddress: "wolo1fixture", AmountUWolo: "78000000", Memo: "aoe2war/satchel/claim-return/v1/101"}}}
	for _, status := range []string{"accepted", "confirmed", "unknown", "failed", "partial"} {
		t.Run(status, func(t *testing.T) {
			record := settlementRunStoredResult{Request: request, Fingerprint: hashSettlementRunRequest(request), UpdatedAt: time.Now().UTC(),
				Response: settlementRunResponse{SettlementRunID: id, Status: status, SignerRole: "escrow", SignerAddress: "wolo1escrowfixture",
					Payouts: []settlementRunPayoutResult{{RequestID: id, Status: status, TxHash: strings.Repeat("A", 64), ToAddress: "wolo1fixture", AmountUWolo: "78000000"}}}}
			path := cfg.runRecordPath(id)
			if err := writeSettlementRunStoredResult(path, record); err != nil {
				t.Fatal(err)
			}
			before, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			r := httptest.NewRequest(http.MethodGet, "/settlement/v1/runs/inspect?settlement_run_id="+url.QueryEscape(id), nil)
			r.Header.Set("Authorization", "Bearer "+cfg.AuthToken)
			w := httptest.NewRecorder()
			cfg.newSettlementHTTPHandler().ServeHTTP(w, r)
			var got settlementRunInspectResponse
			if w.Code != http.StatusOK || json.Unmarshal(w.Body.Bytes(), &got) != nil || !got.Found || got.RunPath != "" || got.Record == nil || !reflect.DeepEqual(*got.Record, record) {
				t.Fatal("inspection changed a stored outcome", w.Code, w.Body.String())
			}
			after, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(before, after) {
				t.Fatal("read-only inspection rewrote payment history")
			}
		})
	}
	handler := cfg.newSettlementHTTPHandler()
	for _, query := range []string{"", "settlement_run_id=../outside", "settlement_run_id=" + id + "&settlement_run_id=" + id, "settlement_run_id=" + id + "&execute=1", "settlement_run_id=%zz", "settlement_run_id=" + strings.Repeat("a", 97)} {
		r := httptest.NewRequest(http.MethodGet, "/settlement/v1/runs/inspect?"+query, nil)
		r.Header.Set("Authorization", "Bearer "+cfg.AuthToken)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != http.StatusBadRequest {
			t.Fatal("ambiguous inspection query accepted", query, w.Code)
		}
	}
	for _, token := range []string{"", "wrong"} {
		r := httptest.NewRequest(http.MethodGet, "/settlement/v1/runs/inspect?settlement_run_id="+id, nil)
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != http.StatusUnauthorized {
			t.Fatal("unauthenticated inspection", w.Code)
		}
	}
	r := httptest.NewRequest(http.MethodGet, "/settlement/v1/runs/inspect?settlement_run_id=satchel:claim-return:999", nil)
	r.Header.Set("Authorization", "Bearer "+cfg.AuthToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	var missing map[string]any
	if w.Code != http.StatusOK || json.Unmarshal(w.Body.Bytes(), &missing) != nil || missing["found"] != false || missing["record"] != nil || missing["status"] != nil {
		t.Fatal("missing became a failed payment", w.Code, w.Body.String())
	}
	cfg.AuthToken = ""
	w = httptest.NewRecorder()
	cfg.newSettlementHTTPHandler().ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatal("unconfigured authentication opened inspection")
	}
}
