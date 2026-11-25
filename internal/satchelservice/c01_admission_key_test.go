package satchelservice

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
)

func TestC01KeyConfigurationBindsRoleAndEnrolledPublicKey(t *testing.T) {
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "admission.json")
	check := func(file c01File, allowed bool) {
		t.Helper()
		raw, err := json.Marshal(file)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
		_, config, err := readC01KeyConfig(path)
		if allowed && (err != nil || config.ConfigSHA256 != c01Digest(raw)) {
			t.Fatal("qualified configuration not bound to its exact bytes")
		}
		if !allowed && err == nil {
			t.Fatal("wrong key or role accepted")
		}
	}

	reviewer := ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize))
	base := c01File{
		Schema: c01FileSchema, Role: "wolo-reviewer",
		KeyFingerprintSHA256: c01Digest(reviewer.Public().(ed25519.PublicKey)),
		C08ReceiptFile:       "/protected/c08.json", C08OwnerPublicFile: "/protected/c08.bin",
		PermitFile: "/protected/permit.json",
	}
	check(base, true)
	native := sdksecp.GenPrivKey().PubKey()
	vault, err := backendPubAddress(native)
	if err != nil {
		t.Fatal(err)
	}
	base.Custody = &c01CustodyKey{Vault: vault, PublicKeyHex: hex.EncodeToString(native.Bytes()), KeyName: "fixture"}
	check(base, false)
	base.Role = "wolo-satchel"
	check(base, false)
	base.KeyFingerprintSHA256 = c01Digest(native.Bytes())
	check(base, true)
	base.Custody.Vault = "not-the-derived-vault"
	check(base, false)
}
