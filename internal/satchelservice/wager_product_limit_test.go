package satchelservice

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// A synthetic, independently signed fixture exercises the exact 10k product
// ceiling. No custodial key, RPC, or real chain transfer is involved.
func TestSatchelWagerSignedTenThousandWOLOProductBoundary(t *testing.T) {
	policy := engineTestPolicy(t)
	policy.MaxAmountUWolo = 50000 * 1000000 // withdrawal capacity is deliberately larger
	backend := &engineTestBackend{}
	dir := t.TempDir()
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	engine, err := Open(filepath.Join(dir, "operations.db"), policy, backend)
	if err != nil {
		t.Fatal(err)
	}
	defer engine.Close()
	engine.now = func() time.Time { return time.Unix(1800000000, 0) }
	send := func(id, amount string) TransferRequest {
		r := engineTestWager(t, id)
		r.AmountUWolo = amount
		r.Reservation = testWagerReservation(t, r, policy, time.Unix(1800000000, 0))
		return r
	}
	good := send("919101", "10000000000")
	outcome, err := engine.Submit(t.Context(), good)
	if err != nil || outcome.Status != "ACCEPTED" || backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
		t.Fatalf("signed owner-authorized 10000 WOLO fixture must be accepted: result=%+v err=%v", outcome, err)
	}
	for _, amount := range []string{"10001000000", "10000500000", "10000000001", "010000000000"} {
		bad := send("919102", amount)
		if _, err := engine.Submit(t.Context(), bad); err == nil {
			t.Fatalf("overcap, fractional, or malformed amount not refused: %s", amount)
		}
		if backend.signs.Load() != 1 || backend.broadcasts.Load() != 1 {
			t.Fatalf("invalid amount reached signing/broadcast: %s", amount)
		}
	}
	policy.MaxAmountUWolo = 1000 * 1000000 // lower signed transport policy also remains binding
	if err := policy.validate(send("919103", "10000000000"), time.Unix(1800000000, 0)); err == nil {
		t.Fatal("an operator-configured 1000 WOLO maximum cannot be enlarged by source change")
	}
}
