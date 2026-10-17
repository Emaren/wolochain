// Cross-language wire fixture check using Node's crypto implementation. This
// test has no network/keyring dependencies and supplies no production authority.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash, createPublicKey, ECDH, verify } from 'node:crypto';

const f = JSON.parse(readFileSync(new URL('../internal/satchelservice/testdata/financial-bridge-v1.json', import.meta.url), 'utf8'));
assert.equal(f.fixture_only, true);
assert.equal(f.mainnet_authority, false);
const r = f.withdrawal_request, m = r.owner_mandate, c = m.challenge, a = r.approval;
const json = JSON.stringify;
const sha = value => createHash('sha256').update(value).digest('hex');
const b64 = value => Buffer.from(value, 'base64');
const ed = createPublicKey({ format: 'der', type: 'spki', key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), Buffer.from(f.approval_public_key_hex, 'hex')]) });

// These exact lines are the current HD withdrawalChallengeText contract.
const text = [
  'AoE2WAR War Satchel WITHDRAWAL AUTHORIZATION',
  'Origin: aoe2war.com', 'Chain: wolo-1', 'Denom: uwolo',
  'Owner UID: ' + c.owner_uid,
  'Linked Keplr receiving wallet: ' + c.wallet_address,
  'Exact withdrawal amount uwolo: ' + c.amount_uwolo,
  'One-use withdrawal challenge ID: ' + c.id,
  'Issued: ' + c.issued_at_utc, 'Expires: ' + c.expires_at_utc,
  'I authorize ONLY this one withdrawal from my War Satchel into my linked Keplr wallet.',
  'This does NOT authorize automated bets or permit any service to read Keplr private keys.',
].join('\n');
assert.equal(text, f.owner_challenge_text);
const ownerBytes = json({ account_number: '0', chain_id: '', fee: { amount: [], gas: '0' }, memo: '', msgs: [{ type: 'sign/MsgSignData', value: { data: Buffer.from(text).toString('base64'), signer: c.wallet_address } }], sequence: '0' });
assert.equal(ownerBytes, f.owner_adr36_sign_bytes);
const full = Buffer.from(ECDH.convertKey(b64(m.pub_key.value), 'secp256k1', undefined, undefined, 'uncompressed'));
const ownerKey = createPublicKey({ format: 'jwk', key: { kty: 'EC', crv: 'secp256k1', x: full.subarray(1, 33).toString('base64url'), y: full.subarray(33, 65).toString('base64url') } });
assert.equal(verify('sha256', Buffer.from(ownerBytes), { key: ownerKey, dsaEncoding: 'ieee-p1363' }, b64(m.signature)), true);
assert.equal(verify('sha256', Buffer.from(ownerBytes + 'tamper'), { key: ownerKey, dsaEncoding: 'ieee-p1363' }, b64(m.signature)), false);
const mandateDigest = sha(json(['aoe2war/satchel/withdraw-owner-mandate/v1', c.id, c.owner_uid, c.wallet_address, c.amount_uwolo, c.issued_at_utc, c.expires_at_utc, m.pub_key.type, m.pub_key.value, m.signature]));
assert.equal(mandateDigest, f.owner_mandate_digest);
assert.equal(sha(json(['aoe2war/satchel/withdraw-hold/v1', a.reservation_digest, mandateDigest])), a.hold_digest);
assert.equal(a.hold_digest, f.withdrawal_hold_digest);
const approvalBytes = json(['aoe2war/satchel/withdraw-approval/v1', 'wolo-1', 'uwolo', f.vault, a.withdrawal_id, a.challenge_id, a.owner_id, a.recipient, a.amount_uwolo, a.memo, a.hold_digest, a.issued_at, a.expires_at]);
assert.equal(approvalBytes, f.withdrawal_approval_sign_bytes);
assert.equal(verify(null, Buffer.from(approvalBytes), ed, b64(a.signature)), true);

const p = f.allocation;
const fields = ['aoe2war/satchel/return-allocation/v2', 'wolo-1', 'uwolo', f.betting_escrow, f.vault, p.version, p.allocation_id, p.revision, p.operation_id, p.owner_id, p.ticket_id, p.funding_tx_hash, p.return_cap_uwolo, p.funds_budget_id, p.funds_available_uwolo, p.bank_evidence_digest, p.bank_height, p.bank_block_hash,
  p.legs.map(l => [l.leg_id, l.market_id, l.stake_uwolo, l.entitlements.map(e => [e.entitlement_id, e.claim_id, e.claim_kind, e.principal_uwolo, e.amount_uwolo])])];
assert.equal(sha(json(fields)), f.allocation_digest);
const allocationBytes = json([...fields, p.issued_at, p.expires_at]);
assert.equal(allocationBytes, f.allocation_sign_bytes);
assert.equal(verify(null, Buffer.from(allocationBytes), ed, b64(p.signature)), true);
const ret = f.return_approval;
const returnBytes = json(['aoe2war/satchel/claim-return-approval/v2', 'wolo-1', 'uwolo', f.betting_escrow, f.vault, ret.version, ret.operation_id, ret.claim_id, ret.owner_id, ret.ticket_id, ret.market_id, ret.leg_id, ret.entitlement_id, ret.claim_kind, ret.amount_uwolo, ret.allocation_digest, ret.issued_at, ret.expires_at]);
assert.equal(returnBytes, f.return_approval_sign_bytes);
assert.equal(verify(null, Buffer.from(returnBytes), ed, b64(ret.signature)), true);
assert.equal(verify(null, Buffer.from(returnBytes.replace(ret.owner_id, 'forged-owner')), ed, b64(ret.signature)), false);
assert.equal(verify(null, Buffer.from(allocationBytes.replace(p.funds_available_uwolo, '99999999999')), ed, b64(p.signature)), false);
console.log('PASS: exact HD ADR36 text, owner secp256k1 signature, independent Ed25519 approval/allocation/return signatures, hold binding and tamper rejection');
