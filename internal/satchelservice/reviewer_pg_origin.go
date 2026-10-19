package satchelservice

// Independently queried PostgreSQL original HD wager evidence. The reviewer
// needs a distinct SELECT-ONLY database account, NOT the web application's
// DB credential or bearer-authenticated HTTP snapshot. This adapter is
// deliberately incomplete: it only implements OriginalHold. Market/Watcher,
// Keplr signature and authenticated bank/liability census methods HOLD until
// their independently governed adapters are wired and proven together.
import (
 "context"
 "database/sql"
 "errors"
 "regexp"
 "strconv"
 "time"
)

var reviewerPGRole = regexp.MustCompile(`^satchel_reviewer_[a-z0-9_]{1,48}$`)

// SQL strings are static and positional; a consumer-supplied operation ID
// is never SQL, a table name, a financial amount or an authorization.
const reviewerPGIdentityQuery = `
SELECT current_user,
       current_setting('transaction_read_only'),
       COALESCE((
         SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls
         FROM pg_roles WHERE rolname=current_user
       ),true),
       has_table_privilege(current_user,'war_satchel_wager_authorizations','INSERT') OR
       has_table_privilege(current_user,'war_satchel_wager_authorizations','UPDATE') OR
       has_table_privilege(current_user,'war_satchel_wager_authorizations','DELETE') OR
       has_table_privilege(current_user,'war_satchel_funded_balances','UPDATE') OR
       has_table_privilege(current_user,'war_satchel_wager_approvals','INSERT') OR
       has_table_privilege(current_user,'bet_auto_executions','UPDATE')
`

const reviewerPGOriginalQuery = `
SELECT a.snapshot_json::text,a.operation_id,a.reservation_id,a.owner_user_id,
       a.reservation_digest,a.ledger_revision,a.consent_digest,
       r.status,r.ticket_request_id,r.amount_uwolo::text,r.ticket_id,
       e.status,e.attempt_count,e.reservation_id,e.game_identity_key,
       e.proposition_hash,e.preset_id,e.preset_version,e.created_at,
       p.enabled,p.self_only,p.version,
       u.uid,u.wallet_address,
       t.id,t.status,t.source,t.wallet_provider,t.wallet_address,
       t.stake_tx_hash,t.total_amount_wolo,
       b.reserved_uwolo::text,
       EXISTS (SELECT 1 FROM war_satchel_wager_approvals ap
         WHERE ap.operation_id=a.operation_id),
       EXISTS (SELECT 1 FROM war_satchel_wager_broadcasts br
         WHERE br.operation_id=a.operation_id)
FROM war_satchel_wager_authorizations a
JOIN war_satchel_funded_reservations r
 ON r.id=a.reservation_id AND r.owner_user_id=a.owner_user_id
JOIN bet_auto_executions e ON e.id=r.execution_id
JOIN bet_auto_presets p ON p.id=e.preset_id AND p.user_id=a.owner_user_id
JOIN users u ON u.id=a.owner_user_id
JOIN bet_stake_tickets t
 ON t.user_id=a.owner_user_id AND t.client_request_id=r.ticket_request_id
JOIN war_satchel_funded_balances b ON b.owner_user_id=a.owner_user_id
WHERE a.operation_id=$1
`

