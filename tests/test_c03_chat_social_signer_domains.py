"""Exact Social Mac Keychain signing-domain compatibility; no private-key use."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SIGNER = Path(__file__).resolve().parents[1] / 'scripts/c03_chat_social_owner_keychain_v1.swift'
SQL = 'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\\0'
RECOVERY = 'AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1\\0'

class SwiftSocialSignerDomainTests(unittest.TestCase):
    def test_only_two_exact_nonoverlapping_domains(self):
        source=SIGNER.read_text()
        self.assertIn('let sqlDomain=Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\\0".utf8)',source)
        self.assertIn('let recoveryDomain=Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1\\0".utf8)',source)
        self.assertIn('guard acceptedPurpose(msg) else {stop("WRONG_SIGNING_PURPOSE")}',source)
        self.assertIn('return msg.count<8192 && (original != recovery)',source)
        self.assertNotIn('create:true',source[source.index('} else if mode=="sign"'):])
        self.assertNotIn('SecKeyCopyExternalRepresentation(key',source)
        self.assertNotIn('LIBRARY',SQL+RECOVERY)
        self.assertFalse(SQL.startswith(RECOVERY) or RECOVERY.startswith(SQL))
        self.assertNotIn('BET',SQL+RECOVERY)

    @unittest.skipUnless(sys.platform=='darwin' and shutil.which('swift'),
                         'Native macOS Swift Foundation execution required')
    def test_native_swift_exact_allowed_and_denied_purposes(self):
        source=SIGNER.read_text()
        a=source.index('let sqlDomain=')
        b=source.index('func stop(',a)
        verified_source=source[a:b]
        swift='''import Foundation
''' + verified_source + '''
let cases:[(String,Data,Bool)] = [
 ("sql",sqlDomain+Data("{}".utf8),true),
 ("original-root-enroll",sqlDomain+Data("ROOT_TRUST_ENROLL_ONLY_V1\\\\0{}".utf8),true),
 ("separate-auto-inverse-recovery",recoveryDomain+Data("{}".utf8),true),
 ("empty",Data(),false),
 ("truncated-sql-without-null",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1".utf8),false),
 ("truncated-recovery-without-null",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V1".utf8),false),
 ("sql-domain-only",sqlDomain,false),
 ("recovery-domain-only",recoveryDomain,false),
 ("unknown-domain",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-UNREVIEWED-ONLY-V1\\\\0{}".utf8),false),
 ("financial-domain",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-FINANCIAL-ONLY-V1\\\\0{}".utf8),false),
 ("partial-recovery",Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-AUTO-INVERSE-RECOVERY-ONLY-V\\\\0{}".utf8),false),
 ("oversized-sql",sqlDomain+Data(repeating:0x41,count:8192),false),
 ("oversized-recovery",recoveryDomain+Data(repeating:0x41,count:8192),false)
]
for (name,message,expected) in cases {
 let actual=acceptedPurpose(message)
 if actual != expected {
  fputs("FAIL_PURPOSE_\\\\(name)\\\\n",stderr)
  exit(3)
 }
}
print("PASS_NATIVE_SWIFT_SOCIAL_TWO_DOMAINS_13_CASES")
'''
        with tempfile.TemporaryDirectory(prefix='we1-swift-domain-test-') as tmp:
            path=Path(tmp)/'native.swift'
            path.write_text(swift)
            r=subprocess.run(['swift',str(path)],capture_output=True,text=True,timeout=100)
            self.assertEqual(r.returncode,0,r.stdout+' '+r.stderr)
            self.assertIn('PASS_NATIVE_SWIFT_SOCIAL_TWO_DOMAINS_13_CASES',r.stdout)

if __name__=='__main__':unittest.main()
