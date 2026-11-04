package satchelservice

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

func snapshotWire(t *testing.T, s CustodyJournalProofSnapshot) []byte {
	t.Helper()
	b, err := json.Marshal(s)
	require.NoError(t, err)
	return b
}

func snapshotDigest(frames []byte) string {
	h := sha256.New()
	h.Write([]byte("aoe2war/satchel/execution-journal/v1\x00"))
	h.Write(frames)
	return hex.EncodeToString(h.Sum(nil))
}

func testSnapshot(t *testing.T, e *Engine) ([]byte, CustodyJournalProofSnapshot, CustodyJournal) {
	t.Helper()
	j := readTestCustodyJournal(t, e)
	wire, err := e.CustodyJournalSnapshot()
	require.NoError(t, err)
	s, err := VerifyCustodyJournalSnapshot(wire, j.PolicyDigest, j.JournalDigest)
	require.NoError(t, err)
	require.Equal(t, j.JournalDigest, snapshotDigest(s.Frames))
	return wire, s, j
}

func TestCustodyJournalSnapshotActualSDKConfirmedParity(t *testing.T) {
	f := newCustodyAuthorityFixture(t)
	f.chain.release()
	result, err := f.engine.Submit(t.Context(), f.request)
	require.NoError(t, err)
	require.Equal(t, "ACCEPTED", result.Status)
	result, err = f.engine.Reconcile(t.Context(), f.request.OperationID)
	require.NoError(t, err)
	require.Equal(t, "CONFIRMED", result.Status)
	f.refreshReview(t) // isolated dual-signed fixture, not independent production reviewers
	signs, broadcasts := f.SDKSigns.Load(), f.chain.broadcasts
	wire, s, journal := testSnapshot(t, f.engine)
	require.Equal(t, uint64(1), journal.OperationsCount)
	require.Equal(t, uint64(1), journal.OperationStatusCounts["CONFIRMED"])
	require.Equal(t, f.review.JournalSnapshotSHA256, snapshotDigest(s.Frames))
	_, err = VerifyCustodyJournalSnapshot(wire, hashJSON(f.engine.policy), f.review.JournalSnapshotSHA256)
	require.NoError(t, err)
	var stored record
	require.NoError(t, f.engine.db.View(func(tx *bolt.Tx) error {
		var err error
		stored, err = load(tx, f.request.OperationID)
		return err
	}))
	// The proof retains the exact SDK transaction record, not a summary digest.
	require.Contains(t, string(s.Frames), string(mustSnapshotRecordJSON(t, stored)))
	require.Equal(t, signs, f.SDKSigns.Load())
	require.Equal(t, broadcasts, f.chain.broadcasts)
	_, _, after := testSnapshot(t, f.engine)
	require.Equal(t, journal, after)
}

func mustSnapshotRecordJSON(t *testing.T, r record) []byte {
	t.Helper()
	b, err := json.Marshal(r)
	require.NoError(t, err)
	return b
}

func TestCustodyJournalSnapshotEmptyNestedRawMutationAndSequence(t *testing.T) {
	backend := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, backend)
	initialWire, _, initial := testSnapshot(t, e)
	require.NoError(t, e.db.Update(func(tx *bolt.Tx) error {
		b, err := tx.CreateBucket([]byte("extra"))
		if err != nil {
			return err
		}
		_, err = b.CreateBucket([]byte("nested"))
		return err
	}))
	_, nested, nestedJournal := testSnapshot(t, e)
	require.NotEqual(t, initial.JournalDigest, nestedJournal.JournalDigest)
	// V1 journal commitments deliberately do not bind Bolt sequence metadata.
	require.NoError(t, e.db.Update(func(tx *bolt.Tx) error {
		return tx.Bucket([]byte("extra")).Bucket([]byte("nested")).SetSequence(42)
	}))
	_, sequence, sequenceJournal := testSnapshot(t, e)
	require.Equal(t, nested, sequence)
	require.Equal(t, nestedJournal.JournalDigest, sequenceJournal.JournalDigest)
	rawKey, rawValue := []byte{0, 255, 1}, []byte{255, 0, 128}
	require.NoError(t, e.db.Update(func(tx *bolt.Tx) error {
		return tx.Bucket([]byte("extra")).Bucket([]byte("nested")).Put(rawKey, rawValue)
	}))
	wire, raw, journal := testSnapshot(t, e)
	require.NotEqual(t, nestedJournal.JournalDigest, journal.JournalDigest)
	require.True(t, bytes.Contains(raw.Frames, append(append([]byte{}, rawKey...), rawValue...)))
	// Omission of an entire real bucket remains syntactically valid but cannot
	// match the separately enrolled journal digest.
	_, err := VerifyCustodyJournalSnapshot(initialWire, journal.PolicyDigest, journal.JournalDigest)
	require.Error(t, err)
	// Remove just the raw value frame while retaining its enclosing buckets.
	needle := append(append([]byte{}, rawKey...), rawValue...)
	at := bytes.Index(raw.Frames, needle) - 17
	require.GreaterOrEqual(t, at, 0)
	omitted := raw
	omitted.Frames = append(append([]byte{}, raw.Frames[:at]...), raw.Frames[at+17+len(needle):]...)
	_, err = VerifyCustodyJournalSnapshot(snapshotWire(t, omitted), journal.PolicyDigest, journal.JournalDigest)
	require.Error(t, err)
	changed := raw
	changed.Frames = append([]byte(nil), raw.Frames...)
	changed.Frames[len(changed.Frames)-1] ^= 1
	_, err = VerifyCustodyJournalSnapshot(snapshotWire(t, changed), journal.PolicyDigest, journal.JournalDigest)
	require.Error(t, err)
	changed = raw
	changed.Policy.MaxAmountUWolo++
	_, err = VerifyCustodyJournalSnapshot(snapshotWire(t, changed), journal.PolicyDigest, journal.JournalDigest)
	require.Error(t, err)
	_, err = VerifyCustodyJournalSnapshot(wire, strings.Repeat("a", 64), journal.JournalDigest)
	require.Error(t, err)
	_, err = VerifyCustodyJournalSnapshot(wire, journal.PolicyDigest, strings.Repeat("b", 64))
	require.Error(t, err)
	require.Zero(t, backend.signs.Load())
	require.Zero(t, backend.broadcasts.Load())
	require.Zero(t, backend.confirmations.Load())
}