type ReviewerPGOriginalRow struct {
 SnapshotJSON string
 OperationID, ReservationID string
 OwnerUserID int64
 ReservationDigest, LedgerRevision, ConsentDigest string
 ReservationStatus, TicketRequestID, ReservationAmount string
 ReservationTicketID sql.NullInt64
 ExecutionStatus string
 AttemptCount int64
 ExecutionReservationID, GameIdentityKey, PropositionHash string
 ExecutionPresetID, ExecutionPresetVersion int64
 ExecutionCreatedAt time.Time
 PlanEnabled, PlanSelfOnly bool
 PlanVersion int64
 UserUID string
 UserWallet sql.NullString
 TicketID int64
 TicketStatus, TicketSource string
 TicketProvider sql.NullString
 TicketWallet string
 TicketHash sql.NullString
 TicketTotalWolo int64
 BalanceReserved string
 AlreadyApproved, AlreadyBroadcast bool
}
func (r *ReviewerPGOriginalRow) scan(row *sql.Row) error {
 return row.Scan(
  &r.SnapshotJSON,&r.OperationID,&r.ReservationID,&r.OwnerUserID,
  &r.ReservationDigest,&r.LedgerRevision,&r.ConsentDigest,
  &r.ReservationStatus,&r.TicketRequestID,&r.ReservationAmount,&r.ReservationTicketID,
  &r.ExecutionStatus,&r.AttemptCount,&r.ExecutionReservationID,&r.GameIdentityKey,
  &r.PropositionHash,&r.ExecutionPresetID,&r.ExecutionPresetVersion,&r.ExecutionCreatedAt,
  &r.PlanEnabled,&r.PlanSelfOnly,&r.PlanVersion,&r.UserUID,&r.UserWallet,
  &r.TicketID,&r.TicketStatus,&r.TicketSource,&r.TicketProvider,&r.TicketWallet,
  &r.TicketHash,&r.TicketTotalWolo,&r.BalanceReserved,&r.AlreadyApproved,&r.AlreadyBroadcast)
}
func (r ReviewerPGOriginalRow)validate(now time.Time,fee string,vault string,escrow string)(WagerReservation,error){
 held:=func()(WagerReservation,error){return WagerReservation{},ErrReviewerHeld}
 if !wagerIDs.MatchString(r.OperationID)||r.OwnerUserID<1||
  r.ReservationStatus!="reserved"||r.TicketRequestID!=r.OperationID||
  r.ExecutionStatus!="funded_reserved"||r.AttemptCount!=1||
  r.ExecutionReservationID!=r.ReservationID||
  !r.PlanEnabled||!r.PlanSelfOnly||
  r.PlanVersion!=r.ExecutionPresetVersion||
  r.TicketStatus!="awaiting_signature"||r.TicketSource!="auto"||
  !r.TicketProvider.Valid||r.TicketProvider.String!="satchel-vault"||
  r.TicketHash.Valid||r.AlreadyBroadcast||r.TicketID<1||
  r.TicketTotalWolo<1||r.TicketTotalWolo>1000||
  r.ReservationTicketID.Valid && r.ReservationTicketID.Int64!=r.TicketID||
  !r.UserWallet.Valid||r.UserWallet.String==""||
  r.ExecutionCreatedAt.After(now)||
  now.Sub(r.ExecutionCreatedAt)>4*time.Minute||
  !reviewerUnsignedDecimal(r.ReservationAmount,false,1000000000)||
  !reviewerUnsignedDecimal(r.BalanceReserved,true,9223372036854775807)||
  !reviewerUnsignedDecimal(fee,false,1000000) {
  return held()
 }
 evidence,e:=VerifyReviewerHDOrigin([]byte(r.SnapshotJSON),ReviewerHDOriginColumns{
  OperationID:r.OperationID,ReservationID:r.ReservationID,OwnerUserID:r.OwnerUserID,
  ReservationDigest:r.ReservationDigest,LedgerRevision:r.LedgerRevision,
  ConsentDigest:r.ConsentDigest})
 if e!=nil||evidence.OwnerUID!=r.UserUID||evidence.OwnerWallet!=r.UserWallet.String||
  evidence.Vault!=vault||evidence.Recipient!=escrow||evidence.Vault!=r.TicketWallet||
  evidence.AmountUWolo!=r.ReservationAmount||
  evidence.TicketID!=r.TicketID||
  evidence.GameIdentityKey!=r.GameIdentityKey||
  evidence.PropositionHash!=r.PropositionHash||
  evidence.PresetID!=r.ExecutionPresetID||
  evidence.PresetVersion!=r.ExecutionPresetVersion||
  evidence.TicketID!=r.TicketID {
  return held()
 }
 amount,_:=strconv.ParseUint(r.ReservationAmount,10,64)
 reserved,_:=strconv.ParseUint(r.BalanceReserved,10,64)
 if reserved<amount || uint64(r.TicketTotalWolo)*1000000!=amount{return held()}
 // A fresh, exact original row still does NOT grant bank or fee authority.
 // The separately authenticated global-census adapter is a hard prerequisite.
 return WagerReservation{
  Version:1,OperationID:r.OperationID,OwnerID:evidence.OwnerUID,
  Vault:vault,Recipient:escrow,AmountUWolo:r.ReservationAmount,
  Memo:evidence.Memo,ReservationDigest:r.ReservationDigest,
  LedgerRevision:r.LedgerRevision,ConsentDigest:r.ConsentDigest,
  FeeUWolo:fee,
 },nil
}

