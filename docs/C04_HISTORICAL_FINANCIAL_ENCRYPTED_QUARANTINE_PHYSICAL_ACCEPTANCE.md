---
id: "aoe2war.wolochain.c04-historical-finance-encrypted-quarantine-and-native-noninterference-acceptance"
title: "C04 Historical Financial Quarantine: Physical Noninterference Acceptance"
type: "runbook"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain", "aoe2war"]
audience: ["operators", "developers", "financial-reviewers", "ai-agents"]
source_of_truth: "git"
authority: "nonfunded-legacy-liability-quarantine-no-adjudication-or-waiver"
reviewed_at: "2026-11-09"
review_interval_days: 7
sensitivity: "restricted"
---

# C04 Historical Financial Quarantine: Physical Noninterference Acceptance

## Purpose and prohibition

**This is a nonfunded quarantine of all historical claims, not settlement.**
It does not say the ambiguous 69 claimed/no-hash obligations were paid,
unpaid, forgiven or available as collateral. All 948 pending claims remain
pending in the original HD ledger; 193 rescinded and 1,243
claimed-with-hash records are also retained as recorded. Original payout
services cannot execute while persistently masked. The new native C02/C04
signed claim namespace only permits canonical 900000000001 through
999999999999 and rejects old 889, 9645 and every legacy identity; its
funded 8094/8095 ports are still closed. The adopted original C08 one-human
governance explicitly disclaims any historical liability waiver and
grants zero funded authority.

## Real HEL1 production quarantine, November 9 UTC

Original exact SHA-pinned units:

- wolochain-mainnet-settlement.service, port8092, original SHA256
  571812b3a13a2e887e434f1e97251a0b87f229859cd245c6ce032db1f317d85b.
- wolochain-founder-rewards-settlement.service, port8093, original SHA256
  ad5020bb527ae09e389fd2f185779b50146e6ed1085809a2a87eaeb0f29b3392.

The original files and pre-change state are retained under protected
/root/aoe2war-c04-legacy-settlement-quarantine-20261109, owner root only.
Both services stopped and disabled, and their exact original systemd unit
paths were replaced by **persistent /dev/null masks**. Subsequent
systemctl daemon-reload confirms LoadState masked, UnitFileState masked,
ActiveState inactive, MainPID zero for each. Four direct loopback
connection attempts to 8092/8093/8094/8095 independently returned
ConnectionRefused. The Wolo validator remains active and both original
3030 and restricted 3032 web origins returned HTTP200.

This intentionally suspends *historical customer payouts*. Neither
Session B's App rollback nor a reboot may silently reenable those services.
Restoration requires explicit, separately reviewed legacy payment
adjudication and a deliberate unit-source recovery ceremony.

## Exactly recovered historical obligations, independently on Intel

- C04 original 12-table protected age ciphertext SHA256
  d0f785629b6ff09d356126329ab211fb0d50426922b37c5549cc3c62ba6efc8f;
  exact on-HEL1 source SHA256
  d2d1a615c358a92181cbacb858ed35e1d2162a019aeda10db6abab7cc20ad75e;
  root-private capture receipt SHA256
  79219faa10d0e583301991bb5196fa470717c0a7fbf210180585563ea9cd71b5.
  Independently restored 12/12 historical tables on FileVault Intel;
  exact private restore receipt SHA256
  ecbf437a14c19287a69ee57a12529d1a32b0403cca1e64da28c23912118a07ca.
- Expanded **30-table** private legacy perimeter: all 29 C03 inventory
  finance candidates plus original mixed-purpose users table. Exact
  PostgreSQL16 custom compressed dump source SHA256
  4066ad25ee253246cbca3dcb8f69b82abe39a7c33afbf8869a9cffc9de1bb600.
  Root-private encrypted capture receipt SHA256
  99209ac9a8a0f4181260cf226a5730995926dbbc6bb8f1461955dbea1cde4080.
  The entire original **2,098,199-byte** encrypted file SHA256
  d7d3d6c708ef0cf485210db70abb2ca7cf8d93dea666dfa6e68fd3dced349ba2
  was independently SHA verified on M1 then FileVault Intel.
  Actual 30/30 tables fully age-authenticated and restored as schema+data
  under isolated Unix-socket-only PostgreSQL16; no TCP, no live database.
  Initial Intel source correctly refused a mismatched table cardinality
  assertion without starting PostgreSQL. The byte-exact fixed source SHA256
  5aa8a30dac7c82a0c81e832f376efe327d8aca5a659728c6b4e619d45231b977
  subsequently restored all 30 tables. Original private Intel restore
  receipt SHA256 e5066aee06ebf4e3801d0cab3200235fb41d3c965a04af9b4c5c3497316adc56.

All 2,453 historic claim IDs, status, claim type, amount and recorded
payout hashes are independently preserved. The protected full claimant
identity/amount commitment SHA256 from the **actual restored Intel database**
is 257d763369b644c025e1e923960059e15a24f7b8436ecde0c122ba14259c897b.
The same projection queried separately from the **live HEL1 HD production**
database after the archival operation produced the *identical* SHA256.
Aggregates: 69 claimed/no-hash nominal 120,443 WOLO, 948 pending nominal
993,289 WOLO, 1,243 claimed with hash, 193 rescinded.

Both archives used only the two verified recovery **public keys**, with
no plaintext financial dumps staged on HEL1. The Intel independent
recovery identity is FileVault protected. No private key exported to
HEL1 or M1.

## Exact limits of the quarantine interpretation

The custom 30-table subset was restored as PostgreSQL pre-data + data,
not all post-data FK/index constraints, since referenced external tables
may be absent in a limited subset. The separate FULL HD 190-table and
DE 52-table archives were already successfully restored on Intel by
C07 earlier, but those were unquiesced.

This evidences preservation and *current* execution denial, NOT
payment finality or reserve solvency. Individual historical payout
causality remains UNKNOWN where transaction/application journal linkage
cannot be authenticated. All amounts remain economic obligations
pending case-by-case adjudication; do not mark old debts paid/unpaid,
credit, auto-retry or use them as new Satchel collateral.

C04 nonfunded legacy quarantine can be formally admitted only if:
1. Exact source and 5/5 source tests pass and the PR merges.
2. A fresh post-state verifies both persistent masks, all four financial
   ports closed, website+validator health, unchanged 69/948 census and
   the exact 2,453-claim identity commitment.
3. The authority record clearly designates a **quarantine**, not a payment
   release or historical liability waiver. Any later restoration of
   8092/8093 or unauthorized old claim in 8094 invalidates that acceptance.
4. C03 live writer fence, C05 asset control, final C06/C07 synchronized
   recovery and C09 transaction signature remain independent gates.

This runbook never authorizes transfers, changes production SQL
ownership, restarts financial services or opens funded listeners.
