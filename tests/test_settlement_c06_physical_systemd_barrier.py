"""Physical barrier primitives on a disposable hosted Linux runner only.

Uses unique fixture units, never real financial, database or website units.
No production authority or systemd-wide stop operations.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import settlement_c06_native_service_barrier as b

@unittest.skipUnless(sys.platform.startswith("linux") and os.geteuid()==0
                     and os.environ.get("CI")=="true"
                     and os.environ.get("GITHUB_ACTIONS")=="true"
                     and os.environ.get("C06_DISPOSABLE_BARRIER")=="1",
                     "disposable hosted Linux fixture only")
class PhysicalBarrier(unittest.TestCase):
    def test_real_activation_denial_and_individual_release(self):
        self.assertTrue(Path("/run/systemd/system").is_dir())
        self.assertFalse(Path("/mnt/HC_Volume_105319120").exists())
        self.assertFalse(b.HOLD.parent.exists())
        for unit in ("wolochaind-mainnet.service","aoe2hdbets-web-prod.service"):
            state=subprocess.run(["systemctl","show","-p","LoadState","--value",unit],
                                 capture_output=True,text=True,timeout=10)
            self.assertIn(state.stdout.strip(),("","not-found"))
        run=b.native_run
        tag="c06-disposable-"+uuid.uuid4().hex
        units=[tag+"-a.service",tag+"-b.service"]
        fragments={}
        gates={}
        with tempfile.TemporaryDirectory(prefix=tag,dir="/var/lib") as td:
            hold=Path(td)/"hold"
            marker=b"DISPOSABLE ONLY\n"
            try:
                for u in units:
                    path=Path("/etc/systemd/system")/u
                    gate=path.parent/(u+".d")/b.DROPIN
                    self.assertFalse(os.path.lexists(path))
                    self.assertFalse(os.path.lexists(gate.parent))
                    b.new_root_file(path,b"[Service]\nType=simple\nExecStart=/usr/bin/sleep 300\nRestart=on-failure\n")
                    fragments[u]=path
                    gate.parent.mkdir(mode=0o755)
                    gates[u]=gate
                run(["systemctl","daemon-reload"])
                for u in units:
                    run(["systemctl","start","--",u])
                    self.assertEqual(b.show(u,run)["ActiveState"],"active")
                b.new_root_file(hold,marker)
                for u in units:b.new_root_file(gates[u],b.gate_bytes(hold))
                run(["systemctl","daemon-reload"])
                for u in units:
                    b.effective_gate(u,hold,run)
                    run(["systemctl","stop","--",u])
                    run(["systemctl","start","--",u])
                    self.assertEqual(b.show(u,run)["ActiveState"],"inactive")
                    self.assertEqual(b.show(u,run)["MainPID"],"0")
                    b.exact_root_file(gates[u],b.gate_bytes(hold))
                # Actual process exit after one gate is removed: remaining
                # persistent gate stays effective after a daemon reload.
                pid=os.fork()
                if pid==0:
                    gates[units[0]].unlink()
                    b.sync_dir(gates[units[0]].parent)
                    os._exit(74)
                _,status=os.waitpid(pid,0)
                self.assertEqual(os.WEXITSTATUS(status),74)
                run(["systemctl","daemon-reload"])
                b.exact_root_file(hold,marker)
                b.effective_gate(units[1],hold,run)
                run(["systemctl","start","--",units[1]])
                self.assertEqual(b.show(units[1],run)["ActiveState"],"inactive")
                run(["systemctl","start","--",units[0]])
                self.assertEqual(b.show(units[0],run)["ActiveState"],"active")
                # Explicit disposable-fixture restoration only.
                gates[units[1]].unlink()
                b.sync_dir(gates[units[1]].parent)
                run(["systemctl","daemon-reload"])
                run(["systemctl","start","--",units[1]])
                self.assertEqual(b.show(units[1],run)["ActiveState"],"active")
                print("PASS_ACTUAL_DISPOSABLE_SYSTEMD_TWO_ACTIVATION_DENIALS_CRASH_RETAINED_GATE_EXPLICIT_RESTORE",flush=True)
            finally:
                for u in fragments:
                    subprocess.run(["systemctl","stop","--",u],capture_output=True,timeout=20)
                for g in gates.values():
                    if g.exists():
                        b.exact_root_file(g,b.gate_bytes(hold))
                        g.unlink()
                    g.parent.rmdir()
                for path in fragments.values():path.unlink()
                run(["systemctl","daemon-reload"])
if __name__=="__main__":unittest.main()