type ReviewerReadOnlyPGSource struct {
 db *sql.DB
 expectedRole,fee,vault,escrow string
 now func()time.Time
}
func NewReviewerReadOnlyPGSource(db *sql.DB,role,fee,vault,escrow string)(*ReviewerReadOnlyPGSource,error){
 if db==nil||!reviewerPGRole.MatchString(role)||
  !reviewerUnsignedDecimal(fee,false,1000000)||
  !validAddress(vault)||!validAddress(escrow)||vault==escrow{
  return nil,ErrReviewerHeld
 }
 return &ReviewerReadOnlyPGSource{db:db,expectedRole:role,fee:fee,vault:vault,escrow:escrow,now:time.Now},nil
}
// This is READ-ONLY PostgreSQL access from a separately governed OS process.
// BEGIN READ ONLY is necessary but NOT sufficient: the connected principal
// must also lack INSERT/UPDATE/DELETE and superuser/role-mgmt permissions.
func (s *ReviewerReadOnlyPGSource) OriginalHold(ctx context.Context,id string)(WagerReservation,error){
 if s==nil||!wagerIDs.MatchString(id)||ctx.Err()!=nil{
  return WagerReservation{},ErrReviewerHeld
 }
 ctx,cancel:=context.WithTimeout(ctx,2*time.Second)
 defer cancel()
 tx,e:=s.db.BeginTx(ctx,&sql.TxOptions{Isolation:sql.LevelRepeatableRead,ReadOnly:true})
 if e!=nil{return WagerReservation{},ErrReviewerHeld}
 defer func(){_ = tx.Rollback()}()
 var role,readonly string
 var privileged,hasWrite bool
 if tx.QueryRowContext(ctx,reviewerPGIdentityQuery).Scan(&role,&readonly,&privileged,&hasWrite)!=nil||
  role!=s.expectedRole||readonly!="on"||privileged||hasWrite{
  return WagerReservation{},ErrReviewerHeld
 }
 var row ReviewerPGOriginalRow
 // Row values are original DB columns, never client-declared origin receipts.
 if row.scan(tx.QueryRowContext(ctx,reviewerPGOriginalQuery,id))!=nil{return WagerReservation{},ErrReviewerHeld}
 original,e:=row.validate(s.now(),s.fee,s.vault,s.escrow)
 if e!=nil{return WagerReservation{},ErrReviewerHeld}
 if tx.Commit()!=nil{return WagerReservation{},ErrReviewerHeld}
 return original,nil
}

// The following remain disabled even though the source supports OriginalHold.
// A separate read-only Keplr ADR36 verification adapter, trusted Watcher
// identity reader, and globally complete Comet bank+gas census are required.
// Plugging this incomplete adapter into 8095 CANNOT cause an approval.
func (*ReviewerReadOnlyPGSource) VerifyOwnerMandate(context.Context,WagerReservation)error{
 return ErrReviewerHeld
}
func (*ReviewerReadOnlyPGSource) VerifyWatcherMarket(context.Context,WagerReservation)error{
 return ErrReviewerHeld
}
func (*ReviewerReadOnlyPGSource) AuthenticatedFeeCensus(context.Context,WagerReservation)(ReviewerFeeCensus,error){
 return ReviewerFeeCensus{},ErrReviewerHeld
}
var _ ReviewerEvidenceSource = (*ReviewerReadOnlyPGSource)(nil)
var _ = errors.Is
