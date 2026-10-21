package satchelservice

// A NON-ACTIVATING reserve-review primitive. It bridges existing native,
// authenticated Cosmos bank evidence with *separate*, signed and bounded
// financial-liability assertions. It cannot establish completeness of a source
// inventory or independence of reviewers. It never changes custody capability,
// execution permits, service health, database state, signer access or funds.
import (
 "bytes"
 "crypto/ed25519"
 "encoding/base64"
 "encoding/json"
 "errors"
 "math/big"
 "regexp"
 "strings"
 "time"

 "github.com/emaren/wolochain/internal/satchel"
)

const reserveReviewScope = "aoe2war/satchel/proof-bound-reserve-review/v1"
const maxReserveReviewSeconds int64 = 120

var (
 reserveDecimal = regexp.MustCompile(`^(0|[1-9][0-9]{0,38})$`)
 reserveDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)
 reserveBlockHashPattern = regexp.MustCompile(`^[A-Fa-f0-9]{64}$`)
 reserveBound = new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1),128),big.NewInt(1))
)

// SignedReserveReview is a financial-reviewer proposal, not the true current
// balance or global liability itself. The operator must provision two DISTINCT
// reviewer public keys from independently trusted sources. Evidence must be
// generated from the exact audited, immutable accounts and journal state,
// including all unknown liabilities, not from a frontend or this JSON payload.
type SignedReserveReview struct {
 Version int `json:"version"`
 Scope string `json:"scope"`
 ChainID string `json:"chain_id"`
 Denom string `json:"denom"`
 Vault string `json:"vault"`
 StateHeight int64 `json:"state_height"`
 CommitBlockHash string `json:"commit_block_hash"`
 ObservedBankUWolo string `json:"observed_bank_uwolo"`
 ConfirmedLiabilitiesUWolo string `json:"confirmed_liabilities_uwolo"`
 UncertainMaxLiabilitiesUWolo string `json:"uncertain_max_liabilities_uwolo"`
 GasReserveUWolo string `json:"gas_reserve_uwolo"`
 UnencumberedMinimumUWolo string `json:"unencumbered_minimum_uwolo"`
 LiabilityInventorySHA256 string `json:"liability_inventory_sha256"`
 JournalSnapshotSHA256 string `json:"journal_snapshot_sha256"`
 NonOverlapWitnessSHA256 string `json:"nonoverlap_witness_sha256"`
 BuildSHA256 string `json:"build_sha256"`
 ConfigSHA256 string `json:"config_sha256"`
 PermitSHA256 string `json:"permit_sha256"`
 AllObligationsCovered bool `json:"all_obligations_covered"`
 UnknownClaimsReserved bool `json:"unknown_claims_reserved"`
 DedicatedVaultIsolated bool `json:"dedicated_vault_isolated"`
 IssuedAt int64 `json:"issued_at"`
 ExpiresAt int64 `json:"expires_at"`
 AccountingReviewerSignature string `json:"accounting_reviewer_signature"`
 CustodyReviewerSignature string `json:"custody_reviewer_signature"`
}

// ReserveReviewAuthority comes ONLY from protected operator configuration,
// never from the SignedReserveReview or bank response.
type ReserveReviewAuthority struct {
 AccountingReviewerKey ed25519.PublicKey
 CustodyReviewerKey ed25519.PublicKey
 // Explicitly separate financial reviewers from execution, wager and owner
 // withdrawal approval powers. These role keys are provisioned independently
 // from protected operator config, not copied from the review statement.
 ExecutionAuthorityKey ed25519.PublicKey
 WagerApprovalKey ed25519.PublicKey
 WithdrawalApprovalKey ed25519.PublicKey
 ExpectedVault string
 ExpectedBuildSHA256 string
 ExpectedConfigSHA256 string
 ExpectedPermitSHA256 string
}

// QualifiedReserveReview is strictly source-level and read-only. It is NOT a
// custody-availability, signer-execution, asset-transfer or release permit.
type QualifiedReserveReview struct {
 Sufficient bool
 ObservedBankUWolo string
 ConservativeCommittedUWolo string
 UncommittedUWolo string
 StateHeight int64
 ExpiresAt time.Time
}