func TestCustodyJournalSnapshotRejectsMalformedAndUnboundedData(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	wire, snapshot, journal := testSnapshot(t, e)
	for _, expected := range [][2]string{{"", ""}, {strings.Repeat("0", 64), journal.JournalDigest}, {journal.PolicyDigest, strings.Repeat("0", 64)}} {
		got, err := VerifyCustodyJournalSnapshot(wire, expected[0], expected[1])
		require.Error(t, err)
		require.True(t, reflect.DeepEqual(CustodyJournalProofSnapshot{}, got))
	}
	for _, bad := range [][]byte{nil, []byte(`{}`), append(append([]byte{}, wire...), '\n'), bytes.Repeat([]byte("x"), custodyJournalSnapshotMaxEncoded+1)} {
		_, err := VerifyCustodyJournalSnapshot(bad, journal.PolicyDigest, journal.JournalDigest)
		require.Error(t, err)
	}
	// Even an attacker supplying a matching digest cannot bypass grammar limits.
	frame := func(kind byte, key, value []byte) []byte {
		b := make([]byte, 17)
		b[0] = kind
		binary.BigEndian.PutUint64(b[1:9], uint64(len(key)))
		binary.BigEndian.PutUint64(b[9:17], uint64(len(value)))
		return append(append(b, key...), value...)
	}
	bucket, end := frame('B', []byte("a"), nil), frame('E', nil, nil)
	cases := [][]byte{
		{}, {0}, bucket, end,
		append(append([]byte{}, bucket...), frame('P', nil, nil)...),
		append(append([]byte{}, bucket...), frame('E', []byte("bad"), nil)...),
		append(append(append([]byte{}, bucket...), end...), end...),
		append(append(append(append([]byte{}, bucket...), frame('V', []byte("z"), nil)...), frame('V', []byte("a"), nil)...), end...),
		bytes.Repeat(bucket, custodyJournalMaxDepth+2),
		bytes.Repeat(end, custodyJournalMaxRecords+1),
		make([]byte, custodyJournalMaxBytes+1),
	}
	tooMany := append([]byte{}, bucket...)
	for i := 0; i < custodyJournalMaxRecords; i++ {
		tooMany = append(tooMany, frame('V', []byte(fmt.Sprintf("%06d", i)), nil)...)
	}
	tooMany = append(tooMany, end...)
	cases = append(cases, tooMany)
	for i, frames := range cases {
		s := snapshot
		s.Frames = frames
		_, err := VerifyCustodyJournalSnapshot(snapshotWire(t, s), journal.PolicyDigest, snapshotDigest(frames))
		require.Error(t, err, "case %d", i)
	}
	// Self-selected expectations are only a consistency check, never proof of
	// genuine review provenance or journal completeness: this API cannot enroll.
	fake := snapshot
	fake.Frames = append(append([]byte{}, bucket...), end...)
	_, err := VerifyCustodyJournalSnapshot(snapshotWire(t, fake), hashJSON(fake.Policy), snapshotDigest(fake.Frames))
	require.NoError(t, err)
}

func TestCustodyJournalSnapshotExportRejectsInvalidAndOversizedState(t *testing.T) {
	for _, mode := range []string{"policy", "bytes"} {
		t.Run(mode, func(t *testing.T) {
			e, _, _ := engineTestOpen(t, &engineTestBackend{})
			require.NoError(t, e.db.Update(func(tx *bolt.Tx) error {
				if mode == "policy" {
					return tx.Bucket(meta).Put([]byte("policy"), []byte("fake"))
				}
				b, err := tx.CreateBucket([]byte("extra"))
				if err != nil {
					return err
				}
				return b.Put([]byte("oversized"), make([]byte, custodyJournalMaxBytes))
			}))
			wire, err := e.CustodyJournalSnapshot()
			require.Error(t, err)
			require.Nil(t, wire)
		})
	}
}

func TestCustodyJournalSnapshotRefusesUnavailableOrBusyEngine(t *testing.T) {
	var absent *Engine
	if b, err := absent.CustodyJournalSnapshot(); err == nil || b != nil {
		t.Fatal("nil engine exported a snapshot")
	}
	empty := &Engine{}
	if b, err := empty.CustodyJournalSnapshot(); err == nil || b != nil {
		t.Fatal("unopened engine exported a snapshot")
	}
	empty.mu.Lock()
	if b, err := empty.CustodyJournalSnapshot(); err == nil || b != nil {
		t.Fatal("busy engine exported a snapshot")
	}
	empty.mu.Unlock()
}
