// woloreviewerd composes the independent, private 8095 wager reviewer.
// It neither installs a service nor opens a Cosmos custody key or broadcaster.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"syscall"
	"time"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	os.Exit(run(ctx, os.Args[1:], os.Stdout, os.Stderr))
}
func run(ctx context.Context, args []string, out, errout io.Writer) int {
	flags := flag.NewFlagSet("woloreviewerd", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	path := flags.String("config", "", "absolute protected reviewer configuration")
	check := flags.Bool("check", false, "verify config/build/permit only; all source evidence remains unchecked")
	if flags.Parse(args) != nil || flags.NArg() != 0 || *path == "" {
		fmt.Fprintln(errout, "reviewer: configuration flag required")
		return 2
	}
	if os.Geteuid() == 0 || pgEnvironmentPresent(os.Environ()) {
		fmt.Fprintln(errout, "reviewer: isolated process identity required")
		return 2
	}
	c, configDigest, e := loadConfig(*path)
	if e != nil {
		fmt.Fprintln(errout, "reviewer: protected configuration refused")
		return 2
	}
	binaryDigest, e := runningDigest()
	info, ok := debug.ReadBuildInfo()
	if e != nil || !ok || !sourcePinned(info, c.SourceRevision) || binaryDigest != c.BinarySHA256 {
		fmt.Fprintln(errout, "reviewer: exact clean source/build attestation unavailable")
		return 2
	}
	gate := &inputGate{config: c, path: *path, configDigest: configDigest, binaryDigest: binaryDigest, now: time.Now}
	// --check deliberately does not read a private reviewer key, DB credential,
	// source token or journal, and performs no network I/O. It is not admission.
	if *check {
		if !checkPermit(gate) {
			fmt.Fprintln(errout, "reviewer: independent startup permit unavailable")
			return 2
		}
		fmt.Fprintln(out, "reviewer: PERMIT_VALID SOURCES_UNCHECKED; no database, journal, private key, listener or financial activation opened")
		return 0
	}
	service, e := compose(ctx, c, gate)
	if e != nil {
		fmt.Fprintln(errout, "reviewer: HELD protected independent source composition unavailable")
		return 2
	}
	defer service.close()
	stopped := make(chan error, 1)
	go func() { stopped <- service.server.ListenAndServe() }()
	select {
	case e := <-stopped:
		if !errors.Is(e, http.ErrServerClosed) {
			fmt.Fprintln(errout, "reviewer: private listener unavailable")
			return 1
		}
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if service.server.Shutdown(shutdown) != nil {
			_ = service.server.Close()
			fmt.Fprintln(errout, "reviewer: shutdown held pending approvals")
			return 1
		}
	}
	return 0
}
func checkPermit(g *inputGate) bool {
	raw, e := readPermit(g.config.PermitPath)
	var p startupPermit
	return e == nil && strictJSON(raw, &p) == nil && verifyPermit(g.config, g.configDigest, g.binaryDigest, p, g.now())
}
func sourcePinned(info *debug.BuildInfo, revision string) bool {
	if info == nil || !revisionPattern.MatchString(revision) {
		return false
	}
	seen := map[string]bool{}
	settings := map[string]string{}
	for _, s := range info.Settings {
		if s.Key == "vcs" || s.Key == "vcs.revision" || s.Key == "vcs.modified" {
			if seen[s.Key] {
				return false
			}
			seen[s.Key] = true
			settings[s.Key] = s.Value
		}
	}
	return settings["vcs"] == "git" && settings["vcs.revision"] == revision && settings["vcs.modified"] == "false"
}
func runningDigest() (string, error) {
	path, e := os.Executable()
	if e != nil {
		return "", errHeld
	}
	if runtime.GOOS == "linux" {
		path = "/proc/self/exe"
	}
	f, e := os.Open(path)
	if e != nil {
		return "", errHeld
	}
	defer f.Close()
	before, e := f.Stat()
	if e != nil || !before.Mode().IsRegular() || before.Size() <= 0 || before.Size() > 512<<20 {
		return "", errHeld
	}
	h := sha256.New()
	n, e := io.Copy(h, io.LimitReader(f, (512<<20)+1))
	after, statErr := f.Stat()
	if e != nil || statErr != nil || n != before.Size() || after.Size() != before.Size() || !after.ModTime().Equal(before.ModTime()) {
		return "", errHeld
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
