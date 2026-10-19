package satchelservice

// A separately governed PostgreSQL role must verify the ORIGINAL stored
// Keplr mandate, not treat a signed_at column as spending authority.
// This component remains financially held because Watcher and chain bank
// evidence adapters are not yet authenticated or enabled.
import (
 "context"
 "database/sql"
 "time"
)

const reviewerPGMandateQuery = `
SELECT c.id::text,c.owner_uid,c.wallet_address,c.preset_id,c.preset_version,
       c.winner_stake_wolo,c.desync_stake_wolo,c.desync_side,
       c.per_game_cap_wolo,c.daily_cap_wolo,c.nonce,
       c.issued_at,c.challenge_expires_at,c.spend_expires_at,
       c.signed_at,c.revoked_at,
       m.until_out,m.games_remaining,m.challenge_text,
       m.owner_signature_json::text,m.signed_at,
       p.enabled,p.self_only,p.version,p.until_out,p.games_remaining,
       p.winner_stake_wolo,p.desync_stake_wolo,p.desync_side,
       u.uid,u.wallet_address
FROM public.war_satchel_wager_authorizations a
JOIN public.war_satchel_auto_spend_consents c
 ON c.id::text=(a.snapshot_json->>'consentId')
 AND c.owner_user_id=a.owner_user_id
JOIN public.war_satchel_auto_spend_mandates m ON m.consent_id=c.id
JOIN public.bet_auto_presets p
 ON p.id=c.preset_id AND p.user_id=c.owner_user_id
JOIN public.users u ON u.id=c.owner_user_id
WHERE a.operation_id=$1
`

type ReviewerPGMandateRow struct {
 ConsentID,OwnerUID,Wallet string
 PresetID,PresetVersion int64
 WinnerStakeWolo,DesyncStakeWolo int64
 DesyncSide string
 PerGameCapWolo,DailyCapWolo int64
 Nonce string
 IssuedAt,ChallengeExpiresAt,SpendExpiresAt time.Time
 SignedAt,RevokedAt sql.NullTime
 UntilOut bool
 GamesRemaining sql.NullInt64
 ChallengeText,SignatureJSON string
 MandateSignedAt sql.NullTime
 PlanEnabled,PlanSelfOnly bool
 CurrentPresetVersion int64
 CurrentUntilOut bool
 CurrentGamesRemaining sql.NullInt64
 CurrentWinnerStakeWolo,CurrentDesyncStakeWolo int64
 CurrentDesyncSide,CurrentUID string
 CurrentWallet sql.NullString
}
func (r *ReviewerPGMandateRow)scan(row *sql.Row)error{
 return row.Scan(&r.ConsentID,&r.OwnerUID,&r.Wallet,
  &r.PresetID,&r.PresetVersion,&r.WinnerStakeWolo,&r.DesyncStakeWolo,&r.DesyncSide,
  &r.PerGameCapWolo,&r.DailyCapWolo,&r.Nonce,
  &r.IssuedAt,&r.ChallengeExpiresAt,&r.SpendExpiresAt,
  &r.SignedAt,&r.RevokedAt,
  &r.UntilOut,&r.GamesRemaining,&r.ChallengeText,&r.SignatureJSON,&r.MandateSignedAt,
  &r.PlanEnabled,&r.PlanSelfOnly,&r.CurrentPresetVersion,&r.CurrentUntilOut,
  &r.CurrentGamesRemaining,&r.CurrentWinnerStakeWolo,&r.CurrentDesyncStakeWolo,
  &r.CurrentDesyncSide,&r.CurrentUID,&r.CurrentWallet)
}
func reviewerNullableGames(x sql.NullInt64)*int64{
 if !x.Valid{return nil}
 v:=x.Int64;return &v
}
func (r ReviewerPGMandateRow)verify(original ReviewerHDOriginResult, now time.Time)error{
 if !r.PlanEnabled||!r.PlanSelfOnly||
  r.ConsentID!=original.ConsentID||
  r.OwnerUID!=original.OwnerUID||
  r.Wallet!=original.OwnerWallet||
  r.CurrentUID!=original.OwnerUID||
  !r.CurrentWallet.Valid||r.CurrentWallet.String!=original.OwnerWallet||
  r.PresetID!=original.PresetID||r.PresetVersion!=original.PresetVersion||
  r.CurrentPresetVersion!=original.PresetVersion||
  !r.SignedAt.Valid||!r.MandateSignedAt.Valid||
  !r.SignedAt.Time.Equal(r.MandateSignedAt.Time)||
  r.ChallengeText!=original.ChallengeText{
  return ErrReviewerHeld
 }
 parsed,e:=reviewerStrictJSON([]byte(r.SignatureJSON))
 if e!=nil{return ErrReviewerHeld}
 signature,ok:=parsed.(map[string]any)
 if !ok||!reviewerRecord(signature,[]string{"pub_key","signature"}){return ErrReviewerHeld}
 pub,ok:=signature["pub_key"].(map[string]any)
 if !ok||!reviewerRecord(pub,[]string{"type","value"}){return ErrReviewerHeld}
 originalHash,e1:=reviewerCanonicalHash(original.OwnerSignatureJSON)
 actualHash,e2:=reviewerCanonicalHash(signature)
 if e1!=nil||e2!=nil||originalHash!=actualHash{return ErrReviewerHeld}
 mandate:=ReviewerStoredOwnerMandate{
  OwnerUID:r.OwnerUID,WalletAddress:r.Wallet,
  PresetID:r.PresetID,PresetVersion:r.PresetVersion,
  WinnerStakeWolo:r.WinnerStakeWolo,
  DesyncSide:r.DesyncSide,DesyncStakeWolo:r.DesyncStakeWolo,
  PerGameCapWolo:r.PerGameCapWolo,DailyCapWolo:r.DailyCapWolo,
  UntilOut:r.UntilOut,GamesRemaining:reviewerNullableGames(r.GamesRemaining),
  Nonce:r.Nonce,
  IssuedAt:r.IssuedAt.UTC(),ChallengeExpiresAt:r.ChallengeExpiresAt.UTC(),
  SpendExpiresAt:r.SpendExpiresAt.UTC(),SignedAt:r.SignedAt.Time.UTC(),
  ChallengeText:r.ChallengeText,
  PublicKeyType:reviewerStr(pub,"type"),PublicKeyBase64:reviewerStr(pub,"value"),
  SignatureBase64:reviewerStr(signature,"signature"),
 }
 if r.RevokedAt.Valid {rev:=r.RevokedAt.Time.UTC();mandate.RevokedAt=&rev}
 expected:=ReviewerOwnerExpectation{
  OwnerUID:r.CurrentUID,WalletAddress:r.CurrentWallet.String,
  PresetID:r.PresetID,PresetVersion:r.CurrentPresetVersion,
  WinnerStakeWolo:r.CurrentWinnerStakeWolo,DesyncStakeWolo:r.CurrentDesyncStakeWolo,
  DesyncSide:r.CurrentDesyncSide,UntilOut:r.CurrentUntilOut,
  GamesRemaining:reviewerNullableGames(r.CurrentGamesRemaining),
  OriginalOperationID:original.OperationID,
 }
 if VerifyReviewerOwnerMandate(mandate,expected,now)!=nil{return ErrReviewerHeld}
 return nil
}

