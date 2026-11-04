// Package nativeverifier is a bounded, offline, non-signing proof adapter.
// It never consumes a global receipt, opens custody or grants financial GO.
package nativeverifier

import (
	"github.com/emaren/wolochain/internal/epochescrow"
	"github.com/emaren/wolochain/internal/satchel"
	"github.com/emaren/wolochain/internal/satchelservice"
)

const MaxBundleBytes = 14*1024*1024 + 128*1024
const MaxPinsBytes = 256 * 1024
const ModeDisposableTest = "DISPOSABLE_TEST"
const ModeProduction = "PRODUCTION"

type Identity struct {
	SourceCommit string `json:"source_commit"`
	Compiler     string `json:"compiler"`
	BinarySHA256 string `json:"binary_sha256"`
	Modified     bool   `json:"modified"`
}

type OwnerEnrollment struct {
	UID          string `json:"uid"`
	Wallet       string `json:"wallet"`
	PublicKeyHex string `json:"public_key_hex"`
}

type ObserverPin struct {
	Role           string `json:"role"`
	KeyID          string `json:"key_id"`
	OperatorID     string `json:"operator_id"`
	EndpointSHA256 string `json:"endpoint_sha256"`
	PublicKeyHex   string `json:"public_key_hex"`
}

// The five keys map directly to the existing reserve review authority.
type FinancialKeys struct {
	AccountingReviewerKeyHex string `json:"accounting_reviewer_key_hex"`
	CustodyReviewerKeyHex    string `json:"custody_reviewer_key_hex"`
	ExecutionAuthorityKeyHex string `json:"execution_authority_key_hex"`
	WagerApprovalKeyHex      string `json:"wager_approval_key_hex"`
	WithdrawalApprovalKeyHex string `json:"withdrawal_approval_key_hex"`
}

// Pins must originate from the protected fixed installation, never stdin.
// TEST enrollment authenticates disposable evidence, not production operators.
type Pins struct {
	Version                  int                `json:"version"`
	Mode                     string             `json:"mode"`
	ExpectedIdentity         Identity           `json:"expected_identity"`
	ConfigSHA256             string             `json:"config_sha256"`
	Policy                   epochescrow.Policy `json:"policy"`
	Owners                   []OwnerEnrollment  `json:"owners"`
	Observers                []ObserverPin      `json:"observers"`
	FinancialKeys            FinancialKeys      `json:"financial_keys"`
	RequiredLiabilitySources []string           `json:"required_liability_sources"`
	ProductionTrustEnrolled  bool               `json:"production_trust_enrolled"`
	EnrollmentSHA256         string             `json:"enrollment_sha256"`
}

type SourceSnapshot struct {
	SourceID       string `json:"source_id"`
	SnapshotSHA256 string `json:"snapshot_sha256"`
}

type LiabilityClaim struct {
	ClaimID     string `json:"claim_id"`
	SourceID    string `json:"source_id"`
	AccountRole string `json:"account_role"`
	Kind        string `json:"kind"` // confirmed or unknown
	AmountUWolo string `json:"amount_uwolo"`
}

// Inventory contains actual signed-review inputs, not digest-only assertions.
// It does not itself prove that operators supplied every real-world obligation.
type Inventory struct {
	Version         int              `json:"version"`
	EpochID         string           `json:"epoch_id"`
	StateHeight     int64            `json:"state_height"`
	CommitBlockHash string           `json:"commit_block_hash"`
	AppHash         string           `json:"app_hash"`
	Sources         []SourceSnapshot `json:"sources"`
	Claims          []LiabilityClaim `json:"claims"`
}

type AccountReview struct {
	AccountRole string                             `json:"account_role"`
	Review      satchelservice.SignedReserveReview `json:"review"`
}

// Capture is an enrolled observer's signature over the complete payload digest
// and the exact observed native root/head/time. Transcript role labels alone
// never satisfy observer authentication.
type Capture struct {
	Version        int    `json:"version"`
	Role           string `json:"role"`
	KeyID          string `json:"key_id"`
	OperatorID     string `json:"operator_id"`
	EndpointSHA256 string `json:"endpoint_sha256"`
	PayloadSHA256  string `json:"payload_sha256"`
	StateHeight    int64  `json:"state_height"`
	CommitHeight   int64  `json:"commit_height"`
	BlockSHA256    string `json:"block_sha256"`
	AppSHA256      string `json:"app_sha256"`
	HeadHeight     int64  `json:"head_height"`
	ObservedAt     int64  `json:"observed_at"`
	ExpiresAt      int64  `json:"expires_at"`
	Signature      string `json:"signature"`
}

type DepositMandate struct {
	PolicySHA256      string `json:"policy_sha256"`
	EpochID           string `json:"epoch_id"`
	OwnerUID          string `json:"owner_uid"`
	OwnerWallet       string `json:"owner_wallet"`
	OwnerPublicKeyHex string `json:"owner_public_key_hex"`
	EconomicKey       string `json:"economic_key"`
	TxHash            string `json:"tx_hash"`
	AmountUWolo       string `json:"amount_uwolo"`
	Memo              string `json:"memo"`
	IssuedAt          int64  `json:"issued_at"`
	ExpiresAt         int64  `json:"expires_at"`
	OwnerSignature    string `json:"owner_signature"`
}

