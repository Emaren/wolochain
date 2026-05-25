# WoloChain Mainnet Genesis Allocation Template

This is a planning template only. It is not a final allocation table and must not be used to launch mainnet without Tony's explicit review.

Testnet balances do not automatically migrate to mainnet.

## Supply Target

- Total supply: `100000000 WOLO`
- Base amount: `100000000000000uwolo`
- Decimals: `6`
- Base denom: `uwolo`
- Display denom: `wolo`

All final genesis balances must sum exactly to `100000000000000uwolo`.

## Allocation Buckets

These buckets are suggested planning categories, not final truth.

| Bucket | Example WOLO | Example uwolo | Example % | Genesis | Notes |
| --- | ---: | ---: | ---: | --- | --- |
| Operator / validator reserve | `10000000` | `10000000000000` | `10%` | yes | Funds validator self-delegation, node operations, fees, and emergency ops. |
| Community treasury | `25000000` | `25000000000000` | `25%` | yes | Long-lived community treasury. Prefer cold or multisig custody. |
| Staking / rewards | `15000000` | `15000000000000` | `15%` | yes | Reward programs and future staking incentive plans. |
| Tournaments | `10000000` | `10000000000000` | `10%` | yes | Tournament funding controlled outside WoloChain business logic. |
| Watcher / player rewards | `10000000` | `10000000000000` | `10%` | yes | Reward pool for app-owned player and watcher programs. |
| Liquidity / Osmosis seed | `5000000` | `5000000000000` | `5%` | yes | Held until IBC and Osmosis prep are complete. Do not create liquidity during launch prep. |
| Future ecosystem | `15000000` | `15000000000000` | `15%` | yes | Partnerships, future integrations, grants, or ecosystem growth. |
| Contributor / early tester allocation | `5000000` | `5000000000000` | `5%` | yes | Only after Tony approves eligibility and addresses. Not a testnet balance migration. |
| Unallocated reserve | `5000000` | `5000000000000` | `5%` | yes | Cold reserve for future decisions. |
| Total | `100000000` | `100000000000000` | `100%` | yes | Must match fixed supply exactly. |

## CSV Template

```csv
bucket,label,address,amount_wolo,amount_uwolo,custody,genesis,notes
operator_validator_reserve,Operator validator reserve,wolo1_REPLACE_ME,10000000,10000000000000,hot-or-warm,yes,Includes validator self-delegation and operating fees
community_treasury,Community treasury,wolo1_REPLACE_ME,25000000,25000000000000,cold-or-multisig,yes,Final address required before genesis
staking_rewards,Staking rewards,wolo1_REPLACE_ME,15000000,15000000000000,cold-or-multisig,yes,Program logic remains app or governance owned
tournaments,Tournaments,wolo1_REPLACE_ME,10000000,10000000000000,cold-or-multisig,yes,AoE2 apps own tournament eligibility
watcher_player_rewards,Watcher/player rewards,wolo1_REPLACE_ME,10000000,10000000000000,warm,yes,AoE2 apps own eligibility
liquidity_osmosis_seed,Liquidity/Osmosis seed,wolo1_REPLACE_ME,5000000,5000000000000,cold,yes,Do not transfer to Osmosis until IBC plan is approved
future_ecosystem,Future ecosystem,wolo1_REPLACE_ME,15000000,15000000000000,cold-or-multisig,yes,Future integrations and grants
contributors_early_testers,Contributor/early tester allocation,wolo1_REPLACE_ME,5000000,5000000000000,cold-or-multisig,yes,Not automatic testnet migration
unallocated_reserve,Unallocated reserve,wolo1_REPLACE_ME,5000000,5000000000000,cold,yes,Hold until future decision
```

## Genesis Rules

- Every address must use the `wolo` bech32 prefix.
- No `cosmos1...` addresses are allowed.
- No testnet validator, payout, escrow, faucet, or app-side claim address should be copied automatically.
- No mnemonic belongs in git, docs, screenshots, shell history, or issue trackers.
- The final allocation file should be generated from a reviewed source table.
- The final genesis should be validated by a script before any service starts.

## Validator Self-Delegation

The validator/operator reserve must include enough WOLO for:

- validator self-delegation in the gentx
- launch transaction fees
- emergency governance or staking operations
- a reserve floor that keeps the validator account usable after launch

The exact self-delegation amount is a launch decision.

