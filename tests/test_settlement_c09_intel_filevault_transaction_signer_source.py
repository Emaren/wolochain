"""C09 separate native FileVault Intel-only P-256 owner signer source guard."""
from pathlib import Path
import hashlib
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/c09_intel_filevault_transaction_p256_v1.swift"
SHA="592f3a21c2b2726f36b8bb67fa6b93941cab161c3cb5171a30b4cefbd1a5b159"

class IntelFileVaultC09Signer(unittest.TestCase):
    def setUp(self):
        self.content=SOURCE.read_bytes()
        self.swift=self.content.decode("utf-8")
    def test_exact_physically_compiled_intel_source_bytes(self):
        self.assertEqual(hashlib.sha256(self.content).hexdigest(),SHA)
    def test_distinct_one_use_domain_and_private_key_enrollment(self):
        for required in (
            "aoe2war-c09-transaction-only-intel-filevault-p256-v1-20261109",
            "AOE2WAR-WOLO-C09-TRANSACTION-SPECIFIC-P256-V1",
            "SecKeyCreateRandomKey","kSecAttrIsPermanent",
            "SecKeyCreateSignature","SecKeyCopyPublicKey",
            "SecKeyCopyExternalRepresentation","kSecAttrApplicationTag",
            "x86_64","FileVault is On.","NONROOT_OWNER_REQUIRED",
            "PRIVATE_KEY_EXPORTED", "C09_TRANSACTION_SIGNED",
            "FINANCIAL_RELEASE_AUTHORIZED", "false",
            "SIGNED_MESSAGE_NOT_C09_EXACT_DOMAIN",
            "O_CREAT|O_EXCL|O_NOFOLLOW", "fsync(fd)==0",
            "OWNER_OUTPUT_EXISTS","PUBLIC_KEY_ENROLLMENT_DRIFT",
        ):
            self.assertIn(required,self.swift)
    def test_no_policy_signer_or_custody_access_or_export(self):
        for banned in (
            "aoe2war-c08-owner-policy-only-keychain-p256",
            "SecKeyCopyExternalRepresentation(key",
            "SecKeyCopyExternalRepresentation(privateKey",
            "kSecAttrTokenIDSecureEnclave",
            "wolochaind tx","8092","8094","8095",
            "http://","https://","systemctl",
            "security unlock-keychain","SecItemDelete",
            "SecKeyCreateDecryptedData",
        ):
            self.assertNotIn(banned,self.swift)
    def test_owner_only_no_bypass_or_overwrite(self):
        self.assertIn('if mode=="enroll"',self.swift)
        self.assertIn('} else if mode=="public"',self.swift)
        self.assertIn('} else if mode=="sign"',self.swift)
        self.assertIn("getKey(create:false)",self.swift)
        self.assertIn("SecItemCopyMatching",self.swift)
        self.assertIn("getuid() != 0",self.swift)
        self.assertIn("PRIVATE_INPUT_UNSAFE",self.swift)
        self.assertIn("PRIVATE_INPUT_CHANGED",self.swift)
if __name__=="__main__":unittest.main()
