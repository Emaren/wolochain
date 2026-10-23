package satchelservice

import (
	"encoding/base64"
	"strconv"
	"testing"
	"time"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/stretchr/testify/require"
)

func TestProductWagerCeilingRequiresExactSeparateReservation(t *testing.T) {
	p := engineTestPolicy(t)
	p.MaxAmountUWolo = 50_000_000_000
	r := engineTestWager(t, "10")
	r.AmountUWolo = strconv.FormatUint(ProductMaxWagerUWolo, 10)
	r.Reservation = testWagerReservation(t, r, p, time.Now())
	require.NoError(t, p.validate(r, time.Now()), "current 10,000 WOLO signed wager should fit product ceiling")
	r.AmountUWolo = strconv.FormatUint(ProductMaxWagerUWolo+1_000_000, 10)
	r.Reservation = testWagerReservation(t, r, p, time.Now())
	require.Error(t, p.validate(r, time.Now()), "fresh approval cannot override product ceiling")
	r = engineTestWager(t, "11")
	r.AmountUWolo = "2000000000"
	require.Error(t, p.validate(r, time.Now()), "old narrow reservation cannot silently authorize larger wager")
}

func TestProductNewOwnerCapsAreSignedAndOldOwnerCapsNeverWiden(t *testing.T) {
	m, x := sampleReviewerMandate(t)
	m.WinnerStakeWolo = ProductMaxWagerWOLO
	m.PerGameCapWolo = ProductMaxWagerWOLO
	m.DailyCapWolo = ProductMaxAutoDailyWOLO
	x.WinnerStakeWolo = m.WinnerStakeWolo
	resign := func() {
		i, _ := reviewerISO(m.IssuedAt)
		e, _ := reviewerISO(m.ChallengeExpiresAt)
		s, _ := reviewerISO(m.SpendExpiresAt)
		m.ChallengeText = reviewerOwnerChallengeText(m, i, e, s)
		data, err := ReviewerADR36SignBytes(m.WalletAddress, m.ChallengeText)
		require.NoError(t, err)
		key := sdksecp.GenPrivKeyFromSecret([]byte("test ADR36 user wallet held isolated 20261019"))
		sig, err := key.Sign(data)
		require.NoError(t, err)
		m.SignatureBase64 = base64.StdEncoding.EncodeToString(sig)
	}
	resign()
	require.NoError(t, VerifyReviewerOwnerMandate(m, x, m.SignedAt.Add(time.Minute)))
	m.DailyCapWolo++
	resign()
	require.Error(t, VerifyReviewerOwnerMandate(m, x, m.SignedAt.Add(time.Minute)))
	m, x = sampleReviewerMandate(t)
	x.WinnerStakeWolo = ProductMaxWagerWOLO
	require.Error(t, VerifyReviewerOwnerMandate(m, x, m.SignedAt.Add(time.Minute)), "product ceiling must not rewrite owner-signed lower limit")
}
