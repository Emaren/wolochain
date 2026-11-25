package cmd

// This is the existing CLI stored-run inspection over authenticated HTTP.
// It cannot execute, reconcile, retry, rewrite or classify a missing payment.
import (
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"os"
)

func (cfg settlementConfig) inspectSettlementRunHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "private, no-store")
	if r.Method != http.MethodGet {
		writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
		return
	}
	// Unlike optional-token compatibility on old public read surfaces, this
	// private recovery record requires an explicitly configured bearer token.
	if cfg.AuthToken == "" || cfg.checkAuth(r) != nil {
		writeJSONResponse(w, http.StatusUnauthorized, map[string]string{"detail": "private authentication required"})
		return
	}
	query, err := url.ParseQuery(r.URL.RawQuery)
	values := query["settlement_run_id"]
	if err != nil || r.URL.RawPath != "" || len(r.URL.RawQuery) > 512 || len(query) != 1 || len(values) != 1 || validateSettlementRunID(values[0]) != nil {
		writeJSONResponse(w, http.StatusBadRequest, map[string]string{"detail": "one exact settlement_run_id is required"})
		return
	}
	id := values[0]
	if r.Context().Err() != nil {
		writeJSONResponse(w, http.StatusRequestTimeout, map[string]string{"detail": "inspection canceled"})
		return
	}
	record, err := readSettlementRunStoredResult(cfg.runRecordPath(id))
	if errors.Is(err, os.ErrNotExist) {
		// Missing is UNKNOWN. In particular, it does not prove a prior request
		// failed or permit resubmitting a possibly broadcast payment.
		writeJSONResponse(w, http.StatusOK, settlementRunInspectResponse{Found: false, SettlementRunID: id})
		return
	}
	if err != nil || record.Request.SettlementRunID != id || record.Response.SettlementRunID != id ||
		record.Fingerprint != hashSettlementRunRequest(record.Request) || len(record.Request.Payouts) > settlementMaxRunPayouts ||
		len(record.Response.Payouts) > settlementMaxRunPayouts || r.Context().Err() != nil {
		writeJSONResponse(w, http.StatusConflict, map[string]string{"detail": "stored run is unavailable or unverifiable"})
		return
	}
	summary := summarizeSettlementRunStoredResult(record)
	response := settlementRunInspectResponse{Found: true, SettlementRunID: id, Summary: &summary, Record: &record}
	// Omit the filesystem RunPath. Preserve all original request/response
	// statuses and candidate hashes exactly, including prebroadcast UNKNOWN.
	wire, err := json.Marshal(response)
	if err != nil || len(wire) > settlementReceiptMaxStateBytes {
		writeJSONResponse(w, http.StatusConflict, map[string]string{"detail": "stored run exceeds inspection bounds"})
		return
	}
	writeJSONResponse(w, http.StatusOK, response)
}
