package satchelservice

// A strict READ-ONLY SQL market observation. Database values alone are NOT
// authenticated Watcher / Steam evidence: InspectWatcherMarket can only
// produce a bounded diagnostic candidate. VerifyWatcherMarket must remain
// ErrReviewerHeld until a separate pinned replay/Watcher authority verifies it.
import (
 "context"
 "database/sql"
 "strings"
 "time"
)
const reviewerPGMarketQuery = `
SELECT e.source_evidence::text,e.status,e.created_at,e.game_identity_key,
       e.winner_market_id,e.selected_side,e.proposition_hash,
       m.status,m.integrity_status,m.market_type,m.proposition_hash,
       m.scheduled_match_id,m.linked_session_key,m.created_at,
       m.close_at,m.phase_opens_at,m.phase_closes_at,
       m.winner_side,m.settled_at,m.voided_at,m.refund_status,
       m.settlement_executed_at,m.linked_game_stats_id,m.late_final_game_stats_id,
       c.signed_at
FROM public.war_satchel_wager_authorizations a
JOIN public.war_satchel_funded_reservations r ON r.id=a.reservation_id
JOIN public.bet_auto_executions e ON e.id=r.execution_id
JOIN public.bet_markets m ON m.id=e.winner_market_id
JOIN public.war_satchel_auto_spend_consents c
 ON c.id::text=a.snapshot_json->>'consentId' AND c.owner_user_id=a.owner_user_id
WHERE a.operation_id=$1
`
type ReviewerPGMarketRow struct{
 SourceEvidence sql.NullString
 ExecutionStatus string
 ExecutionCreated time.Time
 ExecutionGameKey string
 WinnerMarketID int64
 SelectedSide sql.NullString
 ExecutionProposition string
 MarketStatus,MarketIntegrity,MarketType string
 MarketProposition sql.NullString
 ScheduledMatchID sql.NullInt64
 LinkedSession sql.NullString
 MarketCreated time.Time
 CloseAt,PhaseOpensAt,PhaseClosesAt sql.NullTime
 WinnerSide sql.NullString
 SettledAt,VoidedAt sql.NullTime
 RefundStatus sql.NullString
 SettlementExecutedAt sql.NullTime
 LinkedGameStats, LateFinalGameStats sql.NullInt64
 OwnerSignedAt sql.NullTime
}
func (x *ReviewerPGMarketRow)scan(row *sql.Row)error{
 return row.Scan(&x.SourceEvidence,&x.ExecutionStatus,&x.ExecutionCreated,
  &x.ExecutionGameKey,&x.WinnerMarketID,&x.SelectedSide,&x.ExecutionProposition,
  &x.MarketStatus,&x.MarketIntegrity,&x.MarketType,&x.MarketProposition,
  &x.ScheduledMatchID,&x.LinkedSession,&x.MarketCreated,
  &x.CloseAt,&x.PhaseOpensAt,&x.PhaseClosesAt,&x.WinnerSide,
  &x.SettledAt,&x.VoidedAt,&x.RefundStatus,
  &x.SettlementExecutedAt,&x.LinkedGameStats,&x.LateFinalGameStats,
  &x.OwnerSignedAt)
}
type ReviewerWatcherCandidate struct {
 OriginalOperationID string
 OwnerUID string
 GameIdentityKey string
 MarketID int64
 PropositionHash string
 SelectedSide string
 LinkedSession string
 CreatedAt time.Time
 // NEVER include a boolean that implies authenticated or spend authority.
}
func (x ReviewerPGMarketRow)validate(now time.Time,original ReviewerHDOriginResult)(ReviewerWatcherCandidate,error){
 held:=func()(ReviewerWatcherCandidate,error){return ReviewerWatcherCandidate{},ErrReviewerHeld}
 if !x.SourceEvidence.Valid||x.ExecutionStatus!="funded_reserved"||
  !x.OwnerSignedAt.Valid||!x.SelectedSide.Valid||
  (x.SelectedSide.String!="left"&&x.SelectedSide.String!="right")||
  x.ExecutionGameKey!=original.GameIdentityKey||
  x.ExecutionProposition!=original.PropositionHash||
  !reviewerHexDigest.MatchString(x.ExecutionProposition)||
  x.MarketStatus!="live"||x.MarketIntegrity!="verified"||
  x.MarketType!="winner"||!x.MarketProposition.Valid||
  x.MarketProposition.String!=original.PropositionHash||
  x.WinnerMarketID<1||x.ScheduledMatchID.Valid||
  !x.LinkedSession.Valid||strings.TrimSpace(x.LinkedSession.String)==""||
  x.WinnerSide.Valid||x.SettledAt.Valid||x.VoidedAt.Valid||
  x.RefundStatus.Valid||x.SettlementExecutedAt.Valid||
  x.LinkedGameStats.Valid||x.LateFinalGameStats.Valid||
  !x.ExecutionCreated.After(x.OwnerSignedAt.Time)||
  x.ExecutionCreated.After(now)||now.Sub(x.ExecutionCreated)>4*time.Minute||
  x.MarketCreated.Before(x.OwnerSignedAt.Time)||
  x.MarketCreated.After(x.ExecutionCreated)||
  x.CloseAt.Valid&&!x.CloseAt.Time.After(now)||
  x.PhaseClosesAt.Valid&&!x.PhaseClosesAt.Time.After(now)||
  x.PhaseOpensAt.Valid&&x.PhaseOpensAt.Time.After(now) {
  return held()
 }
 // Original selected side and winner proposition must agree with the
 // canonical immutable stake leg, not merely the mutable market row.
 matched:=0
 for _,leg:=range original.Legs{
  if leg.MarketID==x.WinnerMarketID{
   matched++
   if leg.Side!=x.SelectedSide.String||leg.PropositionHash!=x.ExecutionProposition{return held()}
  }
 }
 if matched!=1{return held()}
 raw,e:=reviewerStrictJSON([]byte(x.SourceEvidence.String))
 if e!=nil{return held()}
 evidence,ok:=raw.(map[string]any)
 if !ok||!reviewerRecord(evidence,[]string{
  "mode","exactSteamRosterMatch","exactUploaderUidMatch","marketIntegrityStatus",
  "ownerUid","propositionHash","canonicalSessionKey",
 }){return held()}
 if evidence["mode"]!="shadow"||
  evidence["exactSteamRosterMatch"]!=true||
  evidence["exactUploaderUidMatch"]!=true||
  evidence["marketIntegrityStatus"]!="verified"||
  evidence["ownerUid"]!=original.OwnerUID||
  evidence["propositionHash"]!=original.PropositionHash||
  evidence["canonicalSessionKey"]!=original.GameIdentityKey{return held()}
 return ReviewerWatcherCandidate{OriginalOperationID:original.OperationID,
  OwnerUID:original.OwnerUID,GameIdentityKey:original.GameIdentityKey,
  MarketID:x.WinnerMarketID,PropositionHash:original.PropositionHash,
  SelectedSide:x.SelectedSide.String,LinkedSession:x.LinkedSession.String,
  CreatedAt:x.ExecutionCreated},nil
}

