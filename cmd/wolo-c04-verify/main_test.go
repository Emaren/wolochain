package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testHash = "D5B4CFAA5E9063F8342EA9E2B6119FCFF28DEE20B2E1DD6803944933B237D699"
const testID = "aoe2-original-100-wolo"

func makeRequest(t *testing.T, status string) (string, string, string) {
	t.Helper()
	root := t.TempDir()
	dir := filepath.Join(root, "requests")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	x := map[string]any{"request": map[string]any{
		"request_id": testID, "to_address": "wolo1originalrecipient", "amount_uwolo": "100000000",
		"memo": "original immutable memo", "signer_role": "escrow"},
		"response": map[string]any{"request_id": testID, "status": status, "tx_hash": testHash,
			"signer_address": "wolo1originalescrow", "signer_role": "escrow"}}
	raw, err := json.Marshal(x)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, testID+".json")
	if err = os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256([]byte(testID))
	return root, hex.EncodeToString(sum[:]), path
}
func TestAcceptedRequestCorrelatesExactOriginalBytes(t *testing.T) {
	root, id, _ := makeRequest(t, "accepted")
	x, err := scan(root, id, testHash)
	if err != nil {
		t.Fatal(err)
	}
	if x.AmountUWolo != "100000000" || x.Sender != "wolo1originalescrow" || x.Recipient != "wolo1originalrecipient" || x.Memo != "original immutable memo" {
		t.Fatal("original identity mismatch")
	}
}
func TestFailedOrModifiedRequestCannotAuthorizeRecovery(t *testing.T) {
	for _, status := range []string{"confirmed", "failed", "pending", "retryable"} {
		t.Run(status, func(t *testing.T) {
			root, id, _ := makeRequest(t, status)
			if _, err := scan(root, id, testHash); err == nil {
				t.Fatal("accepted non-accepted state")
			}
		})
	}
	root, id, _ := makeRequest(t, "accepted")
	if _, err := scan(root, id, strings.Repeat("A", 64)); err == nil {
		t.Fatal("mismatched transaction")
	}
	if _, err := scan(root, strings.Repeat("0", 64), testHash); err == nil {
		t.Fatal("nonexistent original ID")
	}
	if _, err := scan(root, "NOT_HASH", testHash); err == nil {
		t.Fatal("invalid fingerprint")
	}
}
func TestOriginalRequestCannotFollowSymlink(t *testing.T) {
	root, id, path := makeRequest(t, "accepted")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Remove(path); err != nil {
		t.Fatal(err)
	}
	external := filepath.Join(t.TempDir(), "private.json")
	if err = os.WriteFile(external, raw, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink(external, path); err != nil {
		t.Fatal(err)
	}
	if _, err = scan(root, id, testHash); err == nil {
		t.Fatal("accepted symlink")
	}
}
func TestOriginalRequestCannotBeOversizedOrSpoofed(t *testing.T) {
	root, id, path := makeRequest(t, "accepted")
	if err := os.WriteFile(path, []byte(strings.Repeat("x", 1048577)), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := scan(root, id, testHash); err == nil {
		t.Fatal("accepted oversized request")
	}
	root, id, path = makeRequest(t, "accepted")
	raw, _ := os.ReadFile(path)
	changed := strings.Replace(string(raw), `"amount_uwolo":"100000000"`, `"amount_uwolo":"101000000"`, 1)
	if err := os.WriteFile(path, []byte(changed), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := scan(root, id, testHash); err == nil {
		t.Fatal("accepted different amount")
	}
}
