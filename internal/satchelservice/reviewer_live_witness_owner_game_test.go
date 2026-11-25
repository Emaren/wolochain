package satchelservice

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	bolt "go.etcd.io/bbolt"
)

func TestOriginalLiveIssuerCannotRebindCaptureThroughAnotherGameAlias(t *testing.T) {
	issuer, source, _, c, _, now := newOriginalLiveWitnessTestIssuer(t)
	if issuer.IssueOne(t.Context(), c.OriginalOperationID).Witness == nil {
		t.Fatal("first original refused")
	}
	for _, alias := range []string{"same-session-game-alias", "platform:copied-session"} {
		source.original.Candidate.OriginalOperationID = "satchel:ticket:87654"
		source.original.Candidate.GameIdentityKey = alias
		if answer := issuer.IssueOne(t.Context(), source.original.Candidate.OriginalOperationID); answer.Witness != nil {
			t.Fatal("same original checkpoint witnessed twice under different game keys")
		}
	}
	issuer.now = func() time.Time { return now.Add(time.Second) }
}

func originalIssuerPolicy(t *testing.T) Policy {
	t.Helper()
	w, _, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	x, _, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	return Policy{WagerApprovalKey: w, WithdrawalApprovalKey: x}
}
func reopenOriginalIssuer(t *testing.T, issuer *OriginalLiveWitnessIssuer, source OriginalLiveCaptureSource, checkpoint ReviewerIndependentLiveCheckpointReader, now time.Time) *OriginalLiveWitnessIssuer {
	t.Helper()
	path := issuer.db.Path()
	key := append(ed25519.PrivateKey(nil), issuer.key...)
	if e := issuer.Close(); e != nil {
		t.Fatal(e)
	}
	reopened, e := OpenOriginalLiveWitnessIssuer(path, source, checkpoint, key, originalIssuerPolicy(t))
	if e != nil {
		t.Fatal(e)
	}
	reopened.now = func() time.Time { return now }
	t.Cleanup(func() { _ = reopened.Close() })
	return reopened
}
func TestOriginalLiveIssuerOwnerGameCannotApproveTwoOperations(t *testing.T) {
	for _, mutation := range []string{"same_game", "changed_side", "changed_proposition"} {
		t.Run(mutation, func(t *testing.T) {
			issuer, source, checkpoint, c, _, now := newOriginalLiveWitnessTestIssuer(t)
			first := issuer.IssueOne(t.Context(), c.OriginalOperationID)
			if first.Witness == nil {
				t.Fatal("first original operation refused")
			}
			issuer = reopenOriginalIssuer(t, issuer, source, checkpoint, now)
			original := source.original
			source.original.Candidate.OriginalOperationID = "satchel:ticket:87654"
			if mutation == "changed_side" {
				source.original.Candidate.SelectedSide = "right"
			}
			if mutation == "changed_proposition" {
				source.original.Candidate.PropositionHash = strings.Repeat("c", 64)
			}
			second := issuer.IssueOne(t.Context(), source.original.Candidate.OriginalOperationID)
			if second.Status != "PENDING" || second.Witness != nil {
				t.Fatal("one original game witnessed for two operations")
			}
			source.original = original
			again := issuer.IssueOne(t.Context(), c.OriginalOperationID)
			if again.Witness == nil || again.Witness.Signature != first.Witness.Signature {
				t.Fatal("legitimate cached original was blocked or resigned")
			}
		})
	}
}

type originalConcurrentCaptures map[string]OriginalLiveCapture

