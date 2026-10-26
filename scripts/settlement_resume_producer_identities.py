#!/usr/bin/env python3
"""Read-only sealed producer identities for eventual *separately authorized* RESUME.

Never starts/stops units, removes HOLD, certifies all external writers, or grants
financial authority. This module must not be treated as a resume executor.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
import re

import settlement_financial_maintenance as maintenance

SCHEMA = "wolo.financial-maintenance-producer-identities.v1"
CONFIG_PROPERTIES = (
    "Id", "FragmentPath", "DropInPaths", "ActiveState", "MainPID",
    "EnvironmentFiles", "Environment", "ExecStart", "ExecStartPre",
    "ExecStartPost", "ExecStop", "ExecReload", "ExecCondition",
    "WorkingDirectory", "RootDirectory", "RootImage", "User", "Group",
    "LoadCredential", "SetCredential", "BindPaths", "BindReadOnlyPaths",
)
# systemctl show intentionally omits unsupported properties (especially
# service execution properties on .timer units) and optional unset values.
# Production hel1 demonstrated these omissions on all 18 protected units.
# Require the unit-type-specific identity core, and SHA-bind the *exact*
# present-property map; never fabricate omitted values as empty strings.
COMMON_REQUIRED = frozenset(("Id", "FragmentPath", "DropInPaths", "ActiveState"))
SERVICE_REQUIRED = COMMON_REQUIRED | frozenset(("MainPID", "ExecStart"))
STABLE_PROPERTIES = tuple(p for p in CONFIG_PROPERTIES
                          if p not in ("ActiveState", "MainPID", "Id"))
ENVFILE = re.compile(r"(/[^\s]+) \(ignore_errors=(?:yes|no)\)")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def require(value, reason):
    maintenance.require(value, reason)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_properties(unit, runner):
    raw = runner(["systemctl", "--no-pager", "show",
                  "--property=" + ",".join(CONFIG_PROPERTIES), "--", unit])
    require(type(raw) is str and 0 < len(raw) <= 262144,
            "PRODUCER_PROPERTIES_UNAVAILABLE")
    fields = {}
    for line in raw.splitlines():
        require("=" in line, "PRODUCER_PROPERTIES_INVALID")
        key, value = line.split("=", 1)
        require(key in CONFIG_PROPERTIES and key not in fields,
                "PRODUCER_PROPERTIES_INVALID")
        fields[key] = value
    expected = SERVICE_REQUIRED if unit in maintenance.APPS + maintenance.ONESHOTS else COMMON_REQUIRED
    require(unit in maintenance.UNITS and expected.issubset(fields) and
            fields.get("Id") == unit and
            fields.get("FragmentPath") and
            fields.get("ActiveState") in ("active", "inactive") and
            (unit in maintenance.TIMERS or
             (fields.get("ExecStart") and fields.get("MainPID", "").isdigit())),
            "PRODUCER_PROPERTIES_INCOMPLETE")
    # Timer units must not acquire service-only execution properties: accept
    # only known systemd timer/common fields, never an unchecked property
    # expansion that could silently broaden the signed resume scope.
    if unit in maintenance.TIMERS:
        require(set(fields).issubset(COMMON_REQUIRED),
                "UNEXPECTED_TIMER_EXECUTION_PROPERTY")
    return fields


def env_file_paths(value):
    if not value:
        return []
    matches = list(ENVFILE.finditer(value))
    require(len(matches) <= 16 and
            " ".join(item.group(0) for item in matches) == value,
            "UNPARSEABLE_PRODUCER_ENVIRONMENT_FILES")
    return [item.group(1) for item in matches]


def _configuration(unit, fields, runner, *, allow_owned_gate):
    basic = maintenance.show(unit, runner)
    for key in ("Id", "FragmentPath", "DropInPaths", "ActiveState"):
        require(fields[key] == basic.get(key), "PRODUCER_CHANGED_DURING_SAMPLE")
    if unit not in maintenance.TIMERS:
        require(fields["MainPID"] == basic.get("MainPID"),
                "PRODUCER_CHANGED_DURING_SAMPLE")
    require(basic["ActiveState"] in ("active", "inactive") and
            (unit not in maintenance.ONESHOTS or
             (basic["ActiveState"] == "inactive" and basic["MainPID"] == "0")),
            "ACTIVE_OR_UNSTABLE_ONESHOT_REFUSED")

    fragment = fields["FragmentPath"]
    dropins = fields["DropInPaths"].split()
    owned = str(maintenance.dropin(unit))
    require(fragment.startswith(("/etc/systemd/system/", "/usr/lib/systemd/system/",
                                 "/lib/systemd/system/")) and
            len(dropins) <= 32 and len(dropins) == len(set(dropins)),
            "INVALID_PRODUCER_SOURCE_PATHS")
    if allow_owned_gate:
        require(dropins.count(owned) == 1 and
                maintenance.private_read(Path(owned), source=True) ==
                maintenance.expected_dropin(),
                "OWNED_GATE_CHANGED_OR_MISSING")
        dropins = [p for p in dropins if p != owned]
    else:
        require(owned not in dropins and not maintenance.dropin(unit).exists() and
                not maintenance.dropin(unit).is_symlink(),
                "EXISTING_GATE_CANNOT_BE_PRESTATE")

    envs = env_file_paths(fields.get("EnvironmentFiles", ""))
    paths = [("fragment", fragment)] + [("dropin", p) for p in dropins] + [
        ("envfile", p) for p in envs]
    require(len(paths) <= 50 and len({p for _, p in paths}) == len(paths),
            "AMBIGUOUS_PRODUCER_FILES")
    files = []
    for kind, path in paths:
        source = Path(path)
        require(source.is_absolute() and ".." not in source.parts,
                "INVALID_PRODUCER_SOURCE_PATHS")
        # Descriptor/stable inode read, root-owned source. The raw values never
        # enter the receipt; even Environment= and credential paths are hashed.
        raw = maintenance.private_read(source, source=True)
        files.append((kind, sha(str(source).encode()), sha(raw)))
    stable = {key: fields[key] for key in STABLE_PROPERTIES
              if key != "DropInPaths" and key in fields}
    # Preserve absence/presence explicitly. Never collapse "not a timer
    # property" and "present but empty" to the same signed identity.
    stable["present_properties"] = sorted(fields)
    stable["effective_non_owned_dropins"] = [sha(p.encode()) for p in dropins]
    stable["source_file_digests"] = files
    return {"configuration_sha256": sha(maintenance.canonical(stable)),
            "originally_active": basic["ActiveState"] == "active"}


def _sample(*, runner, allow_owned_gate):
    maintenance.no_jobs(runner)
    rows = {}
    for unit in maintenance.UNITS:
        fields = read_properties(unit, runner)
        rows[unit] = _configuration(unit, fields, runner,
                                    allow_owned_gate=allow_owned_gate)
    maintenance.no_jobs(runner)
    return rows


def collect_producer_identities(*, runner, allow_owned_gate=False):
    """Two stable reads, no mutating systemctl operations, no plaintext secrets."""
    require(type(allow_owned_gate) is bool, "INVALID_IDENTITY_MODE")
    if not allow_owned_gate:
        require(not maintenance.HOLD.exists() and not maintenance.HOLD.is_symlink(),
                "EXISTING_HOLD_NOT_CAPTURE_PRESTATE")
    first = _sample(runner=runner, allow_owned_gate=allow_owned_gate)
    require(first == _sample(runner=runner, allow_owned_gate=allow_owned_gate),
            "PRODUCER_IDENTITIES_CHANGED_DURING_CAPTURE")
    return {"schema": SCHEMA, "scope_sha256": maintenance.scope_digest(),
            "units": first, "resume_authorized": False,
            "financial_release_authorized": False}


def verify_producer_identities(expected, *, runner, allow_owned_gate=False):
    """Compare exact pinned source identities; never grant resume permission."""
    require(type(expected) is dict and
            set(expected) == {"schema", "scope_sha256", "units",
                              "resume_authorized", "financial_release_authorized"} and
            expected["schema"] == SCHEMA and
            expected["scope_sha256"] == maintenance.scope_digest() and
            expected["resume_authorized"] is False and
            expected["financial_release_authorized"] is False and
            type(expected["units"]) is dict and
            set(expected["units"]) == set(maintenance.UNITS),
            "RESUME_CAPTURE_IDENTITIES_MISSING")
    for unit, item in expected["units"].items():
        require(type(item) is dict and
                set(item) == {"configuration_sha256", "originally_active"} and
                type(item["originally_active"]) is bool and
                type(item["configuration_sha256"]) is str and
                HEX64.fullmatch(item["configuration_sha256"]) is not None and
                (unit not in maintenance.ONESHOTS or not item["originally_active"]),
                "RESUME_CAPTURE_IDENTITIES_MISSING")
    fresh = collect_producer_identities(runner=runner,
                                        allow_owned_gate=allow_owned_gate)
    for unit in maintenance.UNITS:
        require(expected["units"][unit]["configuration_sha256"] ==
                fresh["units"][unit]["configuration_sha256"],
                "PRODUCER_CONFIGURATION_DRIFT")
    return {"status": "PRODUCER_IDENTITIES_VERIFIED_ONLY",
            "originally_active_apps": [u for u in maintenance.APPS
                                       if expected["units"][u]["originally_active"]],
            "originally_active_timers": [u for u in maintenance.TIMERS
                                         if expected["units"][u]["originally_active"]],
            "resume_authorized": False, "financial_release_authorized": False}


def inspect_readonly(*, runner):
    """Root-only, no-write live prestate inspection; never a signed capture.

    The returned digest is an observation handle, NOT a nonce, permit, or
    durable packet. It cannot replace actual LIVE_CAPTURE or human authority.
    """
    require(os.geteuid() == 0, "ROOT_REQUIRED_FOR_PRIVATE_SOURCE_OBSERVATION")
    packet = collect_producer_identities(runner=runner, allow_owned_gate=False)
    require(packet["schema"] == SCHEMA and packet["scope_sha256"] == maintenance.scope_digest() and
            packet["resume_authorized"] is False and
            packet["financial_release_authorized"] is False and
            set(packet["units"]) == set(maintenance.UNITS),
            "INCOMPLETE_NONAUTHORIZING_PRESTATE")
    units = packet["units"]
    apps = sum(units[u]["originally_active"] for u in maintenance.APPS)
    timers = sum(units[u]["originally_active"] for u in maintenance.TIMERS)
    oneshots = sum(not units[u]["originally_active"] for u in maintenance.ONESHOTS)
    require(len(maintenance.UNITS) == 18 and len(maintenance.APPS) == 4 and
            len(maintenance.TIMERS) == len(maintenance.ONESHOTS) == 7 and
            oneshots == 7 and apps == 4 and timers == 7,
            "PRODUCER_PRESTATE_CHANGED_NOT_SAFE_TO_ASSUME")
    return {
        "schema": "wolo.financial-maintenance-producer-observation.v1",
        "status": "IDENTITIES_OBSERVED_ONLY",
        "scope_sha256": packet["scope_sha256"],
        "identity_observation_sha256": sha(maintenance.canonical(packet)),
        "units": 18, "active_apps": apps, "active_timers": timers,
        "inactive_oneshots": oneshots,
        "signed_capture": False, "global_writers_fenced": False,
        "resume_authorized": False, "financial_release_authorized": False,
    }


def _main():
    if len(sys.argv) != 1:
        print(json.dumps({"status": "HOLD", "reason": "NO_USER_INPUTS_ACCEPTED",
                          "financial_release_authorized": False}))
        return 2
    try:
        result = inspect_readonly(runner=maintenance.run)
    except Exception as exc:
        # Never echo raw systemctl stderr, credentials, command lines, or paths.
        print(json.dumps({"status": "HOLD",
                          "reason": ("INSPECT_REFUSED_" + type(exc).__name__),
                          "financial_release_authorized": False}))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
