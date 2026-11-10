package satchelservice

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

func c01ServeFixture(t *testing.T) c01StatusEndpoint {
	t.Helper()
	root, err := filepath.EvalSymlinks("/tmp")
	if err != nil {
		t.Fatal(err)
	}
	dir, err := os.MkdirTemp(root, "c01-status-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	if err := os.Chown(dir, -1, os.Getegid()); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	old := unix.Umask(0177)
	t.Cleanup(func() { unix.Umask(old) })
	endpoint, err := newC01StatusEndpoint(dir, uint32(os.Geteuid()), uint32(os.Getegid()))
	if err != nil {
		t.Fatal(err)
	}
	return endpoint
}

func c01ServeTestClient(t *testing.T, path string) *http.Client {
	t.Helper()
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", path)
		},
		DisableKeepAlives: true,
	}
	t.Cleanup(transport.CloseIdleConnections)
	return &http.Client{Transport: transport, Timeout: time.Second}
}

func startC01TestStatus(t *testing.T, endpoint c01StatusEndpoint, expires time.Time, current func(context.Context) bool) (context.CancelFunc, <-chan error) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	done := make(chan error, 1)
	go func() {
		done <- serveC01Status(ctx, endpoint, C01NonfundedKeyReceipt{
			Schema: "wolo.c01.zero-funded-key-possession-receipt.v1", Role: C01CustodyRole,
		}, expires, current)
	}()
	until := time.Now().Add(time.Second)
	for time.Now().Before(until) {
		if _, err := endpoint.socketInfo(); err == nil {
			return cancel, done
		}
		select {
		case err := <-done:
			t.Fatalf("status service refused before bind: %v", err)
		case <-time.After(5 * time.Millisecond):
		}
	}
	t.Fatal("status socket did not appear")
	return nil, nil
}

func c01TestStatusRequest(t *testing.T, client *http.Client, method, path string, body io.Reader) *http.Response {
	t.Helper()
	request, err := http.NewRequest(method, "http://localhost"+path, body)
	if err != nil {
		t.Fatal(err)
	}
	response, err := client.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = response.Body.Close() })
	return response
}

func awaitC01TestStatusStop(t *testing.T, done <-chan error, expected error) {
	t.Helper()
	select {
	case err := <-done:
		if !errors.Is(err, expected) {
			t.Fatalf("unexpected shutdown: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("status service did not stop within one second")
	}
}

func TestC01StatusPrivateSocketAndRevocation(t *testing.T) {
	endpoint := c01ServeFixture(t)
	var live atomic.Bool
	live.Store(true)
	_, done := startC01TestStatus(t, endpoint, time.Now().Add(time.Minute),
		func(context.Context) bool { return live.Load() })
	client := c01ServeTestClient(t, endpoint.socket)
	response := c01TestStatusRequest(t, client, http.MethodGet, "/status", nil)
	var receipt C01NonfundedKeyReceipt
	if response.StatusCode != http.StatusOK || response.Header.Get("Cache-Control") != "no-store" ||
		json.NewDecoder(response.Body).Decode(&receipt) != nil || receipt.FundingAuthorized ||
		receipt.Role != C01CustodyRole || receipt.Schema != "wolo.c01.zero-funded-key-possession-receipt.v1" {
		t.Fatal("private zero-funds status receipt refused")
	}
	_ = response.Body.Close()
	for _, test := range []struct {
		method, path, body string
		status             int
	}{
		{http.MethodPost, "/status", "", http.StatusMethodNotAllowed},
		{http.MethodGet, "/status", "request body", http.StatusMethodNotAllowed},
		{http.MethodGet, "/status?", "", http.StatusNotFound},
		{http.MethodGet, "/%73tatus", "", http.StatusNotFound},
		{http.MethodPost, "/satchel/v1/operations", "", http.StatusNotFound},
		{http.MethodPost, "/reviewer/v1/wagers", "", http.StatusNotFound},
	} {
		var body io.Reader
		if test.body != "" {
			body = strings.NewReader(test.body)
		}
		r := c01TestStatusRequest(t, client, test.method, test.path, body)
		if r.StatusCode != test.status {
			t.Fatalf("%s %s: got %d, want %d", test.method, test.path, r.StatusCode, test.status)
		}
		_ = r.Body.Close()
	}

	conn, err := net.DialTimeout("unix", endpoint.socket, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if err := conn.SetDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if _, err := io.WriteString(conn, "OPTIONS * HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	options, err := http.ReadResponse(bufio.NewReader(conn), &http.Request{Method: http.MethodOptions})
	if err != nil || options.StatusCode != http.StatusNotFound {
		t.Fatalf("general OPTIONS handler not refused: %v", err)
	}
	_ = options.Body.Close()

	live.Store(false)
	if response, err := client.Get("http://localhost/status"); err == nil {
		_ = response.Body.Close()
		if response.StatusCode != http.StatusServiceUnavailable {
			t.Fatalf("response after revoke: %d", response.StatusCode)
		}
	}
	awaitC01TestStatusStop(t, done, nil)
	if _, err := endpoint.socketInfo(); err != nil {
		t.Fatal("daemon unlinked the socket pathname")
	}
	if conn, err := net.DialTimeout("unix", endpoint.socket, time.Second); err == nil {
		conn.Close()
		t.Fatal("listener survived revocation")
	}
}

func TestC01StatusRefusesPriorSocketAndSwap(t *testing.T) {
	endpoint := c01ServeFixture(t)
	current := func(context.Context) bool { return true }
	if err := serveC01Status(context.Background(), endpoint, C01NonfundedKeyReceipt{},
		time.Now().Add(time.Minute), func(context.Context) bool { return false }); err == nil || !endpoint.available() {
		t.Fatal("refused admission bound or mutated the socket")
	}

	prior, err := net.ListenUnix("unix", &net.UnixAddr{Name: endpoint.socket, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	defer prior.Close()
	priorInfo, err := endpoint.socketInfo()
	if err != nil {
		t.Fatal(err)
	}
	if err := serveC01Status(context.Background(), endpoint, C01NonfundedKeyReceipt{},
		time.Now().Add(time.Minute), current); !errors.Is(err, ErrC01NonfundedAdmission) {
		t.Fatalf("preexisting socket not refused: %v", err)
	}
	same, err := endpoint.socketInfo()
	if err != nil || !os.SameFile(same, priorInfo) {
		t.Fatal("preexisting socket changed")
	}
	if err := prior.Close(); err != nil {
		t.Fatal(err)
	}

	_, done := startC01TestStatus(t, endpoint, time.Now().Add(time.Minute), current)
	displaced := filepath.Join(endpoint.dir, "displaced.sock")
	if err := os.Rename(endpoint.socket, displaced); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(endpoint.socket, []byte("replacement"), 0600); err != nil {
		t.Fatal(err)
	}
	awaitC01TestStatusStop(t, done, ErrC01NonfundedAdmission)
	if raw, err := os.ReadFile(endpoint.socket); err != nil || string(raw) != "replacement" {
		t.Fatal("daemon removed or altered the replacement")
	}
}

func TestC01StatusStopsAtExpiry(t *testing.T) {
	endpoint := c01ServeFixture(t)
	_, done := startC01TestStatus(t, endpoint, time.Now().Add(600*time.Millisecond),
		func(context.Context) bool { return true })
	awaitC01TestStatusStop(t, done, nil)
}
