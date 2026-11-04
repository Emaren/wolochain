package satchelservice

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCustodyJournalSnapshotHTTPPrivateReadAndBusyFence(t *testing.T) {
	b := &engineTestBackend{}
	e, _, _ := engineTestOpen(t, b)
	cfg := testHTTPConfig(t)
	cfg.Health.VaultAddress, cfg.Health.EscrowAddress = e.policy.Vault, e.policy.BettingEscrow
	cfg.Authorize = func(context.Context) bool { return false } // Read survives execution revocation.
	h := testHTTPHandler(t, e, cfg)
	journal := readTestCustodyJournal(t, e)
	request := func(method, path string, authenticated bool) *httptest.ResponseRecorder {
		r := testHTTPRequest(method, path, "")
		if !authenticated {
			r.Header.Del("Authorization")
		}
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w
	}
	path := "/satchel/v1/custody/journal-snapshot"
	w := request(http.MethodGet, path, true)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	_, err := VerifyCustodyJournalSnapshot(w.Body.Bytes(), journal.PolicyDigest, journal.JournalDigest)
	require.NoError(t, err)
	require.Equal(t, "no-store", w.Header().Get("Cache-Control"))
	require.Equal(t, http.StatusUnauthorized, request(http.MethodGet, path, false).Code)
	require.Equal(t, http.StatusMethodNotAllowed, request(http.MethodPost, path, true).Code)
	require.Equal(t, http.StatusBadRequest, request(http.MethodGet, path+"?owner=other", true).Code)
	e.mu.Lock()
	w = request(http.MethodGet, path, true)
	e.mu.Unlock()
	require.Equal(t, http.StatusConflict, w.Code, "busy export must not wait on a signer")
	require.Equal(t, journal, readTestCustodyJournal(t, e))
	require.Zero(t, b.signs.Load())
	require.Zero(t, b.broadcasts.Load())
	require.Zero(t, b.confirmations.Load())
}

type journalSnapshotHTTPFixture struct {
	httpTestBackend
	raw []byte
}

func (b *journalSnapshotHTTPFixture) CustodyJournalSnapshot() ([]byte, error) { return b.raw, nil }

func TestCustodyJournalSnapshotHTTPRefusesMalformedOrOtherPolicy(t *testing.T) {
	e, _, _ := engineTestOpen(t, &engineTestBackend{})
	raw, err := e.CustodyJournalSnapshot()
	require.NoError(t, err)
	cfg := testHTTPConfig(t)
	cfg.Health.VaultAddress, cfg.Health.EscrowAddress = e.policy.Vault, e.policy.BettingEscrow
	b := &journalSnapshotHTTPFixture{raw: raw}
	h := testHTTPHandler(t, b, cfg)
	for _, bad := range [][]byte{nil, []byte(`{}`), append(append([]byte{}, raw...), '\n')} {
		b.raw = bad
		w := httptest.NewRecorder()
		h.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/custody/journal-snapshot", ""))
		require.Equal(t, http.StatusConflict, w.Code)
	}
	b.raw = raw
	cfg.Health.VaultAddress = e.policy.BettingEscrow
	h = testHTTPHandler(t, b, cfg)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, testHTTPRequest(http.MethodGet, "/satchel/v1/custody/journal-snapshot", ""))
	require.Equal(t, http.StatusConflict, w.Code)
}
