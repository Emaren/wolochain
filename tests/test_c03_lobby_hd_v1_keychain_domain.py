"""Native Swift one-purpose Lobby signing domain; no production Keychain access."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SWIFT=ROOT/'scripts/c03_lobby_hd_v1_owner_keychain.swift'

class LobbyMacKeychainDomainTests(unittest.TestCase):
    def test_purpose_locked_distinct_from_social(self):
        source=SWIFT.read_text()
        self.assertIn('aoe2war-WE1-chat-lobby-HD-v1-P256-v1-20261120',source)
        self.assertIn('AOE2WAR-WE1-LOBBY-HD-V1-SQL-ONLY-V1\\0',source)
        self.assertNotIn('aoe2war-WE1-chat-social-HD-v2-P256-v1-20261120',source)
        self.assertNotIn('recoveryDomain',source)
        self.assertIn('WRONG_SIGNING_PURPOSE',source)
        self.assertIn('let pub=publicBytes(getKey(create:true))',source)
        self.assertIn('let key=getKey(create:false)',source)
        self.assertNotIn('SecKeyCopyExternalRepresentation(key',source)
        self.assertIn('msg.count<8192',source)

    @unittest.skipUnless(sys.platform=='darwin' and shutil.which('swift'),'needs native macOS Swift Foundation')
    def test_native_actual_swift_eight_negative_cases(self):
        source=SWIFT.read_text()
        block=source[source.index('let sqlDomain='):source.index('func stop(')]
        program='import Foundation\n'+block+'''
let cases:[(String,Data,Bool)]=[
("valid",sqlDomain+Data("{}".utf8),true),
("domain-only",sqlDomain,false),
("empty",Data(),false),
("social-sql",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\\0{}".utf8),false),
("social-recovery",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1\\0{}".utf8),false),
("wrong-lobby",Data("AOE2WAR-WE1-LOBBY-HD-V1-FINANCIAL-V1\\0{}".utf8),false),
("lowercase",Data("aoe2war-WE1-LOBBY-HD-V1-SQL-ONLY-V1\\0{}".utf8),false),
("oversize",sqlDomain+Data(repeating:65,count:8192),false)]
for (name,data,pass) in cases {
 if acceptedPurpose(data) != pass {
   fputs("FAIL_\\(name)\\n",stderr)
   exit(3)
 }
}
print("PASS_LOBBY_SWIFT_8_CASES")
'''
        with tempfile.TemporaryDirectory(prefix='lobby-swift-domain-') as td:
            path=Path(td)/'domain.swift'
            path.write_text(program)
            r=subprocess.run(['swift',str(path)],capture_output=True,text=True,timeout=110)
            self.assertEqual(r.returncode,0,r.stdout+' '+r.stderr)
            self.assertIn('PASS_LOBBY_SWIFT_8_CASES',r.stdout)

if __name__=='__main__':unittest.main()