// VerifyOwnerMandate independently re-reads original SQL and the signed
// Keplr consent from a SELECT-only principal. It CANNOT grant a chain send:
// caller must still prove an unmodified live Watcher market and complete
// independently authenticated bank/liabilities/fee census.
func (s *ReviewerReadOnlyPGSource)VerifyOwnerMandate(ctx context.Context,input WagerReservation)error{
 if s==nil||s.db==nil||ctx==nil||!wagerIDs.MatchString(input.OperationID){return ErrReviewerHeld}
 original,e:=s.OriginalHold(ctx,input.OperationID)
 if e!=nil||original.OwnerID!=input.OwnerID||
  original.Vault!=input.Vault||original.Recipient!=input.Recipient||
  original.AmountUWolo!=input.AmountUWolo||original.Memo!=input.Memo||
  original.ReservationDigest!=input.ReservationDigest||
  original.LedgerRevision!=input.LedgerRevision||
  original.ConsentDigest!=input.ConsentDigest||
  original.FeeUWolo!=input.FeeUWolo{return ErrReviewerHeld}
 ctx,cancel:=context.WithTimeout(ctx,2*time.Second);defer cancel()
 tx,e:=s.db.BeginTx(ctx,&sql.TxOptions{Isolation:sql.LevelRepeatableRead,ReadOnly:true})
 if e!=nil{return ErrReviewerHeld}
 defer func(){_ = tx.Rollback()}()
 var user,readonly string
 var privileged,canWrite bool
 if tx.QueryRowContext(ctx,reviewerPGIdentityQuery).Scan(&user,&readonly,&privileged,&canWrite)!=nil||
  user!=s.expectedRole||readonly!="on"||privileged||canWrite{return ErrReviewerHeld}
 var row ReviewerPGMandateRow
 if row.scan(tx.QueryRowContext(ctx,reviewerPGMandateQuery,input.OperationID))!=nil{return ErrReviewerHeld}
 // The original immutable source is re-read in the same transaction as the
 // mandate; do not pair a fresh signature with an old/cross-user hold.
 var source ReviewerPGOriginalRow
 if source.scan(tx.QueryRowContext(ctx,reviewerPGOriginalQuery,input.OperationID))!=nil{return ErrReviewerHeld}
 held,e:=source.validate(s.now(),s.fee,s.vault,s.escrow)
 if e!=nil||held.OwnerID!=input.OwnerID||
  held.ReservationDigest!=input.ReservationDigest||
  held.ConsentDigest!=input.ConsentDigest||
  held.LedgerRevision!=input.LedgerRevision{return ErrReviewerHeld}
 originalPayload,e:=VerifyReviewerHDOrigin([]byte(source.SnapshotJSON),ReviewerHDOriginColumns{
  OperationID:source.OperationID,ReservationID:source.ReservationID,OwnerUserID:source.OwnerUserID,
  ReservationDigest:source.ReservationDigest,LedgerRevision:source.LedgerRevision,
  ConsentDigest:source.ConsentDigest})
 if e!=nil||row.verify(originalPayload,s.now())!=nil{return ErrReviewerHeld}
 if tx.Commit()!=nil{return ErrReviewerHeld}
 return nil
}