// InspectWatcherMarket reads and bounds the CURRENT market state, within
// a separately role-checked read-only SQL snapshot. This is NOT an
// independent replay/watcher cryptographic attestation.
func (s *ReviewerReadOnlyPGSource)InspectWatcherMarket(ctx context.Context,input WagerReservation)(ReviewerWatcherCandidate,error){
 if s==nil||s.db==nil||ctx==nil||!wagerIDs.MatchString(input.OperationID){return ReviewerWatcherCandidate{},ErrReviewerHeld}
 ctx,cancel:=context.WithTimeout(ctx,2*time.Second);defer cancel()
 tx,e:=s.db.BeginTx(ctx,&sql.TxOptions{Isolation:sql.LevelRepeatableRead,ReadOnly:true})
 if e!=nil{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 defer func(){_ = tx.Rollback()}()
 var user,readonly string
 var priv,write bool
 if tx.QueryRowContext(ctx,reviewerPGIdentityQuery).Scan(&user,&readonly,&priv,&write)!=nil||
  user!=s.expectedRole||readonly!="on"||priv||write{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 var row ReviewerPGOriginalRow
 if row.scan(tx.QueryRowContext(ctx,reviewerPGOriginalQuery,input.OperationID))!=nil{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 head,e:=row.validate(s.now(),s.fee,s.vault,s.escrow)
 if e!=nil||head.OwnerID!=input.OwnerID||head.OperationID!=input.OperationID||
  head.ReservationDigest!=input.ReservationDigest||head.LedgerRevision!=input.LedgerRevision||
  head.ConsentDigest!=input.ConsentDigest||head.AmountUWolo!=input.AmountUWolo{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 orig,e:=VerifyReviewerHDOrigin([]byte(row.SnapshotJSON),ReviewerHDOriginColumns{
  OperationID:row.OperationID,ReservationID:row.ReservationID,OwnerUserID:row.OwnerUserID,
  ReservationDigest:row.ReservationDigest,LedgerRevision:row.LedgerRevision,ConsentDigest:row.ConsentDigest})
 if e!=nil{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 var current ReviewerPGMarketRow
 if current.scan(tx.QueryRowContext(ctx,reviewerPGMarketQuery,input.OperationID))!=nil{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 candidate,e:=current.validate(s.now(),orig)
 if e!=nil||tx.Commit()!=nil{return ReviewerWatcherCandidate{},ErrReviewerHeld}
 return candidate,nil
}
