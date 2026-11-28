# Historical Clan image admission — source review only

Exact successor to #266 and #264; adds a separate root/database-owner controlled
admission map, not synthetic upload request keys. Existing attachment and message
rows remain unchanged. The existing read_hall and read_image function bodies are
preimage-pinned; only explicitly mapped, still-matching single clan-audience
PNG/JPEG/WebP attachments of at most 10 MB are exposed to active members. No
new raw access for web, social writer or image executor. The original upload
receipt path is unchanged. No live migration is implied by the fixture.

Owner-native census: 734 legacy rows, 625 metadata/magic matches, 624 fully
decoded and SHA256-qualified current files, 642902575 bytes. Census SHA
65ea9d33a5cd76916544f0ac7934817bff5d6df609f714fdf69ac2ef1d98da77;
content receipt SHA d94454d0daf995f5789a66ca643bab4ab1d611e9fd2a361ce5fd714669ec1f28.
No private paths or attachment IDs are committed. Qualification is current-byte
integrity, not proof of original historical content hash.

Before native install: independently check exact live function definitions,
role/ACL and object identities, source lineage, empty mapping preimage, and
filesystem ownership. Stage only selected, revalidated content under exclusive
fresh random protected filenames; verify no collisions against existing files,
request keys or mapping rows. Maintain DATA reserve (including transient growth),
never delete originals, never hardlink or create synthetic upload receipts.
Verify bytes and ownership before inserting any mappings. Use separate bounded
native transaction and durable admission ledger with exact row preimages; preserve
all original message and attachment records. Empty inverse only; populated
mapping rollback requires separately reviewed reversible unadmission, not file
or history deletion. No financial or DE changes.

Run `python3 -I -B scripts/clan_legacy_reader_v1/test.py` as nonroot on an
isolated local PG16 binary installation; the fixture binds only a private Unix
socket, tests original source functions and restores/removes its disposable DB.
