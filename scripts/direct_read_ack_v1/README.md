---
id: "aoe2war.wolochain.hd-direct-read-ack-source-review"
title: "HD Direct Chat read acknowledgement source review"
type: "working"
status: "draft"
owner: "wolochain-ops"
systems: ["wolochain","aoe2war"]
audience: ["developers","operators","ai-agents"]
source_of_truth: "git"
authority: "nonfinancial-HD-source-only-no-native-permit"
reviewed_at: "2026-11-27"
review_interval_days: 7
sensitivity: "restricted"
---

# HD Direct Chat read acknowledgement — source review only

Exact predecessor: #265 319f0fb39cc0f17e87f56ffff23fc5b129ed0f0a. Product successor Emaren/app-prodn#1519. No native execution authority; no financial change. Install candidate materializes historical read membership under bounded locks, then counts explicit recipient/message receipts. Inverse restores the preceding reader definition and revokes new RPC execution without deleting receipts; readmit restores the new reader without reseeding. During inverse the legacy reader cannot reflect new receipts. Do not run any candidate on a live cluster without exact catalog preimage, role/ACL/definition digest, baseline count and lock-budget evidence, independently reviewed inverse/readmission, owner-native authorization and coordinated product guard/writer release. The owner-local PostgreSQL 16 fixture is not a UID650 or HEL1 admission. Fixture SQL lives beside the original #265 fixture. Existing native evidence: Emaren/app-prodn#1519 comment 7224643701; subsequent readmission preserved 49 receipts, zero unread, zero duplicate updates. Production receipt volume, exact ACL preimage, timing and full lifecycle still held.
