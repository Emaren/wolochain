package satchelservice

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"path/filepath"
	"testing"

	"filippo.io/edwards25519"
)

func TestReserveReviewRejectsTwoForgedIdentityReviewers(t *testing.T) {
	now, review, authority, bank, _, _ := reserveReviewFixture(t)
	identity := make(ed25519.PublicKey, ed25519.PublicKeySize)
	identity[0] = 1
	alias := append(ed25519.PublicKey(nil), identity...)
	alias[31] = 0x80

	// The identity point has two accepted encodings in Go's verifier.
	// R=identity and S=0 verify for both encodings without either private key.
	forgery := make([]byte, ed25519.SignatureSize)
	forgery[0] = 1
	signature := base64.StdEncoding.EncodeToString(forgery)
	review.AccountingReviewerSignature = signature
	review.CustodyReviewerSignature = signature
	authority.AccountingReviewerKey = identity
	authority.CustodyReviewerKey = alias
	if _, err := evaluateBoundReserveReview(now, review, authority, bank); err == nil {
		t.Fatal("two forged signatures under distinct encodings of the identity qualified reserves")
	}
}

func TestAuthorityPublicKeyRejectsMixedOrderPoints(t *testing.T) {
	_, _, authority, _, _, _ := reserveReviewFixture(t)
	valid := authority.AccountingReviewerKey
	point, err := new(edwards25519.Point).SetBytes(valid)
	if err != nil || !ValidAuthorityPublicKey(valid) {
		t.Fatal("generated Ed25519 public key refused", err)
	}
	torsion, err := new(edwards25519.Point).SetBytes(make([]byte, ed25519.PublicKeySize))
	if err != nil {
		t.Fatal(err)
	}
	mixed := new(edwards25519.Point).Add(point, torsion)
	if ValidAuthorityPublicKey(mixed.Bytes()) {
		t.Fatal("canonically encoded mixed-order key was accepted")
	}
}

func TestCustodyConfigRejectsIdentityAuthorityEnrollment(t *testing.T) {
	config, _, _, _ := configTestFixture(t)
	_, _, authority, _, _, _ := reserveReviewFixture(t)
	config.AccountingReviewerKeyHex = hex.EncodeToString(authority.AccountingReviewerKey)
	config.CustodyReviewerKeyHex = hex.EncodeToString(authority.CustodyReviewerKey)
	config.ReserveReviewFile = filepath.Join(filepath.Dir(config.PermitFile), "reserve.json")

	path := filepath.Join(filepath.Dir(config.PermitFile), "config.json")
	load := func(config Config) error {
		t.Helper()
		raw, err := json.Marshal(config)
		if err != nil {
			t.Fatal(err)
		}
		configTestWrite(t, path, raw)
		_, _, err = LoadConfig(path)
		return err
	}
	if err := load(config); err != nil {
		t.Fatal("configuration with genuine separated keys refused", err)
	}
	identity := make(ed25519.PublicKey, ed25519.PublicKeySize)
	identity[0] = 1
	config.AccountingReviewerKeyHex = hex.EncodeToString(identity)
	if err := load(config); err == nil {
		t.Fatal("identity point enrolled as accounting reviewer")
	}
}
