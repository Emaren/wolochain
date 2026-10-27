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
# Native systemctl emits one property line per ordered command/env-file.
# Repeated singular identity/state properties still fail closed.
REPEATED_PROPERTIES = frozenset(("EnvironmentFiles", "ExecStart", "ExecStartPre",
    "ExecStartPost", "ExecStop", "ExecReload", "ExecCondition", "LoadCredential",
    "SetCredential", "BindPaths", "BindReadOnlyPaths"))
ENVFILE = re.compile(r"(/[^\s]+) \(ignore_errors=(?:yes|no)\)")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CODE_LOADING_ENV = re.compile(rb"(?:^|[^A-Za-z0-9_])(?:LD_[A-Z0-9_]+|DYLD_[A-Z0-9_]+|"
    rb"NODE_OPTIONS|NODE_PATH|PYTHONPATH|PYTHONHOME|PYTHONSTARTUP|BASH_ENV|ENV|"
    rb"RUBYOPT|RUBYLIB|PERL5OPT|PERL5LIB|PHP_INI_SCAN_DIR|GCONV_PATH)\s*=")


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
        require(key in CONFIG_PROPERTIES and
                (key not in fields or key in REPEATED_PROPERTIES),
                "PRODUCER_PROPERTIES_INVALID")
        if key in REPEATED_PROPERTIES:
            fields.setdefault(key, []).append(value)
            require(len(fields[key]) <= 32, "PRODUCER_PROPERTY_ITEMS_EXCEEDED")
        else:
            fields[key] = value
    expected = SERVICE_REQUIRED if unit in maintenance.APPS + maintenance.ONESHOTS else COMMON_REQUIRED
    require(unit in maintenance.UNITS and expected.issubset(fields) and
            fields.get("Id") == unit and
            fields.get("FragmentPath") and
            fields.get("ActiveState") in ("active", "inactive") and
            (unit in maintenance.TIMERS or
             (fields.get("ExecStart") and all(fields["ExecStart"]) and fields.get("MainPID", "").isdigit())),
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
    values = [value] if isinstance(value, str) else value
    require(type(values) is list and len(values) <= 16 and
            all(type(item) is str for item in values),
            "UNPARSEABLE_PRODUCER_ENVIRONMENT_FILES")
    result = []
    for text in values:
        matches = list(ENVFILE.finditer(text))
        require(len(matches) <= 16 and
                " ".join(item.group(0) for item in matches) == text,
                "UNPARSEABLE_PRODUCER_ENVIRONMENT_FILES")
        result.extend(item.group(1) for item in matches)
    require(len(result) <= 16, "UNPARSEABLE_PRODUCER_ENVIRONMENT_FILES")
    return result


EXECUTION_PROPERTIES = frozenset(("ExecStart", "ExecStartPre", "ExecStartPost",
                                  "ExecStop", "ExecReload", "ExecCondition"))


def native_empty_credentials(unit, fields, runner):
    """Even empty credential arrays render '[unprintable]' in systemctl.

    Validate native empty arrays. Nonempty inputs still need separate content
    sealing and remain unavailable; no credential value enters any receipt.
    """
    expected = {"LoadCredential": "a(ss)", "SetCredential": "a(say)"}
    present = set(fields).intersection(expected)
    if not present:
        return
    raw = runner(["busctl", "--system", "--json=short", "call", "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager", "LoadUnit", "s", unit])
    require(type(raw) is str and len(raw) <= 65536, "PRODUCER_NATIVE_UNIT_INVALID")
    loaded = json.loads(raw)
    require(type(loaded) is dict and loaded.get("type") == "o" and
            type(loaded.get("data")) is list and len(loaded["data"]) == 1 and
            type(loaded["data"][0]) is str and
            re.fullmatch(r"/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+", loaded["data"][0]),
            "PRODUCER_NATIVE_UNIT_INVALID")
    for name in sorted(present):
        raw = runner(["busctl", "--system", "--json=short", "get-property",
            "org.freedesktop.systemd1", loaded["data"][0], "org.freedesktop.systemd1.Service", name])
        require(type(raw) is str and len(raw) <= 262144, "PRODUCER_NATIVE_CREDENTIAL_LIMIT")
        value = json.loads(raw)
        require(type(value) is dict and set(value) == {"type", "data"} and
                value["type"] == expected[name] and type(value["data"]) is list,
                "PRODUCER_NATIVE_CREDENTIAL_INVALID")
        require(not value["data"], "PRODUCER_UNSEALED_EXECUTION_SOURCE")


def native_execution_configuration(unit, fields, runner):
    """Use native ordered argv tuples; PID/timing/exit values are runtime state.

    Unit/drop-in bytes remain independently hashed. Do not parse argv out of
    systemctl's lossy human rendering, or hash volatile last-run timestamps as
    if stopping a unit changed its source configuration.
    """
    names = sorted(EXECUTION_PROPERTIES.intersection(fields))
    if not names:
        return {}
    loaded = json.loads(runner(["busctl", "--system", "--json=short", "call",
        "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager", "LoadUnit", "s", unit]))
    require(loaded.get("type") == "o" and type(loaded.get("data")) is list and
            len(loaded["data"]) == 1 and type(loaded["data"][0]) is str and
            re.fullmatch(r"/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+", loaded["data"][0]),
            "PRODUCER_NATIVE_UNIT_INVALID")
    result = {}
    for name in names:
        raw = runner(["busctl", "--system", "--json=short", "get-property",
            "org.freedesktop.systemd1", loaded["data"][0],
            "org.freedesktop.systemd1.Service", name])
        require(type(raw) is str and len(raw) <= 262144, "PRODUCER_NATIVE_EXECUTION_LIMIT")
        value = json.loads(raw)
        require(type(value) is dict and set(value) == {"type", "data"} and
                value["type"] == "a(sasbttttuii)" and type(value["data"]) is list and
                len(value["data"]) <= 32, "PRODUCER_NATIVE_EXECUTION_INVALID")
        text_rows = fields[name]
        expected = 0 if text_rows == [""] else len(text_rows)
        require(len(value["data"]) == expected, "PRODUCER_EXECUTION_CHANGED_DURING_SAMPLE")
        rows = []
        for row in value["data"]:
            require(type(row) is list and len(row) == 10 and type(row[0]) is str and
                    0 < len(row[0]) <= 4096 and row[0].startswith("/") and
                    type(row[1]) is list and 0 < len(row[1]) <= 256 and
                    all(type(a) is str and len(a) <= 16384 for a in row[1]) and
                    type(row[2]) is bool and all(type(n) is int for n in row[3:]),
                    "PRODUCER_NATIVE_EXECUTION_INVALID")
            rows.append(row[:3])
        result[name] = rows
    return result


def _configuration(unit, fields, runner, *, allow_owned_gate):
    basic = maintenance.show(unit, runner)
    for key in ("Id", "FragmentPath", "DropInPaths", "ActiveState"):
        require(fields[key] == basic.get(key), "PRODUCER_CHANGED_DURING_SAMPLE")
    if unit not in maintenance.TIMERS:
        require(fields["MainPID"] == basic.get("MainPID"),
                "PRODUCER_CHANGED_DURING_SAMPLE")
    if unit in maintenance.APPS:
        require((basic["ActiveState"] == "active" and int(basic["MainPID"]) > 0) or
                (basic["ActiveState"] == "inactive" and basic["MainPID"] == "0"),
                "PRODUCER_APP_PROCESS_IDENTITY_UNAVAILABLE")
    require(basic["ActiveState"] in ("active", "inactive") and
            (unit not in maintenance.ONESHOTS or
             (basic["ActiveState"] == "inactive" and basic["MainPID"] == "0")),
            "ACTIVE_OR_UNSTABLE_ONESHOT_REFUSED")
    if unit in maintenance.TIMERS:
        require(basic.get("Triggers", "").split() == [unit[:-6] + ".service"],
                "PRODUCER_TIMER_TARGET_OUTSIDE_QUALIFIED_PAIR")

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
    # These knobs can execute code outside the sealed argv/build tree. Do not
    # parse or log their secret values, or guess that a preload is harmless.
    require(not CODE_LOADING_ENV.search(fields.get("Environment", "").encode()),
            "PRODUCER_UNSEALED_ENVIRONMENT_CODE")
    # These properties introduce extra filesystem/credential inputs. A path
    # property hash cannot seal the underlying content or a mounted image.
    native_empty_credentials(unit, fields, runner)
    for key in ("BindPaths", "BindReadOnlyPaths", "RootDirectory", "RootImage"):
        value = fields.get(key, "")
        require(not value or value == [""], "PRODUCER_UNSEALED_EXECUTION_SOURCE")
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
        if kind == "envfile":
            require(not CODE_LOADING_ENV.search(raw), "PRODUCER_UNSEALED_ENVIRONMENT_CODE")
        files.append((kind, sha(str(source).encode()), sha(raw)))
    stable = {key: fields[key] for key in STABLE_PROPERTIES
              if key != "DropInPaths" and key not in EXECUTION_PROPERTIES and key in fields}
    stable["native_execution"] = native_execution_configuration(unit, fields, runner)
    if unit in maintenance.TIMERS:
        stable["timer_target"] = basic["Triggers"]
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
