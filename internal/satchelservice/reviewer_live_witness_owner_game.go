package satchelservice

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	bolt "go.etcd.io/bbolt"
)

var independentLiveOwnerGames = []byte("original-live-watcher-owner-games-v1")

const originalLiveRecoveryByteLimit = 8 << 20
const originalLiveRecoveryEntryLimit = 16 << 10

func originalLiveOwnerGame(owner, game string) string {
	raw, _ := json.Marshal([]string{"aoe2war/satchel/original-live-owner-game/v1", owner, game})
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:])
}

func originalLiveOwnerCapture(owner, checkpoint string) string {
	raw, _ := json.Marshal([]string{"aoe2war/satchel/original-live-owner-capture/v1", owner, checkpoint})
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:])
}

// Rebuild only derivable indexes from original, signed durable evidence.
// A legacy PENDING record lacks owner/game facts, so its possible game cannot
// be guessed or released. Opening that journal remains HELD for review.
func recoverOriginalLiveOwnerGames(tx *bolt.Tx, key ed25519.PublicKey) error {
	issues, games := tx.Bucket(independentLiveIssues), tx.Bucket(independentLiveOwnerGames)
	count := 0
	totalBytes := 0
	return issues.ForEach(func(id, raw []byte) error {
		count++
		if count > 100000 || raw == nil || len(id) > 128 || len(raw) > originalLiveRecoveryEntryLimit ||
			len(raw)+len(id) > originalLiveRecoveryByteLimit-totalBytes || !wagerIDs.Match(id) {
			return ErrReviewerHeld
		}
		totalBytes += len(raw) + len(id)
		var entry originalLiveIssueEntry
		if json.Unmarshal(raw, &entry) != nil || !reviewerHexDigest.MatchString(entry.Fingerprint) ||
			(entry.Status != "PENDING" && entry.Status != "SIGNED") {
			return ErrReviewerHeld
		}
		ownerGame := entry.OwnerGame
		ownerCapture := entry.OwnerCapture
		if entry.Status == "SIGNED" {
			w := entry.Witness
			if w == nil || w.OperationID != string(id) || w.Version != 2 || !ownerUIDPattern.MatchString(w.OwnerUID) ||
				w.GameIdentityKey == "" || len(w.GameIdentityKey) > 255 || independentLiveFingerprint(*w) != entry.Fingerprint {
				return ErrReviewerHeld
			}
			signature, e := base64.StdEncoding.Strict().DecodeString(w.Signature)
			if e != nil || len(signature) != ed25519.SignatureSize || base64.StdEncoding.EncodeToString(signature) != w.Signature || !ed25519.Verify(key, ReviewerWatcherLiveWitnessMessage(*w), signature) {
				return ErrReviewerHeld
			}
			derived := originalLiveOwnerGame(w.OwnerUID, w.GameIdentityKey)
			if ownerGame != "" && ownerGame != derived {
				return ErrReviewerHeld
			}
			ownerGame = derived
			derivedCapture := originalLiveOwnerCapture(w.OwnerUID, w.LiveCheckpointSHA256)
			if !reviewerHexDigest.MatchString(w.LiveCheckpointSHA256) || ownerCapture != "" && ownerCapture != derivedCapture {
				return ErrReviewerHeld
			}
			ownerCapture = derivedCapture
		} else if entry.Witness != nil {
			return ErrReviewerHeld
		}
		if !reviewerHexDigest.MatchString(ownerGame) || !reviewerHexDigest.MatchString(ownerCapture) {
			return ErrReviewerHeld
		}
		prior := games.Get([]byte(ownerGame))
		if len(prior) > 128 || prior != nil && string(prior) != string(id) {
			return ErrReviewerHeld
		}
		priorCapture := games.Get([]byte(ownerCapture))
		if len(priorCapture) > 128 || priorCapture != nil && string(priorCapture) != string(id) {
			return ErrReviewerHeld
		}
		if err := games.Put([]byte(ownerGame), id); err != nil {
			return err
		}
		return games.Put([]byte(ownerCapture), id)
	})
}
