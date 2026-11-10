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

func TestC01ServeProfilePinsRoleAndBothPaths(t *testing.T) {
	for _, profile := range []struct {
		role, config, permit string
	}{
		{C01CustodyRole, "/etc/wolo-financial-c01/custody.json",
			"/var/lib/wolo-financial-role-state/v1/custody/c01-admission/canonical-serve-permit.json"},
		{C01ReviewerRole, "/etc/wolo-financial-c01/reviewer.json",
			"/var/lib/wolo-financial-role-state/v1/reviewer/c01-admission/canonical-serve-permit.json"},
	} {
		if !c01ServePathsMatch(profile.role, profile.config, profile.permit) {
			t.Fatalf("canonical %s paths refused", profile.role)
		}
		if c01ServePathsMatch(profile.role, profile.config+".old", profile.permit) ||
			c01ServePathsMatch(profile.role, profile.config, profile.permit+".old") ||
			c01ServePathsMatch(profile.role, profile.config, strings.Replace(profile.permit, "/c01-admission/", "/c01-admission/./", 1)) ||
			c01ServePathsMatch("other-role", profile.config, profile.permit) {
			t.Fatalf("alternate %s scope accepted", profile.role)
		}
	}
	if c01ServePathsMatch(C01ReviewerRole, c01CustodyConfigPath, c01ReviewerServePermit) ||
		c01ServePathsMatch(C01CustodyRole, c01CustodyConfigPath, c01ReviewerServePermit) {
		t.Fatal("cross-role config or permit accepted")
	}
}

func TestC01ServeRejectsOneShotAuthorizationEvenOnSameBinary(t *testing.T) {
	f := makeC01Fixture(t)
	file := c01File{
		Schema: c01FileSchema, Role: C01ReviewerRole,
		KeyFingerprintSHA256: f.c.KeyFingerprintSHA256,
		C08ReceiptFile:       f.c.C08ReceiptFile,
		C08OwnerPublicFile:   f.c.C08OwnerPublicFile,
		PermitFile:           f.c.PermitFile,
	}
	write := func() {
		t.Helper()
		raw, err := json.Marshal(file)
		if err != nil {
			t.Fatal(err)
		}
		c01WriteTestFile(t, f.c.ConfigFile, raw)
	}
	write()
	_, oneShot, err := readC01KeyConfig(f.c.ConfigFile)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := readC01KeyConfigSchema(f.c.ConfigFile, c01ServeFileSchema); err == nil {
		t.Fatal("one-shot config accepted by the serve schema")
	}
	f.request[0], f.request[4] = oneShot.Role, oneShot.ConfigSHA256
	f.writePermit(t, f.owner, c01StartupDomain, f.request)
	if _, _, _, err := verifyC01Startup(oneShot, f.revision, f.binary, f.trust, f.now); err != nil {
		t.Fatalf("original one-shot signature refused: %v", err)
	}

	// Only the schema changes. The same role, source, executable, public key,
	// policy and permit location cannot make the old signature reusable.
	file.Schema = c01ServeFileSchema
	write()
	_, serve, err := readC01KeyConfigSchema(f.c.ConfigFile, c01ServeFileSchema)
	if err != nil || oneShot.ConfigSHA256 == serve.ConfigSHA256 {
		t.Fatalf("serve schema did not establish a distinct signed config: %v", err)
	}
	if _, _, err := readC01KeyConfig(f.c.ConfigFile); err == nil {
		t.Fatal("serve config accepted by one-shot admission")
	}
	if _, _, err := readC01ServeConfig(f.c.ConfigFile); !errors.Is(err, ErrC01NonfundedAdmission) {
		t.Fatal("serve accepted a noncanonical config path")
	}
	if _, _, _, err := verifyC01Startup(serve, f.revision, f.binary, f.trust, f.now); err == nil {
		t.Fatal("one-shot signature admitted serve")
	}

	f.request[4] = serve.ConfigSHA256
	f.writePermit(t, f.owner, c01StartupDomain, f.request)
	if _, _, _, err := verifyC01Startup(serve, f.revision, f.binary, f.trust, f.now); err != nil {
		t.Fatalf("new signature over exact serve config refused: %v", err)
	}
}
