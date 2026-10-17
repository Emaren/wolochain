#!/usr/bin/env python3
"""Reproduce both reviewed PR25 defects on immutable source, offline only."""
import io
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile

BASE = "d3b7586dc13c9ab38d634acbc0572e350463a325"
ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = {"TestBaselineMultiLegIndependentPayouts", "TestBaselinePartialLegFullRefund"}


def main():
    archive = subprocess.check_output(["git", "archive", BASE], cwd=ROOT, timeout=30)
    if len(archive) > 64 << 20:
        raise RuntimeError("baseline_archive_limit")
    with tempfile.TemporaryDirectory(prefix="satchel-multileg-before-") as folder:
        target = pathlib.Path(folder).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            members = source.getmembers()
            if len(members) > 10000 or sum(m.size for m in members) > 256 << 20:
                raise RuntimeError("baseline_archive_limit")
            for member in members:
                name = pathlib.PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                    raise RuntimeError("baseline_archive_refused")
            source.extractall(target, members=members, filter="data")
        shutil.copyfile(ROOT / "tests/fixtures/satchel-multileg-before_test.go.txt",
                        target / "internal/satchelservice/returns_multileg_before_test.go")
        env = dict(os.environ, GOPROXY="off", GOSUMDB="off", GOWORK="off", GOENV="off")
        result = subprocess.run(["go", "test", "-tags=go1.27", "./internal/satchelservice",
                                 "-run", "^TestBaseline(MultiLegIndependentPayouts|PartialLegFullRefund)$",
                                 "-count=1", "-json"], cwd=target, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        failures = {e["Test"] for e in events if e.get("Action") == "fail" and "Test" in e}
        output = "".join(e.get("Output", "") for e in events)
        if result.returncode == 0 or failures != TESTS or "operation_return_already_allocated" not in output or "owner_return_policy_refused" not in output:
            raise RuntimeError("historical_defect_not_reproduced")
        print(json.dumps({"baseline": BASE, "expected_failures": sorted(failures),
                          "reproduced": True, "network": False, "production_actions": False}))


if __name__ == "__main__":
    main()