func reserveUnsignedMessage(r SignedReserveReview) []byte {
 b,_:=json.Marshal([]any{reserveReviewScope,r.Version,r.Scope,r.ChainID,r.Denom,r.Vault,
  r.StateHeight,r.CommitBlockHash,r.ObservedBankUWolo,
  r.ConfirmedLiabilitiesUWolo,r.UncertainMaxLiabilitiesUWolo,
  r.GasReserveUWolo,r.UnencumberedMinimumUWolo,
  r.LiabilityInventorySHA256,r.JournalSnapshotSHA256,r.NonOverlapWitnessSHA256,
  r.BuildSHA256,r.ConfigSHA256,r.PermitSHA256,
  r.AllObligationsCovered,r.UnknownClaimsReserved,r.DedicatedVaultIsolated,
  r.IssuedAt,r.ExpiresAt})
 return b
}

func validReserveDigest(v string) bool {
 return reserveDigest.MatchString(v) && strings.Trim(v,"0")!=""
}
func reserveUint(v string) (*big.Int,bool) {
 if !reserveDecimal.MatchString(v) {return nil,false}
 n,ok:=new(big.Int).SetString(v,10)
 return n,ok && n.Sign()>=0 && n.Cmp(reserveBound)<=0
}
func validReviewSignature(encoded string, pub ed25519.PublicKey, message []byte) bool {
 if len(pub)!=ed25519.PublicKeySize || len(encoded)>100 {
  return false
 }
 sig,err:=base64.StdEncoding.Strict().DecodeString(encoded)
 return err==nil && len(sig)==ed25519.SignatureSize &&
  base64.StdEncoding.EncodeToString(sig)==encoded && ed25519.Verify(pub,message,sig)
}
func validReviewAuthority(a ReserveReviewAuthority) bool {
 keys:=[]ed25519.PublicKey{
  a.AccountingReviewerKey,a.CustodyReviewerKey,
  a.ExecutionAuthorityKey,a.WagerApprovalKey,a.WithdrawalApprovalKey,
 }
 for i,key:=range keys {
  if len(key)!=ed25519.PublicKeySize {return false}
  for j:=0;j<i;j++ {if bytes.Equal(key,keys[j]) {return false}}
 }
 return a.ExpectedVault!="" &&
  validReserveDigest(a.ExpectedBuildSHA256) &&
  validReserveDigest(a.ExpectedConfigSHA256) &&
  validReserveDigest(a.ExpectedPermitSHA256)
}

type reviewedBankObservation struct {
 vault,balance,commitHash string
 stateHeight int64
 current bool
 expiresAt time.Time
}

// EvaluateProofBoundReserveReview accepts ONLY the genuine native,
// independently anchored satchel bank evidence produced by VerifyBankProof.
// It requires the state committed at HEAD H+1, not a historic account balance,
// and it never constructs or promotes a custody Capability object.
func EvaluateProofBoundReserveReview(
 now time.Time, evidence satchel.AuthenticatedBankEvidence,
 review SignedReserveReview, authority ReserveReviewAuthority,
) (QualifiedReserveReview,error) {
 if !evidence.CurrentAt(now) || evidence.CreditAuthorized() ||
  evidence.ChainID()!=satchel.ChainID || evidence.Denom()!=satchel.Denom {
  return QualifiedReserveReview{},errors.New("reserve_bank_proof_not_current")
 }
 return evaluateBoundReserveReview(now,review,authority,reviewedBankObservation{
  vault:evidence.VaultAddress(),balance:evidence.BalanceUWolo(),
  commitHash:evidence.BlockHash(),stateHeight:evidence.Height(),
  current:true,expiresAt:evidence.ExpiresAt(),
 })
}

