package satchelservice

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

const (
	c01StatusSocketName    = "status.sock"
	c01ServeFileSchema     = "wolo.c01.zero-funded-serve-config.v1"
	c01CustodyConfigPath   = "/etc/wolo-financial-c01/custody.json"
	c01ReviewerConfigPath  = "/etc/wolo-financial-c01/reviewer.json"
	c01CustodyServePermit  = "/var/lib/wolo-financial-role-state/v1/custody/c01-admission/canonical-serve-permit.json"
	c01ReviewerServePermit = "/var/lib/wolo-financial-role-state/v1/reviewer/c01-admission/canonical-serve-permit.json"
)

func c01ServePathsMatch(role, config, permit string) bool {
	return (role == C01CustodyRole && config == c01CustodyConfigPath && permit == c01CustodyServePermit) ||
		(role == C01ReviewerRole && config == c01ReviewerConfigPath && permit == c01ReviewerServePermit)
}

func readC01ServeConfig(path string) (c01File, C01StartupConfig, error) {
	if path != c01CustodyConfigPath && path != c01ReviewerConfigPath {
		return c01File{}, C01StartupConfig{}, ErrC01NonfundedAdmission
	}
	file, config, err := readC01KeyConfigSchema(path, c01ServeFileSchema)
	if err != nil || !c01ServePathsMatch(config.Role, config.ConfigFile, config.PermitFile) {
		return c01File{}, C01StartupConfig{}, ErrC01NonfundedAdmission
	}
	return file, config, nil
}

// PrepareC01ServeRequest prepares an owner challenge only for a canonical serve
// config. The signed config hash distinguishes it from one-shot admission.
func PrepareC01ServeRequest(ctx context.Context, path string) ([]byte, error) {
	_, config, err := readC01ServeConfig(path)
	if err != nil {
		return nil, err
	}
	return PrepareC01NonfundedStartup(ctx, config)
}

// ServeC01AdmittedKey consumes a fresh C01 permit and proves possession before
// serving only GET /status over the role's private Unix socket. The caller
// must set umask 0177 before startup. Systemd owns RuntimeDirectory cleanup.
func ServeC01AdmittedKey(ctx context.Context, configPath string) error {
	file, config, err := readC01ServeConfig(configPath)
	if err != nil {
		return err
	}
	uid, gid, ok := c01RoleIdentity(file.Role)
	if !ok {
		return ErrC01NonfundedAdmission
	}
	run, err := os.Lstat("/run")
	if err != nil || !run.IsDir() || run.Mode().Perm()&0022 != 0 || !c01OwnedBy(run, 0, 0) {
		return ErrC01NonfundedAdmission
	}
	// The serve config and Linux identity identify exactly one fixed role.
	dir := "/run/" + file.Role + "-c01"
	endpoint, err := newC01StatusEndpoint(dir, uid, gid)
	if err != nil || !endpoint.available() {
		return ErrC01NonfundedAdmission
	}
	receipt, grant, err := checkC01AdmittedKey(ctx, file, config)
	if err != nil {
		return err
	}
	return serveC01Status(ctx, endpoint, receipt, grant.ExpiresAt(), grant.Current)
}

type c01StatusEndpoint struct {
	dir, socket string
	dirInfo     os.FileInfo
	uid, gid    uint32
}

func c01OwnedBy(info os.FileInfo, uid, gid uint32) bool {
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && stat.Uid == uid && stat.Gid == gid
}

func newC01StatusEndpoint(dir string, uid, gid uint32) (c01StatusEndpoint, error) {
	resolved, err := filepath.EvalSymlinks(dir)
	if err != nil || !filepath.IsAbs(dir) || resolved != dir {
		return c01StatusEndpoint{}, ErrC01NonfundedAdmission
	}
	info, err := os.Lstat(dir)
	if err != nil || info.Mode() != os.ModeDir|0700 || !c01OwnedBy(info, uid, gid) {
		return c01StatusEndpoint{}, ErrC01NonfundedAdmission
	}
	return c01StatusEndpoint{
		dir: dir, socket: filepath.Join(dir, c01StatusSocketName),
		dirInfo: info, uid: uid, gid: gid,
	}, nil
}

func (e c01StatusEndpoint) currentDirectory() bool {
	info, err := os.Lstat(e.dir)
	return err == nil && info.Mode() == os.ModeDir|0700 && c01OwnedBy(info, e.uid, e.gid) &&
		os.SameFile(info, e.dirInfo)
}

func (e c01StatusEndpoint) available() bool {
	if !e.currentDirectory() {
		return false
	}
	_, err := os.Lstat(e.socket)
	return errors.Is(err, os.ErrNotExist)
}

func (e c01StatusEndpoint) socketInfo() (os.FileInfo, error) {
	info, err := os.Lstat(e.socket)
	if err != nil || info.Mode() != os.ModeSocket|0600 || !e.currentDirectory() {
		return nil, ErrC01NonfundedAdmission
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != e.uid || stat.Gid != e.gid || stat.Nlink != 1 {
		return nil, ErrC01NonfundedAdmission
	}
	return info, nil
}

func serveC01Status(ctx context.Context, endpoint c01StatusEndpoint, receipt C01NonfundedKeyReceipt, expiresAt time.Time, current func(context.Context) bool) error {
	if ctx == nil || ctx.Err() != nil || current == nil || receipt.FundingAuthorized {
		return ErrC01NonfundedAdmission
	}
	body, err := json.Marshal(receipt)
	if err != nil || !endpoint.available() || !time.Now().Before(expiresAt) || !current(ctx) {
		return ErrC01NonfundedAdmission
	}
	listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: endpoint.socket, Net: "unix"})
	if err != nil {
		return ErrC01NonfundedAdmission
	}
	// Never unlink a pathname that another process could have replaced.
	listener.SetUnlinkOnClose(false)
	defer listener.Close()
	socket, err := endpoint.socketInfo()
	if err != nil || !time.Now().Before(expiresAt) || !current(ctx) {
		return ErrC01NonfundedAdmission
	}
	socketCurrent := func() bool {
		info, err := endpoint.socketInfo()
		return err == nil && os.SameFile(info, socket)
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		if !time.Now().Before(expiresAt) || !current(r.Context()) || !socketCurrent() {
			http.Error(w, "C01_ZERO_FUNDS_STATUS_UNAVAILABLE", http.StatusServiceUnavailable)
			return
		}
		if r.RequestURI != "/status" {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodGet || r.Body != http.NoBody {
			w.Header().Set("Allow", http.MethodGet)
			http.Error(w, "C01_STATUS_GET_ONLY", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	})
	server := &http.Server{
		Handler:                      handler,
		DisableGeneralOptionsHandler: true,
		BaseContext: func(net.Listener) context.Context {
			return ctx
		},
		ReadHeaderTimeout: time.Second,
		ReadTimeout:       time.Second,
		WriteTimeout:      time.Second,
		IdleTimeout:       time.Second,
		MaxHeaderBytes:    4096,
	}
	server.SetKeepAlivesEnabled(false)
	defer server.Close()
	done := make(chan error, 1)
	go func() { done <- server.Serve(listener) }()
	deadline := time.NewTimer(time.Until(expiresAt))
	defer deadline.Stop()
	check := time.NewTicker(100 * time.Millisecond)
	defer check.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-deadline.C:
			return nil
		case <-check.C:
			if !socketCurrent() {
				return ErrC01NonfundedAdmission
			}
			if !current(ctx) {
				return nil
			}
		case <-done:
			return ErrC01NonfundedAdmission
		}
	}
}
