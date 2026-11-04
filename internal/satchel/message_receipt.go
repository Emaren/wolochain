package satchel

import "context"

// canonicalMessageEvidence provides a separate physical MsgSend namespace for
// authenticated single-message transactions. Legacy ReadTransfer receipt IDs
// and the complete Observation event list/ordinal remain unchanged. The exact
// existing protobuf parser, transaction inclusion and committed result checks
// must all succeed before event ordinal zero or one can identify message zero.
func canonicalMessageEvidence(intent TransferIntent, evidence AuthenticatedEvidence) (AuthenticatedEvidence, error) {
	if !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() || !exactSend(evidence.Observation().TxBytes, intent.Sender, intent.Recipient, intent.AmountUWolo, intent.Memo) {
		return AuthenticatedEvidence{}, fail(TransactionMismatch, "message", "authenticated_single_send")
	}
	evidence.evidence.Receipt = ReceiptCandidate{ChainID, evidence.Receipt().TxHash, 0}
	return evidence, nil
}

// ReadMessageTransfer authenticates the same exact native transaction as
// ReadTransfer, returning its physical MsgSend index zero. It never renumbers
// bank events or changes the legacy event-ordinal receipt API.
func (r *TrustedReader) ReadMessageTransfer(ctx context.Context, intent TransferIntent, hash string) (AuthenticatedEvidence, error) {
	evidence, err := r.ReadTransfer(ctx, intent, hash)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	return canonicalMessageEvidence(intent, evidence)
}

// VerifyMessageTransferProof reuses the full portable Comet/SDK verifier and
// exact single-MsgSend parser before returning canonical physical message zero.
// A caller-supplied event ordinal, hash or receipt boolean cannot construct it.
func (v *ProofVerifier) VerifyMessageTransferProof(ctx context.Context, intent TransferIntent, hash string, proof PortableProof) (AuthenticatedEvidence, error) {
	evidence, err := v.VerifyTransferProof(ctx, intent, hash, proof)
	if err != nil {
		return AuthenticatedEvidence{}, err
	}
	return canonicalMessageEvidence(intent, evidence)
}
