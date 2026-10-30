package satchelservice

import "context"

// RequireIssuanceAuthorization binds a trusted runtime's fresh authorization
// fence once, before this process's first ReviewOne use. Historical journal
// records do not prevent binding after restart and are never rewritten here.
// The callback executes under the issuer lock and must not reenter the issuer.
// It must come from protected startup composition, never an HTTP request.
//
// Standalone library users retain their existing independently authenticated
// source contract until opting in; woloreviewerd always binds before serving.
// Once bound, no caller can remove, replace or relax this additional fence.
func (r *ReviewerIssuer) RequireIssuanceAuthorization(authorize func(context.Context) bool) error {
	if r == nil || authorize == nil {
		return ErrReviewerHeld
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.db == nil || r.issuanceStarted || r.issuanceAuthorization != nil {
		return ErrReviewerHeld
	}
	r.issuanceAuthorization = authorize
	return nil
}

// Caller owns r.mu. Check context both before and after the callback so a
// deadline/cancellation during authorization cannot reach signing/persistence.
func (r *ReviewerIssuer) issuanceAuthorizedLocked(ctx context.Context) bool {
	return ctx != nil && ctx.Err() == nil &&
		(r.issuanceAuthorization == nil || r.issuanceAuthorization(ctx)) && ctx.Err() == nil
}
