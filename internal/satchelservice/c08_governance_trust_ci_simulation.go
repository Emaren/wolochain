//go:build satchel_c08_ci_simulation

package satchelservice

// This source exists only in the explicitly tagged isolated SDK subprocess
// executable built for CI. It never appears in the production signer binary.
// Test identities are ephemerally injected into this disposable process.
import (
	"net/url"
	"os"
	"strings"
)

var productionC08V3Trust = C08V3Trust{
	OwnerKeySHA:          os.Getenv("SATCHEL_C08_CI_OWNER_SHA256"),
	SourceCommit:         "ecdeded047610119e57012b095ad8cb5f8019114",
	PolicySHA:            "50910864e6d24236ac3ea98cda1456bedee8d9bf2f9365a8441c6d1e29b41806",
	NoticeSHA:            "b17206bc8b693b1777cd4a3ceef53f81f62f18668a6ebd2c2b8d793bd3146223",
	EnrollmentCommentSHA: "bde91d30f97aaf53650122d33128790187a809b3760210a9e08822ece2395b48",
	ReceiptSHA:           os.Getenv("SATCHEL_C08_CI_RECEIPT_SHA256"),
}

// Even a mistakenly tagged test executable cannot qualify an ordinary
// production/mainnet config. It is bounded to an exact isolated test
// authority, explicit CI-mode process, and THREE numeric IPv4 loopback peers.
func C08TrustRuntimeEligible(c Config) bool {
	if os.Getenv("SATCHEL_C08_CI_EXPLICIT_ISOLATED") !=
		"disposable-c01-executable-sdk-ci-no-real-chain" ||
		c.TrustAnchor.EvidenceReference !=
			"isolated-custody-issuer-test-validator-only" ||
		len(productionC08V3Trust.OwnerKeySHA) != 64 ||
		len(productionC08V3Trust.ReceiptSHA) != 64 {
		return false
	}
	for _, endpoint := range []string{c.RPC, c.REST, c.WitnessRPC} {
		u, err := url.Parse(endpoint)
		if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" ||
			u.Port() == "" || u.User != nil || u.RawQuery != "" ||
			(u.Path != "" && u.Path != "/") || u.Fragment != "" ||
			strings.Contains(u.Host, "@") {
			return false
		}
	}
	return true
}
