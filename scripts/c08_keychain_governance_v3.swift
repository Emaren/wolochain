// macOS-only C08 governance signing transport: private P-256 key stays in login Keychain.
// Software Keychain, NOT Secure Enclave, NOT Cosmos/Funding signer.
// Public key exported X9.63; signature is ASN.1 DER ECDSA-SHA256.
// No password, key export, wallet send, token or financial release.
import Foundation
import Security
import CryptoKit
import Darwin

let tagString = "aoe2war-c08-owner-policy-only-keychain-p256-v3-20261108"
let tag = Data(tagString.utf8)
let domain = Data("AOE2WAR-WOLO-C08-KEYCHAIN-GOVERNANCE-ADOPTION-V3\0".utf8)
let keyType = kSecAttrKeyTypeECSECPrimeRandom
func hex(_ d:Data)->String { d.map{String(format:"%02x",$0)}.joined() }
func fail(_ s:String)->Never { print("HOLD_C08_KEYCHAIN_V3_\(s)");exit(3) }
func query()->[String:Any] {
 return [
  kSecClass as String:kSecClassKey,
  kSecAttrKeyType as String:keyType,
  kSecAttrApplicationTag as String:tag,
  kSecReturnRef as String:true,
  kSecMatchLimit as String:kSecMatchLimitOne
 ]
}
func getKey(create:Bool)->SecKey {
 var result:CFTypeRef?
 let status=SecItemCopyMatching(query() as CFDictionary,&result)
 if status==errSecSuccess {
   guard let ref=result,CFGetTypeID(ref)==SecKeyGetTypeID() else {fail("KEY_REFERENCE_INVALID")}
   return ref as! SecKey
 }
 if status != errSecItemNotFound {fail("KEYCHAIN_LOOKUP_REJECTED")}
 if !create {fail("GOVERNANCE_KEY_NOT_ENROLLED")}
 var error:Unmanaged<CFError>?
 let attrs:[String:Any]=[
  kSecAttrKeyType as String:keyType,
  kSecAttrKeySizeInBits as String:256,
  kSecPrivateKeyAttrs as String:[
   kSecAttrIsPermanent as String:true,
   kSecAttrApplicationTag as String:tag,
   kSecAttrLabel as String:"AOE2WAR C08 GOVERNANCE POLICY ONLY, NO FUNDED PERMITS"
  ]
 ]
 guard let key=SecKeyCreateRandomKey(attrs as CFDictionary,&error) else {
   fail("KEY_GENERATION_REJECTED")
 }
 return key
}
func publicBytes(_ key:SecKey)->Data {
 guard let pub=SecKeyCopyPublicKey(key) else {fail("PUBLIC_KEY_UNAVAILABLE")}
 var error:Unmanaged<CFError>?
 guard let raw=SecKeyCopyExternalRepresentation(pub,&error) as Data?,
       raw.count==65 && raw[0]==4 else {fail("PUBLIC_KEY_X963_UNQUALIFIED")}
 return raw
}
func fileBytes(_ path:String)->Data {
 var s=stat()
 guard lstat(path,&s)==0 && (s.st_mode & mode_t(S_IFMT))==mode_t(S_IFREG)
     && s.st_uid==geteuid() && (s.st_mode & 0o777)==0o600
     && s.st_nlink==1 && s.st_size>0 && s.st_size<16384
 else {fail("PRIVATE_INPUT_PATH_OR_MODE_UNSAFE")}
 let fd=Darwin.open(path,O_RDONLY|O_NOFOLLOW)
 guard fd>=0 else {fail("PRIVATE_INPUT_OPEN_FAILED")}
 defer{Darwin.close(fd)}
 var buf=[UInt8](repeating:0,count:Int(s.st_size))
 let n=buf.withUnsafeMutableBytes { ptr in
  Darwin.read(fd,ptr.baseAddress,ptr.count)
 }
 guard n==s.st_size else {fail("PRIVATE_INPUT_SHORT_READ")}
 return Data(buf)
}
func write0600(_ path:String,_ raw:Data) {
 guard raw.count>0 && raw.count<16384 else {fail("OUTPUT_LENGTH_INVALID")}
 let fd=Darwin.open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,mode_t(0o600))
 guard fd>=0 else {fail("OWNER_PRIVATE_OUTPUT_EXISTS_OR_UNSAFE")}
 defer{Darwin.close(fd)}
 let n=raw.withUnsafeBytes { ptr in
  Darwin.write(fd,ptr.baseAddress,ptr.count)
 }
 guard n==raw.count && fsync(fd)==0 else {fail("SIGNATURE_WRITE_FAILED")}
}
guard CommandLine.arguments.count>=2 else {fail("USAGE")}
let mode=CommandLine.arguments[1]
if mode=="enroll" {
 guard CommandLine.arguments.count==3 else {fail("ENROLL_ARGUMENTS")}
 let key=getKey(create:true)
 let pub=publicBytes(key)
 let path=CommandLine.arguments[2]
 if access(path,F_OK)==0 {
  guard fileBytes(path)==pub else {fail("PUBLIC_OWNER_ENROLLMENT_CHANGED")}
 } else {
  write0600(path,pub)
 }
 print("PASS_C08_KEYCHAIN_P256_OWNER_ENROLLED_PUBLIC_ONLY")
 print("OWNER_PUBLIC_X963_SHA256",hex(Data(SHA256.hash(data:pub))))
 print("PRIVATE_KEY_EXPORTED",false)
 print("FUNDED_AUTHORIZATION",false)
} else if mode=="public" {
 guard CommandLine.arguments.count==2 else {fail("PUBLIC_ARGUMENTS")}
 let pub=publicBytes(getKey(create:false))
 print("PASS_C08_KEYCHAIN_OWNER_PUBLIC_IDENTITY",hex(Data(SHA256.hash(data:pub))))
} else if mode=="sign" {
 guard CommandLine.arguments.count==4 else {fail("SIGN_ARGUMENTS")}
 let raw=fileBytes(CommandLine.arguments[2])
 guard raw.starts(with:domain) && raw.count<8192 else {fail("SIGN_DOMAIN_NOT_C08_GOVERNANCE_V3")}
 let key=getKey(create:false)
 var error:Unmanaged<CFError>?
 guard let signature=SecKeyCreateSignature(key,
   .ecdsaSignatureMessageX962SHA256,raw as CFData,&error) as Data?,
   signature.count>=64 && signature.count<=80 else {fail("SIGNING_REJECTED")}
 write0600(CommandLine.arguments[3],signature)
 print("PASS_C08_NONINTERACTIVE_KEYCHAIN_POLICY_SIGNATURE_CREATED")
 print("SIGNATURE_SHA256",hex(Data(SHA256.hash(data:signature))))
 print("FUNDED_AUTHORIZATION",false)
} else {fail("UNSUPPORTED_MODE")}
