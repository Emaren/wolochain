"""C06 expanded snapshot signature review using the EXISTING owner verifier.

No signing, witness enrollment, forced-command installation or production authorization.
The witness library below reuses the existing one-use nonce storage primitive.
Old solo-capture packets cannot authorize a whole shared-cluster checkpoint.
"""
from datetime import timedelta
import hashlib
import settlement_solo_owner_intent_review as owner
from settlement_c06_checkpoint_coordinator import validate_plan
import settlement_maintenance_nonce_store as nonces
from settlement_c06_checkpoint_rehearsal import canonical, digest, hash64

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


# These are storage categories, not permission aliases. The expanded packet
# has a separate signed domain and scope. Reuse the SAME enrolled witness
# nonce directory so that a nonce spent by the legacy controller cannot be
# spent again here. Do not widen the historical nonce-store schema or pins.
STORAGE_PHASE = {"capture":"live_capture","restore":"offline_verify",
                 "resume":"resume_existing","contain":"contain_partial"}
ACK_SCHEMA = "wolo.c06.expanded-witness-consumption.v1"

def review_witness_plan(plan, *, local_identity, source_identity,
                        witness_identity, expected_plan_sha):
    """Expected identities come from protected native enrollment, not a request."""
    owner.require(all(hash64(x) for x in (local_identity,source_identity,
                  witness_identity,expected_plan_sha)) and
                  local_identity == witness_identity and
                  local_identity != source_identity and
                  plan.get("host") == source_identity and
                  validate_plan(plan) == expected_plan_sha,
                  "EXPANDED_WITNESS_NOT_SEPARATELY_ENROLLED_OR_PLAN_DRIFT")

def consume_expanded_witness(enrollment, packet, plan, *, phase, previous,
        source_commit, enrollment_pin, owner_pin, openssl_path,
        local_identity, source_identity, witness_identity, expected_plan_sha,
        nonce_root, now=None):
    """Witness-side library: a genuine signature plus durable one-use storage.

    A protected dispatcher must independently load the pinned source, plan and
    identities from its native enrollment and obtain actual local identity.
    There is deliberately no CLI, automatic enrollment, transport, or host
    mutation here. A receipt alone authorizes no production action.
    """
    review_witness_plan(plan, local_identity=local_identity,
        source_identity=source_identity, witness_identity=witness_identity,
        expected_plan_sha=expected_plan_sha)
    kwargs = dict(phase=phase, previous=previous, source_commit=source_commit,
        enrollment_pin=enrollment_pin, owner_pin=owner_pin,
        openssl_path=openssl_path, now=now)
    checked = review(enrollment, packet, plan, **kwargs)
    request = owner.parse(packet)["request"]
    storage_phase = STORAGE_PHASE[phase]
    recorded = nonces.reserve_once(nonce_root, request["nonce"],
                                  checked["packet"], storage_phase)
    # Check the same signature/window again after durable reservation.
    # An expired packet is still spent; uncertainty is never an unused nonce.
    review(enrollment, packet, plan, **kwargs)
    return {"schema":ACK_SCHEMA,"phase":phase,"plan":checked["plan"],
            "previous":previous,"packet":checked["packet"],
            "request_sha256":digest(canonical(request)),
            "witness_identity":local_identity,
            "record_sha256":recorded["record_sha256"],
            "nonce":checked["nonce"],"expires":checked["expires"],
            "fresh_consumption_confirmed":True,
            "production_authorized":False,"funding_authorized":False}

def verify_expanded_witness_ack(ack, enrollment, packet, plan, *,
        phase, previous, source_commit, enrollment_pin, owner_pin, openssl_path,
        witness_identity, now=None):
    """Validate a response received on the separately enrolled witness route.

    This does NOT authenticate the channel; native pinned transport must do so.
    Never accept an ACK file supplied by an untrusted caller as authority.
    """
    checked=review(enrollment,packet,plan,phase=phase,previous=previous,
        source_commit=source_commit,enrollment_pin=enrollment_pin,
        owner_pin=owner_pin,openssl_path=openssl_path,now=now)
    request=owner.parse(packet)["request"]
    record={"schema":nonces.SCHEMA,"nonce":request["nonce"],
            "signed_packet_sha256":checked["packet"],"phase":STORAGE_PHASE[phase]}
    expected={"schema":ACK_SCHEMA,"phase":phase,"plan":checked["plan"],
        "previous":previous,"packet":checked["packet"],
        "request_sha256":digest(canonical(request)),
        "witness_identity":witness_identity,
        "record_sha256":digest(nonces.canonical(record)),
        "nonce":checked["nonce"],"expires":checked["expires"],
        "fresh_consumption_confirmed":True,
        "production_authorized":False,"funding_authorized":False}
    owner.require(hash64(witness_identity) and witness_identity != plan["host"]
                  and type(ack) is dict and canonical(ack)==canonical(expected),
                  "EXPANDED_WITNESS_ACK_DRIFT")
    return {"phase":phase,"plan":checked["plan"],"previous":previous,
            "packet":checked["packet"],"witness":digest(canonical(ack)),
            "nonce":checked["nonce"],"expires":checked["expires"]}
