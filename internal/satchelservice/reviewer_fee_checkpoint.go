package satchelservice

// These read-only checkpoints expose actual durable fee obligations to the
// existing reviewer. They confer no bank, coverage, signing or credit authority.
// Independent reserve signatures and the current native bank remain required.
type ReviewerCustodyFeeCheckpoint struct {
	Protocol                    int                  `json:"protocol"`
	Kind                        string               `json:"kind"`
	ChainID                     string               `json:"chain_id"`
	Denom                       string               `json:"denom"`
	Vault                       string               `json:"vault"`
	JournalDigest               string               `json:"journal_digest"`
	PolicyDigest                string               `json:"policy_digest"`
	ObservedAtMS                int64                `json:"observed_at_ms"`
	UnresolvedFees              []ReviewerPendingFee `json:"unresolved_fees"`
	AccountedOperations         map[string]string    `json:"accounted_operations"`
	AccountedFingerprints       map[string]string    `json:"accounted_fingerprints"`
	WagerApprovalKeyFingerprint string               `json:"wager_approval_key_fingerprint"`
}

type ReviewerIssuedFeeCheckpoint struct {
	Protocol               int                  `json:"protocol"`
	Kind                   string               `json:"kind"`
	ChainID                string               `json:"chain_id"`
	Denom                  string               `json:"denom"`
	Vault                  string               `json:"vault"`
	JournalDigest          string               `json:"journal_digest"`
	PolicyDigest           string               `json:"policy_digest"`
	ApprovalKeyFingerprint string               `json:"approval_key_fingerprint"`
	ObservedAtMS           int64                `json:"observed_at_ms"`
	PendingFees            []ReviewerPendingFee `json:"pending_fees"`
	EntryFingerprints      map[string]string    `json:"entry_fingerprints"`
}
