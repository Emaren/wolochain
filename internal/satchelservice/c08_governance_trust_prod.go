//go:build !satchel_c08_ci_simulation

package satchelservice

// Real production identity. Never overridden by runtime environment.
var productionC08V3Trust = C08V3Trust{
	OwnerKeySHA:          "f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826",
	SourceCommit:         "ecdeded047610119e57012b095ad8cb5f8019114",
	PolicySHA:            "50910864e6d24236ac3ea98cda1456bedee8d9bf2f9365a8441c6d1e29b41806",
	NoticeSHA:            "b17206bc8b693b1777cd4a3ceef53f81f62f18668a6ebd2c2b8d793bd3146223",
	EnrollmentCommentSHA: "bde91d30f97aaf53650122d33128790187a809b3760210a9e08822ece2395b48",
	ReceiptSHA:           "edcdf664259b0eeec0ae2ed71919bbe5745183864abc2c3b221aa50e83570d19",
}

// Production always checks the exact verified adopted receipt.
func C08TrustRuntimeEligible(Config) bool { return true }