func (s originalConcurrentCaptures) ReadOriginalLiveCapture(ctx context.Context, id string) (OriginalLiveCapture, error) {
	if ctx.Err() != nil {
		return OriginalLiveCapture{}, ErrReviewerHeld
	}
	x, ok := s[id]
	if !ok {
		return x, ErrReviewerHeld
	}
	return x, nil
}
func TestOriginalLiveIssuerConcurrentDuplicateGamesAndDistinctGames(t *testing.T) {
	_, source, checkpoint, c, _, now := newOriginalLiveWitnessTestIssuer(t)
	captures := originalConcurrentCaptures{}
	for _, id := range []string{c.OriginalOperationID, "satchel:ticket:87654"} {
		x := source.original
		x.Candidate.OriginalOperationID = id
		captures[id] = x
	}
	_, key, e := ed25519.GenerateKey(nil)
	if e != nil {
		t.Fatal(e)
	}
	issuer, e := OpenOriginalLiveWitnessIssuer(filepath.Join(t.TempDir(), "concurrent.db"), captures, checkpoint, key, originalIssuerPolicy(t))
	if e != nil {
		t.Fatal(e)
	}
	issuer.now = func() time.Time { return now }
	t.Cleanup(func() { _ = issuer.Close() })
	var wg sync.WaitGroup
	var mu sync.Mutex
	signed := map[string]bool{}
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			id := c.OriginalOperationID
			if i%2 == 1 {
				id = "satchel:ticket:87654"
			}
			answer := issuer.IssueOne(t.Context(), id)
			if answer.Witness != nil {
				mu.Lock()
				signed[id] = true
				mu.Unlock()
			}
		}(i)
	}
	wg.Wait()
	if len(signed) != 1 {
		t.Fatalf("same owner/game signed %d operations", len(signed))
	}
	x := source.original
	x.Candidate.OriginalOperationID = "satchel:ticket:87655"
	x.Candidate.GameIdentityKey = "a-genuinely-distinct-original-game"
	checkpoint.data = []byte("a different original live checkpoint")
	digest := sha256.Sum256(checkpoint.data)
	x.CheckpointSHA256 = hex.EncodeToString(digest[:])
	captures[x.Candidate.OriginalOperationID] = x
	if answer := issuer.IssueOne(t.Context(), x.Candidate.OriginalOperationID); answer.Witness == nil {
		t.Fatal("distinct original game was blocked")
	}
}
func TestOriginalLiveIssuerCorruptOrMissingOwnerGameIndexIsHeld(t *testing.T) {
	for _, corrupt := range []bool{false, true} {
		issuer, _, _, c, _, _ := newOriginalLiveWitnessTestIssuer(t)
		if issuer.IssueOne(t.Context(), c.OriginalOperationID).Witness == nil {
			t.Fatal("first witness missing")
		}
		if e := issuer.db.Update(func(tx *bolt.Tx) error {
			if !corrupt {
				return tx.DeleteBucket(independentLiveOwnerGames)
			}
			return tx.Bucket(independentLiveOwnerGames).Put([]byte(originalLiveOwnerGame(c.OwnerUID, c.GameIdentityKey)), []byte("satchel:ticket:87654"))
		}); e != nil {
			t.Fatal(e)
		}
		if issuer.IssueOne(t.Context(), c.OriginalOperationID).Witness != nil {
			t.Fatal("corrupt game binding returned a signed witness")
		}
	}
}
func TestOriginalLiveIssuerDifferentOwnersShareGameButCannotShareJournalWriter(t *testing.T) {
	issuer, source, checkpoint, c, _, now := newOriginalLiveWitnessTestIssuer(t)
	if issuer.IssueOne(t.Context(), c.OriginalOperationID).Witness == nil {
		t.Fatal("first owner refused")
	}
	key := append(ed25519.PrivateKey(nil), issuer.key...)
	other, e := OpenOriginalLiveWitnessIssuer(issuer.db.Path(), source, checkpoint, key, originalIssuerPolicy(t))
	if other != nil || !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("two independently active issuer writers opened one journal")
	}
	source.original.Candidate.OriginalOperationID = "satchel:ticket:87654"
	source.original.Candidate.OwnerUID = "separate-original-owner"
	source.original.Candidate.OwnerSteamID = "76561198000000002"
	source.original.Candidate.SelectedSide = "right"
	if reply := issuer.IssueOne(t.Context(), source.original.Candidate.OriginalOperationID); reply.Witness == nil || reply.Witness.ExpiresAtMS > now.Add(30*time.Second).UnixMilli() {
		t.Fatal("separate original owner in same game was blocked")
	}
}
func TestOriginalLiveIssuerPendingOwnerGameRemainsFencedAfterRestart(t *testing.T) {
	issuer, source, checkpoint, c, _, now := newOriginalLiveWitnessTestIssuer(t)
	w, e := captureToWitness(source.original, now)
	if e != nil {
		t.Fatal(e)
	}
	if e = issuer.record(c.OriginalOperationID, originalLiveIssueEntry{
		Fingerprint: independentLiveFingerprint(w), OwnerGame: originalLiveOwnerGame(c.OwnerUID, c.GameIdentityKey), OwnerCapture: originalLiveOwnerCapture(c.OwnerUID, w.LiveCheckpointSHA256), Status: "PENDING",
	}, ""); e != nil {
		t.Fatal(e)
	}
	issuer = reopenOriginalIssuer(t, issuer, source, checkpoint, now)
	source.original.Candidate.OriginalOperationID = "satchel:ticket:87654"
	if answer := issuer.IssueOne(t.Context(), source.original.Candidate.OriginalOperationID); answer.Witness != nil {
		t.Fatal("crashed original reused through another operation")
	}
	source.original.Candidate.GameIdentityKey = "distinct-next-game"
	checkpoint.data = []byte("a different next-game live checkpoint")
	digest := sha256.Sum256(checkpoint.data)
	source.original.CheckpointSHA256 = hex.EncodeToString(digest[:])
	if answer := issuer.IssueOne(t.Context(), source.original.Candidate.OriginalOperationID); answer.Witness == nil {
		t.Fatal("known pending game blocked unrelated new game")
	}
}
func TestOriginalLiveIssuerReconstructsOnlySignedLegacyOwnerGameIndex(t *testing.T) {
	for _, legacy := range []string{"signed", "pending", "corrupt_signature", "oversize"} {
		t.Run(legacy, func(t *testing.T) {
			issuer, source, checkpoint, c, _, now := newOriginalLiveWitnessTestIssuer(t)
			answer := issuer.IssueOne(t.Context(), c.OriginalOperationID)
			if answer.Witness == nil {
				t.Fatal("fixture failed")
			}
			path := issuer.db.Path()
			key := append(ed25519.PrivateKey(nil), issuer.key...)
			if e := issuer.db.Update(func(tx *bolt.Tx) error {
				if e := tx.DeleteBucket(independentLiveOwnerGames); e != nil {
					return e
				}
				entry := originalLiveIssueEntry{Fingerprint: independentLiveFingerprint(*answer.Witness), Status: "SIGNED", Witness: answer.Witness}
				if legacy == "pending" {
					entry.Status = "PENDING"
					entry.Witness = nil
				}
				if legacy == "corrupt_signature" {
					copy := *answer.Witness
					copy.Signature = strings.Repeat("A", 88)
					entry.Witness = &copy
				}
				raw, e := json.Marshal(entry)
				if e != nil {
					return e
				}
				if legacy == "oversize" {
					raw = append([]byte(strings.Repeat(" ", originalLiveRecoveryEntryLimit)), raw...)
				}
				return tx.Bucket(independentLiveIssues).Put([]byte(c.OriginalOperationID), raw)
			}); e != nil {
				t.Fatal(e)
			}
			if e := issuer.Close(); e != nil {
				t.Fatal(e)
			}
			reopened, e := OpenOriginalLiveWitnessIssuer(path, source, checkpoint, key, originalIssuerPolicy(t))
			if legacy != "signed" {
				if reopened != nil || !errors.Is(e, ErrReviewerHeld) {
					t.Fatal("unknown legacy game was guessed or corrupt signature trusted")
				}
				return
			}
			if e != nil {
				t.Fatal(e)
			}
			defer reopened.Close()
			reopened.now = func() time.Time { return now }
			if e = reopened.db.View(func(tx *bolt.Tx) error {
				if string(tx.Bucket(independentLiveOwnerGames).Get([]byte(originalLiveOwnerGame(c.OwnerUID, c.GameIdentityKey)))) != c.OriginalOperationID {
					return errors.New("signed owner/game index missing")
				}
				return nil
			}); e != nil {
				t.Fatal(e)
			}
			if cached := reopened.IssueOne(t.Context(), c.OriginalOperationID); cached.Witness == nil || cached.Witness.Signature != answer.Witness.Signature {
				t.Fatal("signed legacy witness was not preserved")
			}
		})
	}
}
func TestOriginalLiveIssuerRecoveryHasAggregateByteBudget(t *testing.T) {
	issuer, source, checkpoint, _, _, _ := newOriginalLiveWitnessTestIssuer(t)
	path := issuer.db.Path()
	key := append(ed25519.PrivateKey(nil), issuer.key...)
	if e := issuer.db.Update(func(tx *bolt.Tx) error {
		for i := 0; i < 600; i++ {
			id := "satchel:ticket:" + strconv.Itoa(i+1)
			raw, e := json.Marshal(originalLiveIssueEntry{Fingerprint: strings.Repeat("a", 64), OwnerGame: originalLiveOwnerGame("owner", id), OwnerCapture: originalLiveOwnerCapture("owner", id), Status: "PENDING"})
			if e != nil {
				return e
			}
			raw = append([]byte(strings.Repeat(" ", 15000-len(raw))), raw...)
			if e = tx.Bucket(independentLiveIssues).Put([]byte(id), raw); e != nil {
				return e
			}
		}
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	if e := issuer.Close(); e != nil {
		t.Fatal(e)
	}
	if reopened, e := OpenOriginalLiveWitnessIssuer(path, source, checkpoint, key, originalIssuerPolicy(t)); reopened != nil || !errors.Is(e, ErrReviewerHeld) {
		t.Fatal("unbounded aggregate JSON recovery accepted")
	}
}
