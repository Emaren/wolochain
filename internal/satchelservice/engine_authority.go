package satchelservice

import (
	"context"
	"encoding/binary"
	"errors"
	"strings"

	bolt "go.etcd.io/bbolt"
)

var reservationAuthorities = []byte("execution-reservations-v1")
var reservationAuthorityIndex = []byte("execution-reservations-v1-indexed")
var reservationAuthorityCount = []byte("execution-reservations-v1-count")

func executionReservation(req TransferRequest) (string, error) {
	var digest string
	switch req.Kind {
	case "withdrawal":
		if req.Approval != nil {
			digest = req.Approval.ReservationDigest
		}
	case "wager":
		if req.Reservation != nil {
			digest = req.Reservation.ReservationDigest
		}
	}
	if !nonzeroDigest(digest) {
		return "", errors.New("execution_reservation_missing")
	}
	return strings.ToLower(digest), nil
}

// Index only the authority already retained in immutable operation records.
// Never rewrite an old request, invent a missing reservation, release a hold or
// accept historical collisions. A failure rolls this metadata transaction back;
// existing lookup and read-only reconciliation remain available for review.
func (e *Engine) reserveExecutionAuthority(ctx context.Context, tx *bolt.Tx, req TransferRequest) error {
	version := tx.Bucket(meta).Get(reservationAuthorityIndex)
	bucket := tx.Bucket(reservationAuthorities)
	var indexed uint64
	if version != nil {
		count := tx.Bucket(meta).Get(reservationAuthorityCount)
		if string(version) != "1" || bucket == nil || len(count) != 8 {
			return errors.New("reservation_authority_index_corrupt")
		}
		indexed = binary.BigEndian.Uint64(count)
		// A marker and an empty/reduced index must not resurrect a consumed
		// hold. This count is committed atomically with each original intent;
		// missing/corrupt metadata is a hold, never an index auto-repair.
		if indexed > 100000 || uint64(bucket.Stats().KeyN) != indexed {
			return errors.New("reservation_authority_index_corrupt")
		}
	}
	if version == nil {
		var err error
		bucket, err = tx.CreateBucketIfNotExists(reservationAuthorities)
		if err != nil {
			return err
		}
		indexed = uint64(bucket.Stats().KeyN)
		if indexed > 100000 {
			return errors.New("historical_reservation_capacity_hold")
		}
		count := 0
		if err := tx.Bucket(operations).ForEach(func(id, _ []byte) error {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			count++
			if count > 100000 {
				return errors.New("historical_reservation_capacity_hold")
			}
			r, err := load(tx, string(id))
			if err != nil {
				return errors.New("historical_reservation_state_unverifiable")
			}
			// Older ownerless wagers retain their original recovery semantics.
			// No reservation is fabricated for those historical transactions.
			if r.Request.Kind == "wager" && r.Request.Reservation == nil {
				return nil
			}
			digest, err := executionReservation(r.Request)
			if err != nil {
				return errors.New("historical_reservation_review_required")
			}
			if previous := bucket.Get([]byte(digest)); previous != nil {
				if string(previous) != string(id) {
					return errors.New("historical_reservation_collision_hold")
				}
			} else {
				indexed++
			}
			return bucket.Put([]byte(digest), id)
		}); err != nil {
			return err
		}
		if err := tx.Bucket(meta).Put(reservationAuthorityIndex, []byte("1")); err != nil {
			return err
		}
	}
	digest, err := executionReservation(req)
	if err != nil {
		return err
	}
	if previous := bucket.Get([]byte(digest)); previous != nil {
		return errors.New("execution_reservation_already_consumed")
	}
	if indexed >= 100000 {
		return errors.New("historical_reservation_capacity_hold")
	}
	if err := bucket.Put([]byte(digest), []byte(req.OperationID)); err != nil {
		return err
	}
	var count [8]byte
	binary.BigEndian.PutUint64(count[:], indexed+1)
	return tx.Bucket(meta).Put(reservationAuthorityCount, count[:])
}
