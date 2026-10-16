package satchel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strings"
	"testing"
)

func TestCapabilityAlwaysUnavailable(t *testing.T) {
	for _, capability := range []Capability{{}, CurrentCapability()} {
		if capability.Available() || capability.AcceptingDeposits() ||
			capability.ExecutionReady() || capability.CreditAuthorized() {
			t.Fatal("zero or current capability granted financial authority")
		}
	}
	var forged Capability
	if err := json.Unmarshal([]byte(`{"available":true,"accepting_deposits":true,"execution_ready":true,"credit_authorized":true,"vault_address":"wolo1claimed"}`), &forged); err != nil {
		t.Fatal(err)
	}
	if forged.Available() || forged.AcceptingDeposits() || forged.ExecutionReady() || forged.CreditAuthorized() {
		t.Fatal("caller JSON fabricated financial authority")
	}
}

func TestCapabilityIgnoresEnvironmentCertification(t *testing.T) {
	before, err := json.Marshal(CurrentCapability())
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{
		"WOLO_SATCHEL_CERTIFIED", "WOLO_SATCHEL_CUSTODY_APPROVED",
		"WOLO_SATCHEL_EXECUTION_READY", "WOLO_SATCHEL_ACCEPTING_DEPOSITS",
		"WOLO_SATCHEL_VAULT_ADDRESS", "WOLO_SATCHEL_SIGNER_ROLE",
		"LIVE_EXECUTOR_IMPLEMENTED",
	} {
		t.Setenv(name, "true")
	}
	after, err := json.Marshal(CurrentCapability())
	if err != nil {
		t.Fatal(err)
	}
	if string(before) != string(after) {
		t.Fatal("environment changed source custody authority")
	}
}

func TestCapabilityJSONContractAndIsolation(t *testing.T) {
	want := `{"version":"war-satchel-custody-v1","chain_id":"wolo-1","denom":"uwolo","signer_role":"satchel-vault","available":false,"accepting_deposits":false,"execution_ready":false,"credit_authorized":false,"blockers":["dedicated_vault_and_independent_signer_custody_unverified","independent_chain_proof_adapter_unimplemented","reserve_provenance_and_complete_liabilities_unverified","durable_global_receipt_claim_and_atomic_credit_unimplemented","idempotent_withdrawal_and_crash_recovery_unimplemented","protected_release_and_activation_unapproved"]}`
	got, err := json.Marshal(CurrentCapability())
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != want {
		t.Fatalf("capability JSON contract changed:\ngot  %s\nwant %s", got, want)
	}
	if reflect.TypeOf(Capability{}).NumField() != 0 {
		t.Fatal("capability acquired caller-mutable state")
	}
	blockers := CurrentCapability().Blockers()
	blockers[0] = "claimed_certified"
	if CurrentCapability().Blockers()[0] == "claimed_certified" {
		t.Fatal("caller mutated global authority blockers")
	}
}

func TestKnownRoleCatalogMatchesRegisteredWallets(t *testing.T) {
	document, err := os.ReadFile(filepath.Join("..", "..", "docs", "mainnet-wallets.md"))
	if err != nil {
		t.Fatal(err)
	}
	// Read the source registry independently, so adding a documented role wallet
	// without excluding it from Satchel candidates fails this contract.
	pattern := regexp.MustCompile("(?m)^\\| ([^|]+) \\| `(wolo1[a-z0-9]+)` \\|")
	registered := pattern.FindAllSubmatch(document, -1)
	if len(registered) < 23 {
		t.Fatalf("registered wallet table missing or unexpectedly incomplete: %d", len(registered))
	}
	for _, row := range registered {
		label, address := strings.TrimSpace(string(row[1])), string(row[2])
		t.Run(label, func(t *testing.T) {
			if !IsKnownRoleAddress(address) || !IsKnownRoleAddress(" \t"+strings.ToUpper(address)+"\n") {
				t.Fatalf("registered role wallet escaped exclusion: %s", label)
			}
		})
	}
}

func TestFounderRewardsPayoutExcluded(t *testing.T) {
	const founderPayout = "wolo1tg04m57e52evgzjkn9ruwwkz626pfv9qfv27wy"
	if !IsKnownRoleAddress(founderPayout) {
		t.Fatal("protected 8093 founder payout signer escaped candidate exclusion")
	}
	if CurrentCapability().Available() || CurrentCapability().AcceptingDeposits() {
		t.Fatal("existing founder payout custody granted Satchel authority")
	}
}

func TestUnknownAddressNeverCertifiesCustody(t *testing.T) {
	for _, address := range []string{"", "invalid", "wolo1unverifiedcandidate"} {
		if IsKnownRoleAddress(address) {
			t.Fatalf("unexpected catalog member: %q", address)
		}
		if CurrentCapability().Available() || CurrentCapability().AcceptingDeposits() {
			t.Fatal("absence from catalog certified custody")
		}
	}
}
