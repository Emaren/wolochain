// Owner-M1 purpose-specific Chat Social V2 HD SQL permit identity. NEVER custody, C08 or PRODUCT.
// Private key stays in macOS login Keychain. Sign exact DOMAIN-prefixed packets only.
import Foundation
import Security
import CryptoKit
import Darwin

let tag=Data("aoe2war-WE1-chat-social-HD-v2-P256-v1-20261120".utf8)
let domain=Data("AOE2WAR-WE1-CHAT-SOCIAL-HD-V2-SQL-ONLY-V1\0".utf8)
func stop(_ s:String)->Never { print("HOLD_CHAT_SOCIAL_OWNER_KEYCHAIN_\(s)");exit(3) }
func hex(_ d:Data)->String { d.map{String(format:"%02x",$0)}.joined() }
func request()->[String:Any] {
 [kSecClass as String:kSecClassKey,
  kSecAttrKeyType as String:kSecAttrKeyTypeECSECPrimeRandom,
  kSecAttrApplicationTag as String:tag,
  kSecReturnRef as String:true,
  kSecMatchLimit as String:kSecMatchLimitOne]
}
func getKey(create:Bool)->SecKey {
 var result:CFTypeRef?
 let found=SecItemCopyMatching(request() as CFDictionary,&result)
 if found==errSecSuccess {
   guard let obj=result,CFGetTypeID(obj)==SecKeyGetTypeID() else {stop("BAD_KEY_REFERENCE")}
   return obj as! SecKey
 }
 if found != errSecItemNotFound {stop("LOOKUP_REJECTED")}
 if !create {stop("KEY_NOT_ENROLLED")}
 var error:Unmanaged<CFError>?
 let attrs:[String:Any]=[
   kSecAttrKeyType as String:kSecAttrKeyTypeECSECPrimeRandom,
   kSecAttrKeySizeInBits as String:256,
   kSecPrivateKeyAttrs as String:[
      kSecAttrIsPermanent as String:true,
      kSecAttrApplicationTag as String:tag,
      kSecAttrLabel as String:"AOE2WAR WE1 CHAT SOCIAL V2 HD SQL ONLY - NO FUNDS"
   ]]
 guard let k=SecKeyCreateRandomKey(attrs as CFDictionary,&error) else {stop("KEY_CREATION_DENIED")}
 return k
}
func publicBytes(_ key:SecKey)->Data {
 guard let pub=SecKeyCopyPublicKey(key) else {stop("PUBLIC_UNAVAILABLE")}
 var err:Unmanaged<CFError>?
 guard let raw=SecKeyCopyExternalRepresentation(pub,&err) as Data?,
       raw.count==65 && raw[0]==4 else {stop("PUBLIC_KEY_INVALID")}
 return raw
}
func read0600(_ path:String)->Data {
 var s=stat()
 guard lstat(path,&s)==0 && (s.st_mode&mode_t(S_IFMT))==mode_t(S_IFREG)
       && s.st_uid==geteuid() && (s.st_mode&0o777)==0o600
       && s.st_nlink==1 && s.st_size>0 && s.st_size<8192 else {stop("INPUT_UNSAFE")}
 let fd=Darwin.open(path,O_RDONLY|O_NOFOLLOW)
 guard fd>=0 else {stop("INPUT_OPEN_FAILED")}
 defer {Darwin.close(fd)}
 var buf=[UInt8](repeating:0,count:Int(s.st_size))
 let count=buf.withUnsafeMutableBytes {Darwin.read(fd,$0.baseAddress,$0.count)}
 guard count==s.st_size else {stop("INPUT_READ_FAILED")}
 return Data(buf)
}
func write0600(_ path:String,_ data:Data) {
 guard data.count>0 && data.count<8192 else {stop("OUTPUT_SIZE")}
 let fd=Darwin.open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,mode_t(0o600))
 guard fd>=0 else {stop("OUTPUT_EXISTS")}
 defer {Darwin.close(fd)}
 let count=data.withUnsafeBytes {Darwin.write(fd,$0.baseAddress,$0.count)}
 guard count==data.count && fsync(fd)==0 else {stop("OUTPUT_WRITE_FAIL")}
}
guard CommandLine.arguments.count>=2 else {stop("USAGE")}
let mode=CommandLine.arguments[1]
if mode=="enroll" {
 guard CommandLine.arguments.count==3 else {stop("ENROLL_ARGS")}
 let pub=publicBytes(getKey(create:true))
 let path=CommandLine.arguments[2]
 if access(path,F_OK)==0 {
   guard read0600(path)==pub else {stop("PUBLIC_MISMATCH")}
 } else {write0600(path,pub)}
 print("PASS_WE1_CHAT_SOCIAL_OWNER_KEYCHAIN_PUBLIC_ENROLLED",hex(Data(SHA256.hash(data:pub))))
 print("DB_INSTALL_AUTHORIZED",false)
} else if mode=="public" {
 guard CommandLine.arguments.count==2 else {stop("PUBLIC_ARGS")}
 let pub=publicBytes(getKey(create:false))
 print("CHAT_SOCIAL_OWNER_KEY_SHA256",hex(Data(SHA256.hash(data:pub))))
} else if mode=="sign" {
 guard CommandLine.arguments.count==4 else {stop("SIGN_ARGS")}
 let msg=read0600(CommandLine.arguments[2])
 guard msg.starts(with:domain) && msg.count<8192 else {stop("WRONG_SIGNING_PURPOSE")}
 // Executor, NOT signer, enforces exact JSON fields, dates and SQL hashes.
 let key=getKey(create:false)
 var err:Unmanaged<CFError>?
 guard let sig=SecKeyCreateSignature(key,.ecdsaSignatureMessageX962SHA256,msg as CFData,&err) as Data?,
       sig.count>=64 && sig.count<=80 else {stop("SIGN_DENIED")}
 write0600(CommandLine.arguments[3],sig)
 print("PASS_WE1_CHAT_SOCIAL_SQL_PURPOSE_SIGNATURE",hex(Data(SHA256.hash(data:sig))))
 print("FINANCIAL_AUTHORIZED",false)
} else {stop("UNSUPPORTED_MODE")}
