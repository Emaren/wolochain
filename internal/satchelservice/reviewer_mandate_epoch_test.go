package satchelservice

import (
	"context"
	"encoding/base64"
	"errors"
	"strings"
	"testing"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

func TestReviewerHeldEpochAuthenticatesOwnerButCannotIssueFinancialReview(t *testing.T) {
	m, x := sampleReviewerMandate(t)
	if err := VerifyReviewerOwnerMandate(m, x, m.SignedAt); err != nil {
		t.Fatal("pure original-wallet proof refused:", err)
	}
	if ReviewerAutoSpendAuthorizationProtocol != "aoe2war/satchel/mecha-auto-spend/v2" ||
		ReviewerAutoSpendAuthorizationEpoch != "aoe2war/satchel/mecha/v2/held-integration-1" || reviewerMandateEpochReleased() {
		t.Fatal("held source epoch was silently financially activated")
	}
	// The production PG source's financial path refuses this source epoch,
	// independently from any supplied owner proof or environment readiness flag.
	source := &ReviewerReadOnlyPGSource{}
	if !errors.Is(source.VerifyOwnerMandate(context.Background(), WagerReservation{OperationID: x.OriginalOperationID}), ErrReviewerHeld) {
		t.Fatal("held financial reviewer became accepting")
	}
}

func TestReviewerRejectsAuthenticOwnerSignaturesForOldOrFutureEpoch(t *testing.T) {
	for _, which := range []string{"unversioned", "old_epoch", "future_epoch", "old_protocol"} {
		t.Run(which, func(t *testing.T) {
			m, x := sampleReviewerMandate(t)
			switch which {
			case "unversioned":
				m.ChallengeText = strings.ReplaceAll(m.ChallengeText, "Authorization protocol: "+ReviewerAutoSpendAuthorizationProtocol+"\n", "")
				m.ChallengeText = strings.ReplaceAll(m.ChallengeText, "Authorization epoch: "+ReviewerAutoSpendAuthorizationEpoch+"\n", "")
			case "old_epoch":
				m.ChallengeText = strings.ReplaceAll(m.ChallengeText, ReviewerAutoSpendAuthorizationEpoch, "aoe2war/satchel/mecha/v2/release/old-epoch")
			case "future_epoch":
				m.ChallengeText = strings.ReplaceAll(m.ChallengeText, ReviewerAutoSpendAuthorizationEpoch, "aoe2war/satchel/mecha/v2/release/future-epoch")
			case "old_protocol":
				m.ChallengeText = strings.ReplaceAll(m.ChallengeText, ReviewerAutoSpendAuthorizationProtocol, "aoe2war/satchel/mecha-auto-spend/v1")
			}
			// A genuine owner signature is insufficient when the release epoch or
			// domain differs; this is not merely a corrupted-signature test.
			key := sdksecp.GenPrivKeyFromSecret([]byte("test ADR36 user wallet held isolated 20261019"))
			bytes, err := ReviewerADR36SignBytes(m.WalletAddress, m.ChallengeText)
			if err != nil {
				t.Fatal(err)
			}
			signature, err := key.Sign(bytes)
			if err != nil {
				t.Fatal(err)
			}
			m.SignatureBase64 = base64.StdEncoding.EncodeToString(signature)
			if !errors.Is(VerifyReviewerOwnerMandate(m, x, m.SignedAt), ErrReviewerOwnerMandate) {
				t.Fatal("owner signature crossed a release domain or epoch")
			}
		})
	}
}
