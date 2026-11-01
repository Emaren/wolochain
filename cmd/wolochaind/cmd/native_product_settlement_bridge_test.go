package cmd

// A subprocess entrypoint for the disposable product journey. It exposes the
// production legacy handler and executes the actual built Cosmos CLI against
// the isolated SDK fixture. It never substitutes a planned transaction hash.
import (
	"context"
	"encoding/json"
	"net"
	"net/http/httptest"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type nativeProductSettlementConfig struct {
	FixtureOnly bool   `json:"fixture_only"`
	Directory   string `json:"directory"`
	Binary      string `json:"binary"`
	RPC         string `json:"rpc"`
	KeyringDir  string `json:"keyring_dir"`
	UnlockFile  string `json:"unlock_file"`
	Escrow      string `json:"escrow"`
	Token       string `json:"token"`
	ReadyFile   string `json:"ready_file"`
}

func TestNativeProductSettlementBridgeProcess(t *testing.T) {
	path := os.Getenv("SATCHEL_PRODUCT_SETTLEMENT_TEST_CONFIG")
	if path == "" {
		t.Skip("disposable product subprocess only")
	}
	var input nativeProductSettlementConfig
	raw, err := os.ReadFile(path)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(raw, &input))
	require.True(t, input.FixtureOnly)
	directory, err := filepath.EvalSymlinks(input.Directory)
	require.NoError(t, err)
	require.Equal(t, input.Directory, directory)
	require.True(t, strings.HasPrefix(directory, filepath.Clean(os.TempDir())+string(filepath.Separator)))
	for _, child := range []string{path, input.KeyringDir, input.UnlockFile, input.ReadyFile} {
		relative, err := filepath.Rel(directory, child)
		require.NoError(t, err)
		require.False(t, relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)))
	}
	u, err := url.Parse(input.RPC)
	require.NoError(t, err)
	require.Equal(t, "http", u.Scheme)
	require.True(t, net.ParseIP(u.Hostname()).IsLoopback())
	require.True(t, filepath.IsAbs(input.Binary))
	password, err := os.ReadFile(input.UnlockFile)
	require.NoError(t, err)
	state := filepath.Join(directory, "legacy-settlement-state")
	require.NoError(t, os.MkdirAll(state, 0700))
	cfg := settlementConfig{ExecutablePath: input.Binary, HomeDir: input.KeyringDir, KeyringBackend: "file", KeyringDir: input.KeyringDir,
		KeyringPassphrase: strings.TrimSpace(string(password)), NodeAddr: input.RPC, RPCHTTP: input.RPC, RESTURL: input.RPC,
		ChainID: "wolo-1", BaseDenom: "uwolo", DisplayDenom: "wolo", AddressPrefix: "wolo", EscrowKeyName: "product-escrow",
		EscrowAddress: input.Escrow, BroadcastMode: "sync", Gas: "200000", Fees: "1uwolo", EscrowFeeHeadroomUWolo: 1,
		StateDir: state, ListenAddr: "127.0.0.1:0", AuthToken: input.Token, RequestLockTTL: time.Minute,
		RequestTimeout: 15 * time.Second, LookupTimeout: 5 * time.Second, HealthTimeout: 5 * time.Second,
		ConfirmTimeout: 5 * time.Second, ConfirmInterval: 10 * time.Millisecond}
	require.NoError(t, cfg.validateServeSafety())
	server := httptest.NewServer(cfg.newSettlementHTTPHandler())
	defer server.Close()
	ready, err := json.Marshal(map[string]any{"fixture_only": true, "mainnet_authority": false, "url": server.URL})
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(input.ReadyFile, ready, 0600))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
}
