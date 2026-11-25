package satchel

import (
	"context"
	"strings"
	"testing"
	"time"
)

// Existing fixture contains real synthetic Comet validator signatures and
// response commitments. Its fixed 2026-10-15 timestamp is now historical.
// Live-time proof verification must still reject expired replay; archive-only
// proof authentication must recheck those bytes as of their original period,
// without yielding live AuthenticatedEvidence or spend/credit authority.
func TestArchivedTransferProofAcceptsOldSignedTranscriptButNeverCurrentAuthority(t *testing.T) {
	fixture, proof, _ := portableFixture(t, "transfer")
	intent := transferFixtureIntent(fixture)
	anchor := fixtureAnchor(fixture)

	live, err := NewProofVerifier(anchor)
	if err != nil {
		t.Fatal(err)
	}
	live.now = func() time.Time { return fixture.now.Add(48 * time.Hour) }
	if evidence, err := live.VerifyTransferProof(context.Background(), intent, fixture.observation.TxHash, proof); err == nil || evidence.ConsensusAuthenticated() {
		t.Fatal("live proof path accepted expired historical transcript")
	}
	archive, err := VerifyArchivedTransferProof(context.Background(), anchor, fixture.now, intent, fixture.observation.TxHash, proof)
	if err != nil || !archive.ConsensusAuthenticatedAgainstProvidedAnchor() {
		t.Fatalf("genuine synthetic historical Comet transcript rejected: %v", err)
	}
	if archive.CreditAuthorized() || archive.Receipt().TxHash != strings.ToUpper(fixture.observation.TxHash) {
		t.Fatal("archived result gained credit authority or lost exact tx binding")
	}
	if archive.Observation().Height != fixture.observation.Height {
		t.Fatal("historical proof returned unexpected signed inclusion height")
	}
}

func TestArchivedProofStillRejectsFutureTimeBadSignatureAndWrongIntent(t *testing.T) {
	fixture, proof, _ := portableFixture(t, "transfer")
	intent := transferFixtureIntent(fixture)
	anchor := fixtureAnchor(fixture)
	for _, asOf := range []time.Time{{}, time.Date(1999, 1, 1, 0, 0, 0, 0, time.UTC), time.Now().Add(time.Hour)} {
		if archived, err := VerifyArchivedTransferProof(context.Background(), anchor, asOf, intent, fixture.observation.TxHash, proof); err == nil || archived.ConsensusAuthenticatedAgainstProvidedAnchor() {
			t.Errorf("accepted invalid as-of instant %v", asOf)
		}
	}
	bad := clonePortable(t, proof)
	mutateResponse(t, &bad, "primary", "/commit", func(body map[string]any) {
		body["result"].(map[string]any)["signed_header"].(map[string]any)["commit"].(map[string]any)["signatures"].([]any)[0].(map[string]any)["signature"] = strings.Repeat("A", 84) + "AA=="
	})
	if archived, err := VerifyArchivedTransferProof(context.Background(), anchor, fixture.now, intent, fixture.observation.TxHash, bad); err == nil || archived.ConsensusAuthenticatedAgainstProvidedAnchor() {
		t.Fatal("archival as-of mode bypassed bad Comet signature")
	}
	intent.AmountUWolo = "999999999"
	if archived, err := VerifyArchivedTransferProof(context.Background(), anchor, fixture.now, intent, fixture.observation.TxHash, proof); err == nil || archived.ConsensusAuthenticatedAgainstProvidedAnchor() {
		t.Fatal("archival as-of mode bypassed original signed transfer amount")
	}
}
