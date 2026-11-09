---
id: "aoe2war.wolochain.c05-native-registered24-single-height-bank-physical-hold"
title: "C05 Registered Wallets Native Same-Height Bank Evidence: Physical HOLD"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "source-bound-readonly-mainnet-bank-census-not-financial-reserve-acceptance"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C05 Registered Wallets Native Same-Height Bank Evidence: Physical HOLD

**C05 remains OPEN.** This physically executed source proves bank quantities,
not spendable reserves, eligible collateral, private-key custody or liability
settlement. No transfers, permission grants, financial service startups,
C01 key operations or App changes occur.

## Actual source-pinned HEL1 execution

The original docs/mainnet-wallets.md documents exactly 23 current
mainnet address labels. The source
scripts/settlement_c05_native_registered24_single_height_hold.py
loads and SHA-pins the actual 23 documented public addresses from the
protected canonical source document instead of repeating high-entropy
public account strings in new executable code; it adds the separate
fresh C01 prospective vault. The original source document SHA256 is
a159768ee35ccdd0c02f8be0005d1ca1fbedcbfe83079e91ba86544c2e9d0280.
Exact source SHA256:
2b6eb9fd6980dceee24936d9fc302403833f343b2893e5a7611e848ef4f31776.

Independent local tests validated the source's 23 registered wallet addresses
set-for-set against the 23 canonical docs (not just a count). On
November 9 UTC, an actual HEL1 root read-only execution:

- Verified the real running Wolo native binary matches proc/1009/exe and
  uses the real wolo-1 mainnet node home.
- Authenticated local Comet status network wolo-1 and catching_up=false,
  block height **2,886,568** and exact local block ID
  **18CDE084F52EEFC9C7039B924B2B6239308409A3AECE3BA94382EB0B13F9815C**.
- Queried 24/24 accounts with the real bank CLI using the same
  historical --height 2886568, not a moving latest height.
- Strictly validated only uwolo-denom canonical unsigned amounts, no
  duplicate denom and correct complete wallet count.
- Total all 23 labeled wallets plus new C01 vault:
  **87,639,451,200,705 uwolo = 87,639,451.200705 WOLO**.
- New C01 prospective Satchel vault is empty at this same height.
- Root-private source-bound receipt
  /root/aoe2war-c05-native-registered24-bank-v3-20261109/registered24-single-height-native-bank.json
  SHA256
  **148b9d9aa46b01eafd3804a1603d954f2bbaaffe282755e430a288dbc815159d**.
  Root-only directory mode0700; file created with O_NOFOLLOW/O_EXCL mode0600.
The exact full original 24-account v3 JSON was independently copied from
HEL1 to M1 and to Intel FileVault, with matching SHA256 on both offhost
copies and no wallet-private material.

An earlier v1 source with duplicated public wallet address literals had
also physically passed all 24 bank queries at block 2,886,464, same total
and zero C01 vault, with root-private receipt SHA256
bb0a5ace2b0ef4525379b90a0da644d872b6766302260806ef95fa18a37367d3.
GitGuardian detected one of those original PUBLIC addresses as generic
high entropy. To resolve this without whitelisting security checks or
hiding any private credential, current source parses an exact SHA-pinned
copy of the existing canonical wallet documentation instead. That new
source was independently executed against real HEL1 bank at block
2,886,568 and its whole receipt separately read back on Intel. This
is not an independent Comet finality witness.

All five dedicated source-bound tests PASS: physical script SHA, canonical
23-address set equality, fixed native same-height source, no private
credentials/broadcasts, M1/nonroot denial.

## Financial limitations — C05 OPEN

The 23 wallets include founder, player, IBC escrow, staking, treasury,
relayer, faucet, retired and historic settlement balances. Their arithmetic
total does NOT represent a controlled, unencumbered reserve. The bank-only
source asserts current eligible proven collateral = ZERO.

Previously observed exposures include 5,356,076 WOLO active staking
principal, C04 historical 69 claimed-no-hash UNKNOWN plus 948 pending
obligations, dry-run trophy rows, gift/bounty obligations, NFT custody
and semantically money-bearing HD/DE tables. Never add these blindly:
their economic identities and overlaps require adjudication.
C04 quarantine preserves these obligations but does not erase them.

Still required before C05 funded acceptance: real custody ownership
and eligibility; independent native consensus/bank witness of the
same committed height; reconciled disjoint comprehensive source-to-ledger
liability upper bound; reserve floor and gas cushion; independent
source-bound review; separately signed fresh C09 exact canary permit.
Do not top up from historical escrow or count protected/third-party
funds as spendable just to clear C05.

C04 and C08 CLOSED. C01/C02/C03/C05/C06/C07/C09 remain OPEN.
