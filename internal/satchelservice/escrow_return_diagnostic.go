package satchelservice

// Request-local observations only. These fixed labels never grant execution,
// expose signed input, or change the permanent UNKNOWN/replay contract.
import (
	"context"
	"net/http"
	"strconv"
	"sync"
	"time"
)

type escrowBoundaryKey struct{}
type escrowBoundaryObservation struct {
	mu      sync.Mutex
	stage   string
	started time.Time
}

// EscrowReturnBoundaryName admits only source-defined nonsecret labels. A
// client must never echo arbitrary transport errors, headers or response data.
func EscrowReturnBoundaryName(s string) string {
	switch s {
	case "request", "prior_journal", "owner_permission", "reserve_review", "global_permission", "owner_verification",
		"enrolled_signer", "engine_lock", "reserve_enrollment", "reserve_bank", "reserve_journal", "reserve_native_proof",
		"reserve_obligations", "reserve_inventory", "reserve_review_outlives_bank", "reserve_completion", "reserve_late_bank",
		"reserve_late_proof", "reserve_revocation", "durable_intent", "sign_authorization", "broadcast_authorization":
		return s
	}
	return "unclassified"
}

func escrowBoundary(ctx context.Context, stage string) {
	if ctx == nil {
		return
	}
	if d, _ := ctx.Value(escrowBoundaryKey{}).(*escrowBoundaryObservation); d != nil {
		d.mu.Lock()
		d.stage = EscrowReturnBoundaryName(stage)
		d.mu.Unlock()
	}
}

func escrowBoundaryHeaders(ctx context.Context, w http.ResponseWriter, d *escrowBoundaryObservation) {
	d.mu.Lock()
	stage := d.stage
	d.mu.Unlock()
	w.Header().Set("X-Wolo-Escrow-Boundary", EscrowReturnBoundaryName(stage))
	w.Header().Set("X-Wolo-Escrow-Elapsed-Ms", strconv.FormatInt(time.Since(d.started).Milliseconds(), 10))
	state := "active"
	if ctx.Err() == context.DeadlineExceeded {
		state = "deadline"
	} else if ctx.Err() != nil {
		state = "canceled"
	}
	w.Header().Set("X-Wolo-Escrow-Context", state)
}
