package satchel

import (
	"context"
	"net/http"
	"sync/atomic"
	"testing"
	"time"

	cmtjson "github.com/cometbft/cometbft/libs/json"
	"github.com/stretchr/testify/require"
)

func TestCurrentBankProofUsesServerSelectedLatestCommit(t *testing.T) {
	f := newNativeBankFixture(t)
	f.f.status.SyncInfo.LatestBlockHeight = 101
	f.f.status.SyncInfo.LatestBlockHash = f.f.commits[101].Header.Hash()
	f.f.status.SyncInfo.LatestBlockTime = f.f.commits[101].Header.Time
	e, p, err := f.reader(t, nil).ReadCurrentBankProof(context.Background(), f.vault)
	require.NoError(t, err)
	require.EqualValues(t, 100, p.Height)
	require.Equal(t, e.CommitHeight(), e.HeadHeight())
	require.Equal(t, e.BlockHash(), e.HeadBlockHash())
	require.Equal(t, f.f.commits[101].Time, e.HeadTime())
	require.True(t, e.ExpiresAt().After(f.f.now))
	require.False(t, e.FreshAt(e.ExpiresAt().Add(time.Nanosecond)))
}

func TestCurrentBankProofRefusesHeadAdvanceAndNilContext(t *testing.T) {
	f := newNativeBankFixture(t)
	f.f.status.SyncInfo.LatestBlockHeight = 101
	f.f.status.SyncInfo.LatestBlockHash = f.f.commits[101].Header.Hash()
	f.f.status.SyncInfo.LatestBlockTime = f.f.commits[101].Header.Time
	var calls atomic.Int32
	r := f.reader(t, func(request *http.Request, body []byte) []byte {
		if request.URL.Path != "/status" || calls.Add(1) == 1 {
			return body
		}
		status := f.f.status
		status.SyncInfo.LatestBlockHeight = 102
		status.SyncInfo.LatestBlockHash = f.f.commits[102].Header.Hash()
		status.SyncInfo.LatestBlockTime = f.f.commits[102].Header.Time
		encoded, err := cmtjson.Marshal(status)
		require.NoError(t, err)
		return append(append([]byte(`{"jsonrpc":"2.0","id":-1,"result":`), encoded...), '}')
	})
	e, _, err := r.ReadCurrentBankProof(context.Background(), f.vault)
	require.Error(t, err)
	var failure *EvidenceError
	require.ErrorAs(t, err, &failure)
	require.Equal(t, StaleHead, failure.Code)
	require.False(t, e.FreshAt(f.f.now))
	_, _, err = r.ReadCurrentBankProof(nil, f.vault)
	require.Error(t, err)
}