type Bundle struct {
	Version     int                              `json:"version"`
	Purpose     string                           `json:"purpose"`
	EconomicKey string                           `json:"economic_key"`
	TxHash      string                           `json:"tx_hash"`
	Request     *epochescrow.Request             `json:"request,omitempty"`
	Deposit     *DepositMandate                  `json:"deposit,omitempty"`
	Withdrawal  *satchelservice.TransferRequest  `json:"withdrawal,omitempty"`
	Funding     map[string]satchel.PortableProof `json:"funding,omitempty"`
	Preparation *epochescrow.Proofs              `json:"preparation,omitempty"`
	Effect      satchel.PortableProof            `json:"effect"`
	VaultBank   satchel.BankProof                `json:"vault_bank"`
	EscrowBank  satchel.BankProof                `json:"escrow_bank"`
	Inventory   Inventory                        `json:"inventory"`
	Reviews     []AccountReview                  `json:"reviews"`
	Captures    []Capture                        `json:"captures"`
}

type BankVerdict struct {
	AccountRole                string `json:"account_role"`
	Account                    string `json:"account"`
	BankStateHeight            int64  `json:"bank_state_height"`
	BankCommitHeight           int64  `json:"bank_commit_height"`
	BlockSHA256                string `json:"block_sha256"`
	AppSHA256                  string `json:"app_sha256"`
	BankBalanceUWolo           string `json:"bank_balance_uwolo"`
	LiabilitiesUWolo           string `json:"liabilities_uwolo"`
	MaximumUnknownOutflowUWolo string `json:"maximum_unknown_outflow_uwolo"`
	GasUWolo                   string `json:"gas_uwolo"`
	OperatingFloorUWolo        string `json:"operating_floor_uwolo"`
	InventorySHA256            string `json:"inventory_sha256"`
	NonOverlapSHA256           string `json:"nonoverlap_sha256"`
	ProofSHA256                string `json:"proof_sha256"`
}

type Verdict struct {
	WireVersion                   int         `json:"wire_version"`
	Protocol                      string      `json:"protocol"`
	NativeVerdict                 string      `json:"native_verdict"`
	LegacyPaymentAuthorized       bool        `json:"legacy_payment_authorized"`
	ChainID                       string      `json:"chain_id"`
	Denom                         string      `json:"denom"`
	EpochID                       string      `json:"epoch_id"`
	OwnerUID                      string      `json:"owner_uid"`
	Purpose                       string      `json:"purpose"`
	EconomicKey                   string      `json:"economic_key"`
	AmountUWolo                   string      `json:"amount_uwolo"`
	Sender                        string      `json:"sender"`
	Recipient                     string      `json:"recipient"`
	Memo                          string      `json:"memo"`
	TxHash                        string      `json:"tx_hash"`
	MessageIndex                  uint32      `json:"message_index"`
	MessageOrdinalKind            string      `json:"message_ordinal_kind"`
	FundingHeight                 int64       `json:"funding_height"`
	ChainTime                     string      `json:"chain_time"`
	TxSuccessProven               bool        `json:"tx_success_proven"`
	NativeConsensusAuthenticated  bool        `json:"native_consensus_authenticated"`
	NativeICS23Authenticated      bool        `json:"native_ics23_authenticated"`
	FundingMessageCount           int         `json:"funding_message_count"`
	OriginalFundingPrincipalUWolo string      `json:"original_funding_principal_uwolo"`
	PrimaryHeadHeight             int64       `json:"primary_head_height"`
	WitnessHeadHeight             int64       `json:"witness_head_height"`
	BankStateHeight               int64       `json:"bank_state_height"`
	BankCommitHeight              int64       `json:"bank_commit_height"`
	BlockSHA256                   string      `json:"block_sha256"`
	AppSHA256                     string      `json:"app_sha256"`
	VaultAddress                  string      `json:"vault_address"`
	EscrowAddress                 string      `json:"escrow_address"`
	VaultBank                     BankVerdict `json:"vault_bank"`
	EscrowBank                    BankVerdict `json:"escrow_bank"`
	NativeVerifierSource          string      `json:"native_verifier_source"`
	NativeVerifierBinarySHA256    string      `json:"native_verifier_binary_sha256"`
	TrustAnchorSHA256             string      `json:"trust_anchor_sha256"`
	RawProofBundleSHA256          string      `json:"raw_proof_bundle_sha256"`
	OwnerMandateAuthenticated     bool        `json:"owner_mandate_authenticated"`
	ProofSHA256                   string      `json:"proof_sha256"`
	VerificationRecordSHA256      string      `json:"verification_record_sha256"`
	ObservedAt                    string      `json:"observed_at"`
	ExpiresAt                     string      `json:"expires_at"`
	DisposableTestOnly            bool        `json:"disposable_test_only"`
	ProductionTrustEnrolled       bool        `json:"production_trust_enrolled"`
	CreditAuthorized              bool        `json:"credit_authorized"`
	FinancialExecutionAuthorized  bool        `json:"financial_execution_authorized"`
	GlobalReceiptConsumed         bool        `json:"global_receipt_consumed"`
}

type WireVerdict = Verdict