// The internal pure checker is isolated for adversarial arithmetic and
// signature tests. Supplying its arguments in a test does NOT emulate the
// exported function's native cryptographic bank-verification boundary.
func evaluateBoundReserveReview(
 now time.Time,review SignedReserveReview,authority ReserveReviewAuthority,
 observed reviewedBankObservation,
) (QualifiedReserveReview,error) {
 refuse:=func() (QualifiedReserveReview,error) {
  return QualifiedReserveReview{},errors.New("reserve_review_incomplete_or_untrusted")
 }
 if now.IsZero() || !observed.current || !now.Before(observed.expiresAt) ||
  !validReviewAuthority(authority) ||
  review.Version!=1 || review.Scope!=reserveReviewScope ||
  review.ChainID!=satchel.ChainID || review.Denom!=satchel.Denom ||
  review.Vault!=authority.ExpectedVault || review.Vault!=observed.vault ||
  review.StateHeight<=0 || review.StateHeight!=observed.stateHeight ||
  !strings.EqualFold(review.CommitBlockHash,observed.commitHash) ||
  len(review.CommitBlockHash)!=64 ||
  !reserveBlockHashPattern.MatchString(review.CommitBlockHash) ||
  strings.Trim(review.CommitBlockHash,"0")=="" ||
  review.ObservedBankUWolo!=observed.balance ||
  review.BuildSHA256!=authority.ExpectedBuildSHA256 ||
  review.ConfigSHA256!=authority.ExpectedConfigSHA256 ||
  review.PermitSHA256!=authority.ExpectedPermitSHA256 ||
  !validReserveDigest(review.LiabilityInventorySHA256) ||
  !validReserveDigest(review.JournalSnapshotSHA256) ||
  !validReserveDigest(review.NonOverlapWitnessSHA256) ||
  !review.AllObligationsCovered || !review.UnknownClaimsReserved ||
  !review.DedicatedVaultIsolated || review.IssuedAt<=0 ||
  review.ExpiresAt<=review.IssuedAt ||
  review.ExpiresAt-review.IssuedAt>maxReserveReviewSeconds ||
  now.Unix()<review.IssuedAt-5 || now.Unix()>=review.ExpiresAt ||
  time.Unix(review.ExpiresAt,0).After(observed.expiresAt) {
  return refuse()
 }
 balance,bOK:=reserveUint(review.ObservedBankUWolo)
 covered,cOK:=reserveUint(review.ConfirmedLiabilitiesUWolo)
 unknown,uOK:=reserveUint(review.UncertainMaxLiabilitiesUWolo)
 gas,gOK:=reserveUint(review.GasReserveUWolo)
 floor,fOK:=reserveUint(review.UnencumberedMinimumUWolo)
 if !bOK || !cOK || !uOK || !gOK || !fOK || gas.Sign()<=0 ||
  floor.Sign()<=0 || review.UncertainMaxLiabilitiesUWolo=="0" {
  // Until the UNKNOWN historical exposure is independently resolved, an
  // explicit nonzero upper-bound reservation is mandatory. Zero is a
  // different future protocol, not an implicit waiver of claim #889.
  return refuse()
 }
 message:=reserveUnsignedMessage(review)
 if !validReviewSignature(review.AccountingReviewerSignature,authority.AccountingReviewerKey,message) ||
  !validReviewSignature(review.CustodyReviewerSignature,authority.CustodyReviewerKey,message) {
  return refuse()
 }
 committed:=new(big.Int).Add(covered,unknown)
 committed.Add(committed,gas)
 committed.Add(committed,floor)
 if committed.Cmp(reserveBound)>0 || balance.Cmp(committed)<0 {return refuse()}
 free:=new(big.Int).Sub(balance,committed)
 return QualifiedReserveReview{
  Sufficient:true,ObservedBankUWolo:balance.String(),
  ConservativeCommittedUWolo:committed.String(),
  UncommittedUWolo:free.String(),StateHeight:review.StateHeight,
  ExpiresAt:time.Unix(review.ExpiresAt,0),
 },nil
}

// No marshalable export that claims actual activation is provided. A caller
// still requires exact deployment, operator permits, replay/ledger fencing,
// actual source provenance, owner consent, and the full financial release gate.
func (r QualifiedReserveReview) CustodyCapability() string {return "UNAVAILABLE"}

