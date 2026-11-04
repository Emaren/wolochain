package satchelservice

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
)

// The existing private authentication, loopback restriction, concurrency bound
// and timeout apply before this read-only route. Never return these sensitive
// raw records through a browser or a public evidence endpoint.
func (h *privateHTTPHandler) custodyJournalSnapshot(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}
	backend, ok := h.backend.(HTTPCustodyJournalSnapshotBackend)
	if !ok || ctx.Err() != nil {
		httpFailure(w, http.StatusServiceUnavailable, "custody_journal_snapshot_unavailable")
		return
	}
	raw, err := backend.CustodyJournalSnapshot()
	var snapshot CustodyJournalProofSnapshot
	if err != nil || len(raw) == 0 || len(raw) > custodyJournalSnapshotMaxEncoded || json.Unmarshal(raw, &snapshot) != nil ||
		snapshot.Policy.Vault != h.identity.VaultAddress || snapshot.Policy.BettingEscrow != h.identity.EscrowAddress {
		httpFailure(w, http.StatusConflict, "custody_journal_snapshot_unverifiable")
		return
	}
	root := sha256.New()
	root.Write([]byte("aoe2war/satchel/execution-journal/v1\x00"))
	root.Write(snapshot.Frames)
	// Validate transport framing only. These locally calculated expectations are
	// NOT authenticated financial approval. The consumer must separately verify
	// the independent review's original journal and policy commitments.
	if _, err := VerifyCustodyJournalSnapshot(raw, hashJSON(snapshot.Policy), hex.EncodeToString(root.Sum(nil))); err != nil || ctx.Err() != nil {
		httpFailure(w, http.StatusConflict, "custody_journal_snapshot_unverifiable")
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(raw) // Preserve canonical bytes; no framing or newline rewrite.
}
