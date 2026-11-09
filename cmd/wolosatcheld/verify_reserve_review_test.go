package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReserveReviewCommandRefusesUntrustedFilesBeforeStartup(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	claim := filepath.Join(dir, "private-claimed-proof.json")
	if err := os.WriteFile(claim, []byte(`{"spending_authorized":true,"consensus_authenticated":true}`), 0600); err != nil {
		t.Fatal(err)
	}
	writable := filepath.Join(dir, "unprotected-authority.json")
	if err := os.WriteFile(writable, []byte(`{}`), 0644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "redirected-authority.json")
	if err := os.Symlink(claim, link); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"verify-reserve-review"},
		{"verify-reserve-review", "--authority", claim, "--review", claim, "--bank-proof", claim},
		{"verify-reserve-review", "--authority", writable, "--review", claim, "--bank-proof", claim},
		{"verify-reserve-review", "--authority", link, "--review", claim, "--bank-proof", claim},
		{"verify-reserve-review", "--config", "/private/runtime/config.json"},
		{"verify-reserve-review", "--authority", claim, "--review", claim, "--bank-proof", claim, "--rpc", "https://caller.example"},
	} {
		var out, errout bytes.Buffer
		if code := run(t.Context(), args, &out, &errout); code != 2 || out.Len() != 0 ||
			!strings.Contains(errout.String(), "UNVERIFIABLE") || strings.Contains(errout.String(), "private") {
			t.Fatalf("unsafe reserve command: code=%d out=%q err=%q", code, out.String(), errout.String())
		}
	}
}
