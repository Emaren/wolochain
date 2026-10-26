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

// All three exact input byte strings are needed to reproduce an offline
// historical review. Their digests assert no independent checkpoint provenance.
type historicalProofInputBindings struct {
	AnchorSHA256      string `json:"anchor_sha256"`
	ExpectedSHA256    string `json:"expected_sha256"`
	ProofSHA256       string `json:"proof_sha256"`
	HistoricalAsOfUTC string `json:"historical_as_of_utc"`
}

func bindHistoricalProofInputs(anchor, expected, proof []byte, asOf string) historicalProofInputBindings {
	a, e, p := sha256.Sum256(anchor), sha256.Sum256(expected), sha256.Sum256(proof)
	return historicalProofInputBindings{hex.EncodeToString(a[:]), hex.EncodeToString(e[:]), hex.EncodeToString(p[:]), asOf}
}


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
 // Untrusted review time, operator provisioned separately from the proof; NOT current spendability.
 HistoricalAsOfUTC string `json:"historical_as_of_utc"`
}

func strictHistoricalJSON(data []byte, dst any) error {
 if len(bytes.TrimSpace(data))==0 || bytes.TrimSpace(data)[0]!='{' || !chainjson.ValidFolded(data) { return errors.New("historical_json_invalid") }
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
  len(c.JournalIdentitySHA256)!=64 || strings.Trim(c.JournalIdentitySHA256,"0")=="" ||
  len(c.HistoricalAsOfUTC)!=20 || !strings.HasSuffix(c.HistoricalAsOfUTC,"Z") { return false }
 b,err:=hex.DecodeString(c.JournalIdentitySHA256)
 asOf,timeErr:=time.Parse("2006-01-02T15:04:05Z",c.HistoricalAsOfUTC)
 return err==nil && len(b)==sha256.Size && timeErr==nil &&
  asOf.Year()>=2000 && !asOf.After(time.Now().Add(5*time.Second))
}

// historicalPrincipalEffectMatches applies to this ONE pinned legacy accepted
// payout only. The signed transaction decoder, fee-collector identity, exact
// MsgSend, response parity and CometBFT commitments have already been checked
// by VerifyTransferProof. The original receipt contains its signed fee effect
// at ordinal 0 and its exactly 100-WOLO principal at ordinal 1.
// Never reuse this rule for new Satchel deposits or ledger credit admission.
func historicalPrincipalEffectMatches(obs satchel.Observation, receipt satchel.ReceiptCandidate, expected ExpectedHistoricalTransfer) bool {
 if !verifiedHistoricalIntent(expected) ||
  obs.ChainID!=satchel.ChainID || obs.TxHash!=expected.TxHash ||
  obs.Height!=acceptedEscrow100Height || obs.Code==nil || *obs.Code!=0 ||
  receipt.ChainID!=satchel.ChainID || receipt.TxHash!=expected.TxHash ||
  receipt.TransferIndex!=1 || obs.TransferIndex==nil || *obs.TransferIndex!=1 ||
  len(obs.Transfers)!=2 {
  return false
 }
 principal:=satchel.Transfer{
  Sender:expected.Sender,Recipient:expected.Recipient,
  Denom:satchel.Denom,Amount:expected.AmountUWolo,
 }
 // 250000 uwolo = the 0.25 WOLO SDK fee observed in the original tx.
 // The trusted outgoing reader independently proves that this is the exact
 // signed fee paid to the SDK fee_collector, not an unrelated send.
 fee:=obs.Transfers[0]
 return obs.Transfers[1]==principal &&
  fee.Sender==expected.Sender && fee.Recipient!="" &&
  fee.Recipient!=expected.Recipient &&
  fee.Denom==satchel.Denom && fee.Amount=="250000"
}

// A successful verification is intentionally exit 3, not zero: an authenticated
// transaction is not a bank-solvency proof, independently audited trust source,
// released claim, signer permit or operator-authorized historical retry.
func verifyHistoricalTransferCommand(ctx context.Context, args []string, out, errout io.Writer) int {
 fail:=func() int {
  fmt.Fprintln(errout,"satchel: historical accepted transfer UNVERIFIABLE; no financial authority")
  return 2
 }
 if ctx==nil || ctx.Err()!=nil || len(args)!=6 || args[0]!="--anchor" || args[2]!="--expected" || args[4]!="--proof" { return fail() }
 anchorBytes,err:=readProofFile(args[1],64<<10);if err!=nil{return fail()}
 expectedBytes,err:=readProofFile(args[3],64<<10);if err!=nil{return fail()}
 proofBytes,err:=readProofFile(args[5],satchel.MaxPortableProofBytes);if err!=nil{return fail()}
 var anchor satchel.TrustAnchor
 var expected ExpectedHistoricalTransfer
 if strictHistoricalJSON(anchorBytes,&anchor)!=nil || strictHistoricalJSON(expectedBytes,&expected)!=nil ||
  !verifiedHistoricalIntent(expected) { return fail() }
 proof,err:=satchel.DecodePortableProof(proofBytes);if err!=nil{return fail()}
 if proof.Kind!="transfer" || proof.ChainID!=satchel.ChainID || proof.TxHash!=expected.TxHash {return fail()}
 asOf,err:=time.Parse("2006-01-02T15:04:05Z",expected.HistoricalAsOfUTC);if err!=nil{return fail()}
 checkCtx,cancel:=context.WithTimeout(ctx,20*time.Second);defer cancel()
 evidence,err:=satchel.VerifyArchivedTransferProof(checkCtx,anchor,asOf,satchel.TransferIntent{
  Sender:expected.Sender,Recipient:expected.Recipient,
  AmountUWolo:expected.AmountUWolo,Memo:expected.Memo,
 },expected.TxHash,proof)
 if err!=nil || !evidence.ConsensusAuthenticatedAgainstProvidedAnchor() || evidence.CreditAuthorized() {return fail()}
 obs:=evidence.Observation()
 receipt:=evidence.Receipt()
 if !historicalPrincipalEffectMatches(obs,receipt,expected) {return fail()}
 bindings:=bindHistoricalProofInputs(anchorBytes,expectedBytes,proofBytes,expected.HistoricalAsOfUTC)
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
  historicalProofInputBindings
 }{"wolo.historical.accepted-escrow-100.v1","AUTHENTICATED_NONAUTHORIZING",
  satchel.ChainID,expected.TxHash,obs.Height,expected.AmountUWolo,receipt.ID(),
  true,false,false,false,false,false,false,false,
  bindings}
 if json.NewEncoder(out).Encode(result)!=nil{return fail()}
 return 3
}
