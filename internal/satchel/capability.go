// Package satchel defines dormant War Satchel custody contracts. It has no
// runtime adapter, credit writer, signer access, or transaction execution.
package satchel

import (
	"encoding/json"
	"strings"
)

// Capability is an immutable, unavailable authority value. Its zero value is
// equally closed. Evidence validators in this package cannot promote it.
type Capability struct{}

// CurrentCapability reports source authority, not operator certification. A
// separate verified vault and signing boundary have not been established.
func CurrentCapability() Capability { return Capability{} }

func (Capability) Version() string         { return "war-satchel-custody-v1" }
func (Capability) ChainID() string         { return "wolo-1" }
func (Capability) Denom() string           { return "uwolo" }
func (Capability) SignerRole() string      { return "satchel-vault" }
func (Capability) Available() bool         { return false }
func (Capability) AcceptingDeposits() bool { return false }
func (Capability) ExecutionReady() bool    { return false }
func (Capability) CreditAuthorized() bool  { return false }

// Blockers returns a fresh list. None can be satisfied by an environment flag,
// an unverified candidate address, or a successful pure evidence fixture.
func (Capability) Blockers() []string {
	return []string{
		"dedicated_vault_and_independent_signer_custody_unverified",
		"independent_chain_proof_adapter_unimplemented",
		"reserve_provenance_and_complete_liabilities_unverified",
		"durable_global_receipt_claim_and_atomic_credit_unimplemented",
		"idempotent_withdrawal_and_crash_recovery_unimplemented",
		"protected_release_and_activation_unapproved",
	}
}

// MarshalJSON deliberately has no vault address or financial execution input.
func (c Capability) MarshalJSON() ([]byte, error) {
	return json.Marshal(struct {
		Version           string   `json:"version"`
		ChainID           string   `json:"chain_id"`
		Denom             string   `json:"denom"`
		SignerRole        string   `json:"signer_role"`
		Available         bool     `json:"available"`
		AcceptingDeposits bool     `json:"accepting_deposits"`
		ExecutionReady    bool     `json:"execution_ready"`
		CreditAuthorized  bool     `json:"credit_authorized"`
		Blockers          []string `json:"blockers"`
	}{c.Version(), c.ChainID(), c.Denom(), c.SignerRole(), c.Available(),
		c.AcceptingDeposits(), c.ExecutionReady(), c.CreditAuthorized(), c.Blockers()})
}

// IsKnownRoleAddress excludes every registered address in mainnet-wallets.md,
// including retired wallets and named holders. False only means the address is
// absent from this catalog; it never certifies a valid or independent vault.
func IsKnownRoleAddress(address string) bool {
	switch strings.ToLower(strings.TrimSpace(address)) {
	case "wolo1r8kvt7me33rsv9ldaczj03xjrld4yumx0c0jkg", // Founder Cold
		"wolo1hlfvzuv4dc46ngvh3zlteuegx0xga20hj20zd2", // Community Treasury
		"wolo1kwsmr9nzujwul6wmu4hqr90lel4ca4uy3l06en", // DEX Liquidity Reserve
		"wolo12c009ektp58rr0gkjz3nk8f4kgvfpfzwfk86l3", // Faucet Growth Reserve
		"wolo1nalsh7y0hzp33j996c90yxqgerxxvgpqtumfjt", // Validator Ops
		"wolo1wue7vyque2pssskgdrww0fcadlq9ps6mtn605e", // Founder Operating
		"wolo1dmj5dnm7g9hmj005yzy5e5xcygudyt7wxzpxjq", // Ecosystem Bounties
		"wolo1dshyzxffd0jj39k7gj9tq9hgsx96ylxamyp5g0", // Faucet Hot Wallet
		"wolo1a53udazy8ayufvy0s434pfwjcedzqv347h8lzn", // IBC Escrow
		"wolo10zspyrrphzctrpysh6l9dsqj4wcwmj3tk660sz", // Jim
		"wolo1n0yg6ltqxl05ljaqftvvtgec5qavf9a3uh090h", // Julio Alvarez
		"wolo1fl48vsnmsdzcv85q5d2q4z5ajdha8yu3aqv4s2", // Validator Ops Reserve
		"wolo1mcmckkr360n47wyc408xmlsv4tzw95kkczvfp9", // Sniper
		"wolo18v9ugfdrnz2ll2ah5z2yqzm5kzlg3e7l7jy6rn", // Staking Wallet
		"wolo1rmr39nd5gnnv5y5f66qtq367xfwvx9jt5w7ucr", // Retired Staking Wallet
		"wolo1m8qzq92hkktgqp47aewzylkatk6c22vc8c4vgj", // Relayer Gas
		"wolo1t4jq7wd4x030t9f0yfqfq74pt4pmaep5nu67y4", // Legacy Bet Escrow
		"wolo1cy04t5af0mr9d8n6rrzgr8e9j4vuf42nfg02q5", // Retired Bet Payout
		"wolo1zfa9ssu2gpgqg7yzvhmjt4w66mza07qr2a4rwu", // Bet Payout Signer
		"wolo1tg04m57e52evgzjkn9ruwwkz626pfv9qfv27wy", // Founder Rewards Payout Signer (8093)
		"wolo1zygwt232ymc4h2g52yvkntffhmd5alx2kglw7p", // Bet Escrow Signer
		"wolo1jv65s3grqf6v6jl3dp4t6c9t9rk99cd80ypxqz", // Faucet/Test Wallet 10
		"wolo1jx4n3n2ey6uzfq28kplkmpd2am98xsmcn0nerx": // Legacy faucetgrowth
		return true
	default:
		return false
	}
}
