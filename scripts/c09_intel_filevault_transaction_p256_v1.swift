// C09 owner transaction-only P-256 software Keychain identity on FileVault Intel.
// A NEW key distinct from C08 M1 policy signer. No Cosmos key, no execution.
// Create/public public-only enrollment permitted; any actual signing remains
// additionally gated by fresh exact C09 owner direction and physical C01-C07.
import Foundation
import Security
import CryptoKit
import Darwin

let tagString = "aoe2war-c09-transaction-only-intel-filevault-p256-v1-20261109"
let tag = Data(tagString.utf8)
let domain = Data("AOE2WAR-WOLO-C09-TRANSACTION-SPECIFIC-P256-V1\0".utf8)
let keyType = kSecAttrKeyTypeECSECPrimeRandom

func hex(_ data:Data)->String {
  return data.map { String(format:"%02x",$0) }.joined()
}
func stop(_ reason:String)->Never {
  print("HOLD_C09_INTEL_KEYCHAIN_\(reason)")
  exit(3)
}
func commandOutput(_ path:String,_ args:[String])->String {
  let process=Process()
  process.executableURL=URL(fileURLWithPath:path)
  process.arguments=args
  let pipe=Pipe()
  process.standardOutput=pipe
  process.standardError=Pipe()
  do { try process.run() } catch { stop("HOST_PREFLIGHT_NOT_AVAILABLE") }
  process.waitUntilExit()
  guard process.terminationStatus==0 else { stop("HOST_PREFLIGHT_FAILED") }
  let data=pipe.fileHandleForReading.readDataToEndOfFile()
  guard data.count<4096,let result=String(data:data,encoding:.utf8) else {
    stop("HOST_PREFLIGHT_BAD_OUTPUT")
  }
  return result.trimmingCharacters(in:.whitespacesAndNewlines)
}
func hostOK() {
  guard geteuid()==getuid() && getuid() != 0 else {stop("NONROOT_OWNER_REQUIRED")}
  guard commandOutput("/usr/bin/uname",["-m"])=="x86_64" else {
    stop("INTEL_X86_64_REQUIRED")
  }
  guard commandOutput("/usr/bin/fdesetup",["status"])=="FileVault is On." else {
    stop("FILEVAULT_REQUIRED")
  }
}
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
 let code=SecItemCopyMatching(query() as CFDictionary,&result)
 if code==errSecSuccess {
   guard let reference=result,CFGetTypeID(reference)==SecKeyGetTypeID() else {
     stop("KEY_TYPE_MISMATCH")
   }
   return reference as! SecKey
 }
 guard code==errSecItemNotFound else {stop("KEYCHAIN_LOOKUP_UNAVAILABLE")}
 guard create else {stop("TRANSACTION_KEY_NOT_ENROLLED")}
 var error:Unmanaged<CFError>?
 let attrs:[String:Any]=[
  kSecAttrKeyType as String:keyType,
  kSecAttrKeySizeInBits as String:256,
  kSecPrivateKeyAttrs as String:[
    kSecAttrIsPermanent as String:true,
    kSecAttrApplicationTag as String:tag,
    kSecAttrLabel as String:"AOE2WAR C09 FILEVAULT INTEL EXACT TRANSACTION OWNER ONLY"
  ]
 ]
 guard let key=SecKeyCreateRandomKey(attrs as CFDictionary,&error) else {
  stop("KEY_CREATION_FAILED")
 }
 return key
}
func publicBytes(_ key:SecKey)->Data {
 guard let publicKey=SecKeyCopyPublicKey(key) else {stop("PUBLIC_NOT_AVAILABLE")}
 var error:Unmanaged<CFError>?
 guard let raw=SecKeyCopyExternalRepresentation(publicKey,&error) as Data?,
       raw.count==65 && raw[0]==4 else {stop("PUBLIC_FORMAT_INVALID")}
 return raw
}
func input0600(_ path:String)->Data {
 var st=stat()
 guard lstat(path,&st)==0 && (st.st_mode & mode_t(S_IFMT))==mode_t(S_IFREG)
    && st.st_uid==geteuid() && (st.st_mode & 0o777)==0o600
    && st.st_nlink==1 && st.st_size>0 && st.st_size<8192 else {
   stop("PRIVATE_INPUT_UNSAFE")
 }
 let fd=Darwin.open(path,O_RDONLY|O_NOFOLLOW)
 guard fd>=0 else {stop("PRIVATE_INPUT_OPEN")}
 defer { Darwin.close(fd) }
 var bytes=[UInt8](repeating:0,count:Int(st.st_size))
 let length=bytes.withUnsafeMutableBytes { ptr in
   Darwin.read(fd,ptr.baseAddress,ptr.count)
 }
 guard length==st.st_size else {stop("PRIVATE_INPUT_CHANGED")}
 return Data(bytes)
}
func write0600(_ path:String,_ content:Data) {
 guard content.count>0 && content.count<8192 else {stop("OUTPUT_LENGTH")}
 let fd=Darwin.open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,mode_t(0o600))
 guard fd>=0 else {stop("OWNER_OUTPUT_EXISTS")}
 defer { Darwin.close(fd) }
 let count=content.withUnsafeBytes { ptr in
   Darwin.write(fd,ptr.baseAddress,ptr.count)
 }
 guard count==content.count && fsync(fd)==0 else {stop("OUTPUT_WRITE")}
}
hostOK()
guard CommandLine.arguments.count>=2 else {stop("ARGUMENTS")}
let mode=CommandLine.arguments[1]
if mode=="enroll" {
 guard CommandLine.arguments.count==3 else {stop("ENROLL_ARGUMENTS")}
 let bytes=publicBytes(getKey(create:true))
 let path=CommandLine.arguments[2]
 if access(path,F_OK)==0 {
   guard input0600(path)==bytes else {stop("PUBLIC_KEY_ENROLLMENT_DRIFT")}
 } else {
   write0600(path,bytes)
 }
 print("PASS_C09_SEPARATE_INTEL_FILEVAULT_KEYCHAIN_P256_PUBLIC_ENROLLED")
 print("C09_PUBLIC_X963_SHA256",hex(Data(SHA256.hash(data:bytes))))
 print("PRIVATE_KEY_EXPORTED",false)
 print("C09_TRANSACTION_SIGNED",false)
 print("FINANCIAL_RELEASE_AUTHORIZED",false)
} else if mode=="public" {
 guard CommandLine.arguments.count==2 else {stop("PUBLIC_ARGUMENTS")}
 let bytes=publicBytes(getKey(create:false))
 print("PASS_C09_INTEL_FILEVAULT_PUBLIC_IDENTITY",hex(Data(SHA256.hash(data:bytes))))
} else if mode=="sign" {
 guard CommandLine.arguments.count==4 else {stop("SIGN_ARGUMENTS")}
 let bytes=input0600(CommandLine.arguments[2])
 guard bytes.starts(with:domain) && bytes.count>=160 && bytes.count<8192 else {
    stop("SIGNED_MESSAGE_NOT_C09_EXACT_DOMAIN")
 }
 var error:Unmanaged<CFError>?
 guard let signature=SecKeyCreateSignature(getKey(create:false),
    .ecdsaSignatureMessageX962SHA256,bytes as CFData,&error) as Data?,
    signature.count>=64 && signature.count<=80 else {
   stop("SIGNATURE_REJECTED")
 }
 write0600(CommandLine.arguments[3],signature)
 print("PASS_C09_FILEVAULT_TRANSACTION_SIGNATURE_CREATED")
 print("C09_SIGNATURE_SHA256",hex(Data(SHA256.hash(data:signature))))
 print("FINANCIAL_RELEASE_AUTHORIZED",false)
} else {stop("MODE_NOT_ALLOWED")}
