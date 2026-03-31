# WoloChain

**WoloChain** is a fixed-supply Cosmos-based blockchain for the **AoE2HDBets** ecosystem.

Its job is simple:

- hold scarce **WOLO** balances
- support transfers and payouts
- act as the money rail for AoE2HDBets
- stay brutally clean and understandable

WoloChain v1 is **not** trying to be everything at once.

It is **not** launching with:

- on-chain betting logic
- on-chain faucet logic
- privacy features
- rich-list theater
- smart contracts on day one
- gimmicky tokenomics

The chain owns scarcity and settlement.  
AoE2HDBets owns the game logic, faucet rules, premium entitlements, rewards UX, and anti-abuse controls.

---

## Canonical v1 identity

- **Chain name:** `WoloChain`
- **Binary:** `wolochaind`
- **Chain ID:** `wolo-1`
- **Node home:** `~/.wolochain`
- **Address prefix:** `wolo`
- **Address format:** `wolo1...`
- **Base denom:** `uwolo`
- **Display denom:** `wolo`
- **Symbol:** `WOLO`
- **Decimals:** `6`

---

## Monetary policy

WoloChain is being built around a simple promise:

- **Max supply:** `100,000,000 WOLO`
- **Base units:** `100,000,000,000,000 uwolo`
- **Inflation:** `0`
- **Post-genesis minting:** disabled
- **Burning:** disabled
- **No hidden supply tricks**
- **No chicanery**

All supply is intended to exist at genesis and remain fixed.

---

## v1 utility

WOLO v1 is for:

- betting balances
- transfers
- premium subscriptions
- tournament payouts
- rewards and promotions
- faucet onboarding

---

## Architecture stance

WoloChain is the chain layer for **AoE2HDBets**.

**WoloChain owns:**

- scarcity
- balances
- transfers
- payout rail
- future IBC readiness

**AoE2HDBets owns:**

- betting UX
- faucet eligibility and abuse prevention
- premium subscriptions
- rewards logic
- user growth loops

That boundary is intentional.

---

## Repo scope

This repo owns:

- chain code
- app wiring
- genesis
- scripts
- chain docs
- local and testnet bootstrap

This repo does **not** own:

- Ping.pub explorer UI
- AoE2HDBets faucet business logic
- AoE2HDBets betting rules
- public marketing pages
- future DEX liquidity operations

---

## Build order

1. Lock docs and invariants
2. Normalize chain identity and denom
3. Build exact genesis allocations
4. Prove the local chain works
5. Deploy VPS testnet/staging
6. Bring up the separate explorer
7. Integrate AoE2HDBets wallet, balance, faucet, and premium flows
8. Move toward public beta once the machine behaves

---

## Local development

WoloChain is being built locally first, then promoted upward:

- **Local chain** = private workshop on your machine
- **Testnet** = deployed dress rehearsal
- **Mainnet** = public chain with real value and real trust

The goal is not to rush junk into production.  
The goal is to make the chain correct, then make it public.

---

## Philosophy

WoloChain v1 should feel:

- scarce
- honest
- usable
- public
- simple
- clean enough to trust

That is the target.