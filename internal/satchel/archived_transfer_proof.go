package satchel

import (
	"context"
	"time"
)

// ArchivedTransferEvidence is deliberately NOT AuthenticatedEvidence. An old
// Comet signature can be rechecked against a separately supplied historical
// checkpoint, but that does not prove current consensus, custody, solvency,
// global payment ownership or authority to retry an on-chain transfer.
//
// This type can be used ONLY for an archival/noncrediting report. It deliberately
// cannot be passed to any API accepting the live AuthenticatedEvidence type.
type ArchivedTransferEvidence struct {
	evidence AuthenticatedEvidence
}

func (e ArchivedTransferEvidence) Observation() Observation { return e.evidence.Observation() }
func (e ArchivedTransferEvidence) Receipt() ReceiptCandidate { return e.evidence.Receipt() }
func (e ArchivedTransferEvidence) ConsensusAuthenticatedAgainstProvidedAnchor() bool {
	return e.evidence.ConsensusAuthenticated()
}
func (ArchivedTransferEvidence) CreditAuthorized() bool { return false }

// VerifyArchivedTransferProof replays a bounded portable transfer proof at an
// EXPLICIT historical evaluation instant. Only the historical offline command
// should call this function. Using time.Now here would categorically refuse
// genuine old headers once their original trust period elapsed. Conversely,
// accepting caller-supplied asOf never makes a historical checkpoint current.
//
// All ordinary current-time VerifyTransferProof, VerifyDepositProof, bank
// freshness, and custody admission APIs remain unchanged. The existing reader
// still verifies Comet signed headers/validator transitions, H/H+1 commitments,
// witness consistency, exact signed transfer and receipt under the supplied
// trust anchor, evaluated at asOf. An authenticated independent provenance for
// that anchor, the historical asOf instant and original obligation must be
// established OUTSIDE this function and its nonauthorizing consumer.
func VerifyArchivedTransferProof(
	ctx context.Context,
	anchor TrustAnchor,
	asOf time.Time,
	intent TransferIntent,
	hash string,
	proof PortableProof,
) (ArchivedTransferEvidence, error) {
	if ctx == nil || asOf.IsZero() || asOf.After(time.Now().Add(5*time.Second)) ||
		asOf.Year() < 2000 || !validTrustAnchor(anchor) {
		return ArchivedTransferEvidence{}, fail(InvalidConfiguration, "historical", "as_of")
	}
	verifier, err := NewProofVerifier(anchor)
	if err != nil {
		return ArchivedTransferEvidence{}, err
	}
	// A distinct, ephemeral verifier is scoped to this one offline call. Never
	// replace the clock of a long-lived verifier shared with live deposits.
	archiveClock := asOf.UTC()
	verifier.now = func() time.Time { return archiveClock }
	evidence, err := verifier.VerifyTransferProof(ctx, intent, hash, proof)
	if err != nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {
		if err != nil {
			return ArchivedTransferEvidence{}, err
		}
		return ArchivedTransferEvidence{}, fail(UntrustedConsensus, "historical", "anchor")
	}
	return ArchivedTransferEvidence{evidence: evidence}, nil
}
