package satchelservice

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func c08V3Fixture(t *testing.T) ([]byte, C08V3Trust, map[string]any, func(map[string]any) map[string]any) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	public := elliptic.Marshal(elliptic.P256(), key.X, key.Y)
	trust := C08V3Trust{
		OwnerKeySHA: c08HexSHA(public), SourceCommit: strings.Repeat("a", 40),
		PolicySHA: strings.Repeat("b", 64), NoticeSHA: strings.Repeat("c", 64),
		EnrollmentCommentSHA: strings.Repeat("d", 64),
	}
	q := map[string]any{
		"schema":                        c08V3RequestSchema,
		"chain_id":                      "wolo-1",
		"operation":                     "one-human-source-bound-policy-adoption-zero-funds",
		"source_commit":                 trust.SourceCommit,
		"policy_sha256":                 trust.PolicySHA,
		"owner_public_x963_sha256":      trust.OwnerKeySHA,
		"historical_ed25519_der_sha256": "00d08c27271cf484f684059e83478d9522765c374101d5c4e8ed29e266e500ed",
		"historical_owner_key_signed_this_request": false,
		"key_enrollment_comment_id":                json.Number("6727529299"),
		"key_enrollment_comment_body_sha256":       trust.EnrollmentCommentSHA,
		"public_notice_url":                        "https://github.com/Emaren/wolochain/issues/184",
		"public_notice_body_sha256":                trust.NoticeSHA,
		"owner_human_count":                        json.Number("1"),
		"independent_human_review_claimed":         false,
		"legacy_8092_fallback_allowed":             false,
		"historical_claims_waived":                 false,
		"financial_release_authorized":             false,
		"standing_funded_allowance_uwolo":          json.Number("0"),
		"future_c09_canary_ceiling_uwolo":          json.Number("1000000"),
		"c09_transaction_signature_present":        false,
		"nonce":                                    "0123456789abcdef0123456789abcdef",
		"not_before":                               "2026-11-08T22:10:00Z",
		"expires_at":                               "2026-11-08T22:30:00Z",
	}
	signed := func(request map[string]any) map[string]any {
		t.Helper()
		encoded, err := c08Canonical(request)
		if err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(append([]byte(c08V3SignatureDomain), encoded...))
		signature, err := ecdsa.SignASN1(rand.Reader, key, digest[:])
		if err != nil {
			t.Fatal(err)
		}
		packet := map[string]any{"schema": c08V3PacketSchema, "request": request,
			"signature_der_b64": base64.StdEncoding.EncodeToString(signature)}
		packetRaw, err := c08Canonical(packet)
		if err != nil {
			t.Fatal(err)
		}
		return map[string]any{
			"schema":                        c08V3ReceiptSchema,
			"status":                        "PASS_C08_ONE_HUMAN_KEYCHAIN_GOVERNANCE_ADOPTED_NO_FUNDS",
			"source_commit":                 trust.SourceCommit,
			"policy_sha256":                 trust.PolicySHA,
			"owner_public_x963_sha256":      trust.OwnerKeySHA,
			"signed_packet":                 packet,
			"signed_packet_sha256":          c08HexSHA(packetRaw),
			"adopted_utc":                   "2026-11-08T22:11:12Z",
			"public_notice_url":             "https://github.com/Emaren/wolochain/issues/184",
			"key_enrollment_comment_id":     json.Number("6727529299"),
			"historic_ed25519_key_not_used": true,
			"login_keychain_software_key_not_secure_enclave": true,
			"single_human_owner_disclosed":                   true,
			"independent_human_review_claimed":               false,
			"standing_funded_allowance_uwolo":                json.Number("0"),
			"future_c09_canary_ceiling_uwolo":                json.Number("1000000"),
			"financial_release_authorized":                   false,
			"c09_permit_issued":                              false,
		}
	}
	return public, trust, q, signed
}
func c08V3Raw(t *testing.T, r map[string]any) []byte {
	t.Helper()
	b, err := c08Canonical(r)
	if err != nil {
		t.Fatal(err)
	}
	return append(b, '\n')
}
func c08V3Clone(t *testing.T, q map[string]any) map[string]any {
	t.Helper()
	raw := c08V3Raw(t, q)
	d := json.NewDecoder(strings.NewReader(string(raw)))
	d.UseNumber()
	var out map[string]any
	if err := d.Decode(&out); err != nil {
		t.Fatal(err)
	}
	return out
}
func TestC08V3NativeOwnerReceiptVerification(t *testing.T) {
	pub, trust, q, sign := c08V3Fixture(t)
	good := sign(q)
	if err := verifyC08KeychainV3Receipt(pub, c08V3Raw(t, good), trust); err != nil {
		t.Fatalf("real P256 signed policy refused: %v", err)
	}
	t.Run("bad_public", func(t *testing.T) {
		alter := append([]byte(nil), pub...)
		alter[len(alter)-1] ^= 1
		if verifyC08KeychainV3Receipt(alter, c08V3Raw(t, good), trust) == nil {
			t.Fatal("wrong public key")
		}
	})
	for _, tc := range []struct {
		name, key string
		value     any
	}{
		{"no_legacy_fallback", "legacy_8092_fallback_allowed", true},
		{"no_liability_waiver", "historical_claims_waived", true},
		{"no_fake_second_human", "independent_human_review_claimed", true},
		{"zero_fund", "standing_funded_allowance_uwolo", json.Number("1")},
		{"one_wolo_ceiling", "future_c09_canary_ceiling_uwolo", json.Number("1000001")},
		{"no_c09_signature", "c09_transaction_signature_present", true},
		{"source_pinned", "source_commit", strings.Repeat("f", 40)},
		{"notice_pinned", "public_notice_body_sha256", strings.Repeat("e", 64)},
		{"wrong_chain", "chain_id", "wolo-2"},
		{"nonce_required", "nonce", strings.Repeat("0", 32)},
		{"not_expired", "expires_at", "2026-11-08T22:11:00Z"},
		{"historical_key_disclosure", "historical_owner_key_signed_this_request", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			bad := c08V3Clone(t, q)
			bad[tc.key] = tc.value
			receipt := sign(bad) // adversary even has a valid test signing key
			if verifyC08KeychainV3Receipt(pub, c08V3Raw(t, receipt), trust) == nil {
				t.Fatalf("invalid signed request %s accepted", tc.key)
			}
		})
	}
	t.Run("forged_receipt", func(t *testing.T) {
		r := c08V3Clone(t, good)
		r["financial_release_authorized"] = true
		if verifyC08KeychainV3Receipt(pub, c08V3Raw(t, r), trust) == nil {
			t.Fatal("funded receipt accepted")
		}
	})
	t.Run("duplicate_json", func(t *testing.T) {
		raw := c08V3Raw(t, good)
		raw = append([]byte(`{"schema":"not-trusted",`), raw[1:]...)
		if verifyC08KeychainV3Receipt(pub, raw, trust) == nil {
			t.Fatal("duplicate key accepted")
		}
	})
	t.Run("trailing_json", func(t *testing.T) {
		if verifyC08KeychainV3Receipt(pub, append(c08V3Raw(t, good), []byte("{}")...), trust) == nil {
			t.Fatal("trailing body accepted")
		}
	})
}
func TestC08V3OwnerPhysicalReceiptWhenRequested(t *testing.T) {
	root := os.Getenv("AOE2WAR_C08_OWNER_RECEIPT_ROOT")
	if root == "" {
		t.Skip("owner-private physical receipt not provided to public CI")
	}
	pub, err := os.ReadFile(filepath.Join(root, "public-owner-key-x963.bin"))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(root, "adopted-governance-v3.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyC08KeychainV3Receipt(pub, raw); err != nil {
		t.Fatal(err)
	}
	t.Log("PASS_C08_EXACT_SIGNED_OWNER_RECEIPT_GO_NATIVE")
}
