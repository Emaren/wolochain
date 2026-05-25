# Mainnet Genesis Prep

This directory is a scaffold only. It does not contain final genesis.

## Rules

- Final chain ID must be `wolo-1`.
- Final base denom must be `uwolo`.
- Final display denom must be `wolo`.
- Final symbol must be `WOLO`.
- Final decimals must be `6`.
- Final total supply must be `100000000000000uwolo`.
- Final balances must come from a Tony-approved allocation table.
- Testnet balances must not be imported automatically.
- Testnet validator keys must not be reused.
- Testnet settlement signer keys must not be reused.

## Draft Allocation Renderer

Use the read-only helper to validate allocation math and produce a draft JSON artifact under ignored `build/`:

```bash
./scripts/render-mainnet-allocation.sh
```

Default output:

```text
build/mainnet-prep/allocation-draft.json
```

Validation-only mode, used by `./scripts/check-mainnet-prep.sh`:

```bash
./scripts/render-mainnet-allocation.sh --check
```

The helper validates:

- total allocation equals exactly `100000000000000uwolo`
- required columns and row fields are present
- `amount_uwolo` values are non-negative integer strings
- `amount_wolo` matches `amount_uwolo` at 6 decimals
- placeholders are clearly marked and cannot be confused with real addresses
- any future real address must start with `wolo1`
- testnet-only names, services, paths, or stale endpoint hosts do not appear in the allocation rows

The generated JSON is a draft summary only. It is not final genesis and must not be copied into a live chain home.

## Genesis Readiness Checker

Use the readiness checker after rendering the allocation draft:

```bash
./scripts/check-mainnet-genesis-readiness.sh
```

Default output:

```text
build/mainnet-prep/genesis-readiness-report.json
```

The readiness checker confirms:

- allocation math and draft JSON are valid
- chain identity is `wolo-1` / `uwolo` / `wolo` / `WOLO` / `6` / `wolo`
- mainnet service names and ports are present in templates
- all required allocation buckets exist
- placeholder addresses are clearly marked
- stale testnet homes, services, ports, and old Wolo endpoints do not appear in runtime templates

Current placeholder addresses are expected to make `ready_for_genesis` false. That is a safe prep state, not a failure. Use `--strict` only when Tony expects the package to be fully ready for a future genesis-generation step.
