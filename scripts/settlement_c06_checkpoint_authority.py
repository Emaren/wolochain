"""C06 expanded snapshot signature review using the EXISTING owner verifier.

No signing, witness enrollment, nonce consumption, or production authorization.
Old solo-capture packets cannot authorize a whole shared-cluster checkpoint.
"""
from datetime import timedelta
import hashlib
import settlement_solo_owner_intent_review as owner
from settlement_c06_checkpoint_coordinator import validate_plan

DOMAIN = b"AOE2WAR-WOLO-C06-COORDINATED-CHECKPOINT-V1\x00"
SCHEMA = "wolo.c06.coordinated-checkpoint-request.v1"
PACKET = "wolo.c06.coordinated-checkpoint-signed-request.v1"
OPS = {"capture":"coordinated-physical-encrypted-capture",
       "restore":"independent-identical-ciphertext-recovery",
       "resume":"restore-original-nonfinancial-services",
       "contain":"reconcile-ambiguous-checkpoint-effects"}
WINDOW = {"capture":1800,"restore":14400,"resume":1800,"contain":1800}

def review(enrollment, packet, plan, *, phase, previous, source_commit,
           enrollment_pin, owner_pin, openssl_path, now=None):
    plan_sha = validate_plan(plan)
    def validate(q, n):
        owner.require(phase in OPS and set(q)=={
            "schema","chain_id","phase","operation","source_commit","plan_sha256",
            "previous_journal_sha256","nonce","not_before","expires_at"
        } and q["schema"]==SCHEMA and q["chain_id"]=="wolo-1" and
            q["phase"]==phase and q["operation"]==OPS[phase] and
            q["source_commit"]==source_commit and owner.HEX40.fullmatch(source_commit)
            and source_commit!="0"*40 and q["plan_sha256"]==plan_sha and
            q["previous_journal_sha256"]==previous and
            (previous is None if phase=="capture" else owner.hex64(previous)),
            "EXPANDED_SNAPSHOT_SCOPE_OR_LINEAGE")
        owner.require(type(q["nonce"]) is str and owner.HEX32.fullmatch(q["nonce"])
                      and q["nonce"]!="0"*32,"NONCE_INVALID")
        start,end=owner.utc(q["not_before"]),owner.utc(q["expires_at"])
        owner.require(start<=n<end and timedelta()<end-start<=timedelta(seconds=WINDOW[phase]),
                      "PHASE_WINDOW")
    enrolled,q,n=owner.authenticate_owner(enrollment,packet,
        pinned_enrollment_sha256=enrollment_pin,pinned_owner_der_sha256=owner_pin,
        packet_schema=PACKET,domain=DOMAIN,validate_request=validate,now=now,
        openssl_path=openssl_path)
    owner.require(owner.utc(enrolled["valid_from"])<=owner.utc(q["not_before"])
                  and owner.utc(q["expires_at"])<=owner.utc(enrolled["valid_until"]),
                  "ENROLLMENT_MUST_COVER_PHASE")
    return {"status":"CRYPTO_VALID_NONAUTHORIZING",
            "phase":phase,"plan":plan_sha,"previous":previous,
            "packet":hashlib.sha256(packet).hexdigest(),
            "nonce":hashlib.sha256(q["nonce"].encode()).hexdigest(),
            "expires":int(owner.utc(q["expires_at"]).timestamp()),
            "independent_witness_consumed":False,"production_authorized":False,
            "funding_authorized":False}
