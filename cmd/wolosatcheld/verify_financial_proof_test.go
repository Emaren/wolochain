package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/emaren/wolochain/internal/satchelservice"
)

func TestOfflineProofCommandRefusesUntrustedInputsWithoutServiceStartup(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(dir, "malformed.json")
	if err := os.WriteFile(file, []byte(`{"consensus_authenticated":true}`), 0600); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"verify-financial-proof"},
		{"verify-financial-proof", "--config", "/sensitive/production/keyring"},
		{"verify-financial-proof", "--authority", file, "--expected", file, "--proof", file},
		{"verify-financial-proof", "--authority", "/sensitive/operator/authority", "--expected", file, "--proof", file},
	} {
		var out, errout bytes.Buffer
		if code := run(t.Context(), args, &out, &errout); code != 2 || out.Len() != 0 || !strings.Contains(errout.String(), "UNVERIFIABLE") || strings.Contains(errout.String(), "sensitive") {
			t.Fatalf("offline proof failure leaked inputs or entered service: status=%d out=%s err=%s", code, out.String(), errout.String())
		}
	}
}

func TestOfflineProofFileBoundsRejectSymlinkDirectoryWritableAndOversize(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	regular := filepath.Join(dir, "regular.json")
	if err := os.WriteFile(regular, []byte(`{}`), 0600); err != nil {
		t.Fatal(err)
	}
	if b, err := readProofFile(regular, 2); err != nil || string(b) != `{}` {
		t.Fatal("bounded regular proof refused")
	}
	link := filepath.Join(dir, "link.json")
	if err := os.Symlink(regular, link); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{link, dir, "relative.json", filepath.Join(dir, "missing.json")} {
		if _, err := readProofFile(path, 2); err == nil {
			t.Fatalf("unsafe proof path accepted: %s", path)
		}
	}
	if _, err := readProofFile(regular, 1); err == nil {
		t.Fatal("oversized proof accepted")
	}
	if err := os.Chmod(regular, 0666); err != nil {
		t.Fatal(err)
	}
	if _, err := readProofFile(regular, 2); err == nil {
		t.Fatal("mutable operator authority accepted")
	}
}

func TestPermitExpiryDuringTrustAuthenticationCannotReachSign(t *testing.T) {
	inner := &countedBackend{}
	active := true
	b := &permittedBackend{inner: inner, authorize: func(context.Context) bool { return active }, trust: func(context.Context) error { active = false; return nil }}
	if _, err := b.Sign(t.Context(), satchelservice.TransferRequest{}); err != satchelservice.ErrPreSignRefused || inner.signs != 0 || inner.broadcasts != 0 {
		t.Fatal("permit expired during trust I/O reached signer")
	}
}
