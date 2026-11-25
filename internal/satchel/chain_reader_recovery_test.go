package satchel

import (
	"net/http"
	"sync/atomic"
	"testing"
	"time"
)

// All responses and validator signatures are synthetic. A bounded clock
// correction while observing the witness makes its observation older than the
// primary's; subsequent light-client I/O must recheck each retained head. No
// evidence, checkpoint, HTTP transport, or CometBFT verification is bypassed.
func TestTrustedReaderWitnessCannotExpireDuringAuthentication(t *testing.T) {
	f, vals := signedReaderFixture(t)
	var phase atomic.Int32
	primary := adversarialTrustedServer(t, f, vals, func(_ http.ResponseWriter, request *http.Request) bool {
		if request.URL.Path == "/validators" {
			phase.Store(3)
		}
		return false
	})
	witness := adversarialTrustedServer(t, f, vals, func(_ http.ResponseWriter, request *http.Request) bool {
		if request.URL.Path == "/status" {
			phase.Store(1)
		} else if request.URL.Path == "/commit" {
			phase.CompareAndSwap(1, 2)
		}
		return false
	})
	r := adversarialTrustedReader(t, f, primary, witness, fixtureAnchor(f))
	r.reader.now = func() time.Time {
		switch phase.Load() {
		case 1:
			// Still within the allowed 5s difference from the committed head.
			return f.now.Add(-8 * time.Second)
		case 3:
			// Primary observation age=23s and committed block age=26s;
			// witness observation age=31s, beyond the 30s contract.
			return f.now.Add(23 * time.Second)
		default:
			return f.now
		}
	}
	typed := assertTrustedRefusal(t, r, f)
	if phase.Load() != 3 || typed.Code != StaleHead || typed.Source != "witness" || typed.Operation != "complete" {
		t.Fatalf("witness expiration lost its deterministic completion failure: phase=%d error=%v", phase.Load(), typed)
	}
}
