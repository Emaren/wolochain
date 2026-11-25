#!/usr/bin/env python3
"""Bounded read-only observation of exact settlement-bearer holders in /proc.

No credential or credential digest is emitted. This is current local process
metadata, never a complete producer inventory, fence, or release authority.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone

PROC = Path('/proc')
LANES = {'primary': 'wolochain-mainnet-settlement.service',
         'founder': 'wolochain-founder-rewards-settlement.service'}
MAX_PIDS = 4096
MAX_ENV = 1 << 20
MAX_TOTAL = 64 << 20
MAX_SECONDS = 30
SAFE_UNIT = re.compile(r'(?:aoe2hdbets|aoe2dewarwagers|aoe2war|aoe2-wolo|wolochain|wolochaind)[A-Za-z0-9_.@:-]*\.(?:service|scope)$')
SAFE_KEYS = {b'WOLO_SETTLEMENT_AUTH_TOKEN', b'WOLO_FOUNDER_SETTLEMENT_AUTH_TOKEN'}


class BudgetExceeded(ValueError):
    pass


def read_proc(pid, filename, limit, budget=None):
    if not str(pid).isdecimal() or int(pid) <= 0 or filename not in {'environ', 'stat', 'cgroup'}:
        raise ValueError('INVALID_PROCESS_REFERENCE')
    fd = os.open(PROC / str(pid) / filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('UNSAFE_PROCESS_METADATA')
        data = bytearray()
        while len(data) <= limit:
            remaining = MAX_TOTAL - budget[0] if budget is not None else limit
            chunk = os.read(fd, min(65536, limit + 1 - len(data), remaining + 1))
            if budget is not None:
                budget[0] += len(chunk)
                if budget[0] > MAX_TOTAL:
                    raise BudgetExceeded('TOTAL_METADATA_LIMIT')
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > limit:
            raise ValueError('PROCESS_METADATA_LIMIT')
        return bytes(data)
    finally:
        os.close(fd)


def generation(pid):
    fields = read_proc(pid, 'stat', 8192).rsplit(b')', 1)[-1].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise ValueError('PROCESS_GENERATION_UNAVAILABLE')
    return fields[19]


def entries(raw):
    result = []
    for item in raw.split(b'\0'):
        key, sep, value = item.partition(b'=')
        if sep and value:
            result.append((key, value))
    return result


def target_pid(unit, deadline):
    if unit not in LANES.values():
        raise ValueError('INVALID_TARGET_UNIT')
    p = subprocess.run(['systemctl', 'show', '-P', 'MainPID', unit],
                       capture_output=True, timeout=max(0.001, min(8, deadline - time.monotonic())), check=True)
    raw = p.stdout.strip()
    if len(raw) > 16 or not raw.isdigit() or int(raw) <= 0:
        raise ValueError('TARGET_PROCESS_UNAVAILABLE')
    return int(raw)


def targets(deadline, budget=None):
    result = {}
    for lane, unit in LANES.items():
        pid = target_pid(unit, deadline)
        before = generation(pid)
        values = [v for k,v in entries(read_proc(pid, 'environ', MAX_ENV, budget))
                  if k == b'WOLO_SETTLEMENT_AUTH_TOKEN']
        if len(values) != 1 or len(values[0]) < 16:
            raise ValueError('TARGET_AUTHORITY_UNAVAILABLE')
        if before != generation(pid) or pid != target_pid(unit, deadline):
            raise ValueError('TARGET_CHANGED_DURING_OBSERVATION')
        result[lane] = (pid, before, values[0])
    return result


def identity(pid, credentials):
    units = set()
    for line in read_proc(pid, 'cgroup', 8192).decode('ascii', errors='replace').splitlines():
        for part in line.split(':', 2)[-1].split('/'):
            if part.endswith(('.service', '.scope')):
                units.add(part)
    return {'proc_directory_uid': (PROC / str(pid)).stat().st_uid,
            'units': [({'name_disclosure': 'WITHHELD_CREDENTIAL_BEARING_LABEL'}
                       if any(token in u.encode() for token in credentials) else
                       {'name': u} if SAFE_UNIT.fullmatch(u) else
                       {'name_sha256': hashlib.sha256(u.encode()).hexdigest()})
                      for u in sorted(units)]}


def inspect():
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    budget = [0]
    expected = targets(deadline, budget)
    pids = []
    with os.scandir(PROC) as scan:
        for entry in scan:
            if entry.name.isdecimal():
                pids.append(int(entry.name))
                if len(pids) > MAX_PIDS:
                    raise ValueError('PROCESS_COUNT_LIMIT')
    observed, incomplete, matched = 0, 0, []
    for pid in sorted(pids):
        if time.monotonic() >= deadline:
            raise ValueError('OBSERVATION_DEADLINE')
        if budget[0] >= MAX_TOTAL:
            raise ValueError('TOTAL_METADATA_LIMIT')
        try:
            before = generation(pid)
            raw = read_proc(pid, 'environ', min(MAX_ENV, MAX_TOTAL - budget[0]), budget)
            found = {}
            for key, value in entries(raw):
                lanes = [lane for lane, (_, _, token) in expected.items() if value == token]
                if lanes:
                    name = key.decode('ascii') if key in SAFE_KEYS else 'OTHER_ENVIRONMENT_KEY_WITHHELD'
                    found.setdefault(name, set()).update(lanes)
            details = identity(pid, [v[2] for v in expected.values()]) if found else None
            if before != generation(pid):
                raise ValueError('PROCESS_CHANGED')
            if found:
                matched.append({'pid': pid, **details, 'exact_value_matches': {k: sorted(v) for k,v in found.items()}})
            observed += 1
        except BudgetExceeded:
            raise
        except (OSError, ValueError):
            incomplete += 1
    if time.monotonic() >= deadline or targets(deadline, budget) != expected or time.monotonic() >= deadline:
        raise ValueError('TARGET_OR_DEADLINE_CHANGED')
    return {'schema': 'aoe2war.wolo.exact-bearer-holder-observation.v1',
            'observed_at_utc': datetime.now(timezone.utc).isoformat(),
            'processes_listed': len(pids), 'processes_observed': observed,
            'processes_unavailable_or_changed': incomplete, 'environment_bytes_read': budget[0],
            'bearer_lanes_distinct': expected['primary'][2] != expected['founder'][2],
            'holders': matched, 'all_listed_processes_observed': incomplete == 0,
            'observation_atomic': False, 'complete_producer_inventory': False,
            'financial_producers_fenced': False, 'release_authorized': False,
            'production_mutated': False,
            'limits': ['Exact current environment values only; no credential values or digests emitted.',
                       'Does not cover files, inherited open descriptors, embedded or loaded secrets, operator sessions, dormant units, or external holders.',
                       'Process generations and target credentials are checked, but future forks/restarts and concurrent observation gaps remain unknown.',
                       'A bearer grants API authority, not proof of direct signer-key ownership.']}


def main():
    if sys.argv[1:] not in ([], ['--inspect']) or os.geteuid() != 0:
        print('BLOCKED: root read-only inspection required', file=sys.stderr)
        return 2
    try:
        result = inspect()
    except (OSError, ValueError, subprocess.SubprocessError):
        print('BLOCKED: bounded authority observation unavailable', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
