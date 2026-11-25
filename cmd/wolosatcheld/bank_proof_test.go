package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBankProofCommandsFailClosedBeforeCustodyStartup(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(dir, "forged.json")
	if err = os.WriteFile(file, []byte(`{"balance_uwolo":"99999999","consensus_authenticated":true}`), 0600); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"read-bank-proof"}, {"verify-bank-proof"},
		{"read-bank-proof", "--config", "/sensitive/keyring"},
		{"verify-bank-proof", "--authority", file, "--height", "9", "--proof", file},
		{"verify-bank-proof", "--authority", file, "--height", "0", "--proof", file},
		{"verify-bank-proof", "--authority", file, "--height", "9", "--proof", file, "--rpc", "https://caller.example"},
		{"verify-bank-proof", "--authority", file, "--height", "9", "--proof", file, "--account-role", "caller"},
		{"verify-bank-proof", "--authority", file, "--height", "9", "--proof", file, "--account-role", "escrow"},
	} {
		var out, errout bytes.Buffer
		if code := run(t.Context(), args, &out, &errout); code != 2 || out.Len() != 0 || !strings.Contains(errout.String(), "UNVERIFIABLE") || strings.Contains(errout.String(), "sensitive") {
			t.Fatalf("unsafe bank command: code=%d out=%s err=%s", code, out.String(), errout.String())
		}
	}
}
