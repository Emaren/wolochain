package main

// verify-historical-transfer is an offline, NON-AUTHORIZING verification entry
// point for the one historically accepted 100-WOLO settlement transfer. It uses
// the existing CometBFT light-client/SDK replay; it cannot fetch its own root,
// inspect a live journal, access keyrings, broadcast, retry or settle any claim.
// The independent origin of an operator-supplied trust anchor and correspondence
// to a real journal obligation must be attested outside this command.
import (
 "bytes"
 "context"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "strings"
 "time"

 "github.com/emaren/wolochain/internal/chainjson"
 "github.com/emaren/wolochain/internal/satchel"
)

const acceptedEscrow100Hash = "D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699"
const acceptedEscrow100Height int64 = 1078913

// ExpectedHistoricalTransfer is provisioned independently of the untrusted
// chain response and portable transcript. The originating settlement request
// must be authenticated separately: simply writing a matching JSON file does
// not establish that request or discharge any payment obligation.
type ExpectedHistoricalTransfer struct {
 Version int `json:"version"`
 Scope string `json:"scope"`
 ChainID string `json:"chain_id"`
 TxHash string `json:"tx_hash"`
 Height int64 `json:"height"`
 Sender string `json:"sender"`
 Recipient string `json:"recipient"`
 AmountUWolo string `json:"amount_uwolo"`
 Memo string `json:"memo"`
 JournalIdentitySHA256 string `json:"journal_identity_sha256"`
}

func strictHistoricalJSON(data []byte, dst any) error {
 if len(data)==0 || !chainjson.ValidFolded(data) { return errors.New("historical_json_invalid") }
 d:=json.NewDecoder(bytes.NewReader(data))
 d.DisallowUnknownFields()
 if err:=d.Decode(dst);err!=nil{return errors.New("historical_json_invalid")}
 if _,err:=d.Token();err!=io.EOF{return errors.New("historical_json_invalid")}
 return nil
}

func verifiedHistoricalIntent(c ExpectedHistoricalTransfer) bool {
 if c.Version!=1 || c.Scope!="legacy-settlement-accepted-escrow-100" ||
  c.ChainID!=satchel.ChainID || c.TxHash!=acceptedEscrow100Hash ||
  c.Height!=acceptedEscrow100Height || c.AmountUWolo!="100000000" ||
  c.Sender=="" || c.Recipient=="" || c.Sender==c.Recipient ||
  c.Memo=="" || len(c.Memo)>256 ||
  len(c.JournalIdentitySHA256)!=64 || strings.Trim(c.JournalIdentitySHA256,"0")=="" { return false }
 b,err:=hex.DecodeString(c.JournalIdentitySHA256)
 return err==nil && len(b)==sha256.Size
}

// A successful verification is intentionally exit 3, not zero: an authenticated
// transaction is not a bank-solvency proof, independently audited trust source,
// released claim, signer permit or operator-authorized historical retry.
func verifyHistoricalTransferCommand(ctx context.Context, args []string, out, errout io.Writer) int {
 fail:=func() int {
  fmt.Fprintln(errout,"satchel: historical accepted transfer UNVERIFIABLE; no financial authority")
  return 2
 }
 if len(args)!=6 || args[0]!="--anchor" || args[2]!="--expected" || args[4]!="--proof" { return fail() }
 anchorBytes,err:=readProofFile(args[1],64<<10);if err!=nil{return fail()}
 expectedBytes,err:=readProofFile(args[3],64<<10);if err!=nil{return fail()}
 proofBytes,err:=readProofFile(args[5],satchel.MaxPortableProofBytes);if err!=nil{return fail()}
 var anchor satchel.TrustAnchor
 var expected ExpectedHistoricalTransfer
 if strictHistoricalJSON(anchorBytes,&anchor)!=nil || strictHistoricalJSON(expectedBytes,&expected)!=nil ||
  !verifiedHistoricalIntent(expected) { return fail() }
 proof,err:=satchel.DecodePortableProof(proofBytes);if err!=nil{return fail()}
 if proof.Kind!="transfer" || proof.ChainID!=satchel.ChainID || proof.TxHash!=expected.TxHash {return fail()}
 verifier,err:=satchel.NewProofVerifier(anchor);if err!=nil{return fail()}
 checkCtx,cancel:=context.WithTimeout(ctx,20*time.Second);defer cancel()
 evidence,err:=verifier.VerifyTransferProof(checkCtx,satchel.TransferIntent{
  Sender:expected.Sender,Recipient:expected.Recipient,
  AmountUWolo:expected.AmountUWolo,Memo:expected.Memo,
 },expected.TxHash,proof)
 if err!=nil || !evidence.ConsensusAuthenticated() || evidence.CreditAuthorized() {return fail()}
 obs:=evidence.Observation()
 receipt:=evidence.Receipt()
 if obs.Height!=acceptedEscrow100Height || obs.Code==nil || *obs.Code!=0 ||
  receipt.ChainID!=satchel.ChainID || receipt.TxHash!=expected.TxHash ||
  obs.TxHash!=expected.TxHash || receipt.TransferIndex!=0 {return fail()}
 expectedDigest:=sha256.Sum256(expectedBytes)
 proofDigest:=sha256.Sum256(proofBytes)
 // Explicitly distinguish the independently PROVIDED checkpoint from
 // independently VERIFIED checkpoint *provenance*: this tool cannot attest
 // who supplied the anchor or global accounting/obligation identity.
 result:=struct{
  Schema string `json:"schema"`
  Status string `json:"status"`
  ChainID string `json:"chain_id"`
  TxHash string `json:"tx_hash"`
  Height int64 `json:"height"`
  AmountUWolo string `json:"amount_uwolo"`
  ReceiptID string `json:"receipt_id"`
  ConsensusAuthenticatedAgainstProvidedAnchor bool `json:"consensus_authenticated_against_provided_anchor"`
  AnchorIndependenceProven bool `json:"anchor_independence_proven"`
  JournalIdentityIndependentlyProven bool `json:"journal_identity_independently_proven"`
  GlobalLiabilityReconciled bool `json:"global_liability_reconciled"`
  HistoricalClaim889Reconciled bool `json:"historical_claim_889_reconciled"`
  RetryAuthorized bool `json:"retry_authorized"`
  ReleaseAuthorized bool `json:"release_authorized"`
  FundsMoved bool `json:"funds_moved"`
  ExpectedSHA256 string `json:"expected_sha256"`
  ProofSHA256 string `json:"proof_sha256"`
 }{"wolo.historical.accepted-escrow-100.v1","AUTHENTICATED_NONAUTHORIZING",
  satchel.ChainID,expected.TxHash,obs.Height,expected.AmountUWolo,receipt.ID(),
  true,false,false,false,false,false,false,false,
  hex.EncodeToString(expectedDigest[:]),hex.EncodeToString(proofDigest[:])}
 if json.NewEncoder(out).Encode(result)!=nil{return fail()}
 return 3
}
