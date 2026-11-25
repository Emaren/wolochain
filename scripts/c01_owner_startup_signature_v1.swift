// Owner-local signing for the zero-funds C01 startup scope only.
import Foundation
import Security
import CryptoKit
import Darwin

let schema = "wolo.c01.zero-funded-startup-permit.v1"
let domain = Data("AOE2WAR-WOLO-C01-ZERO-FUNDED-STARTUP-V1\0".utf8)
let ownerKeyTag = Data("aoe2war-c08-owner-policy-only-keychain-p256-v3-20261108".utf8)
let ownerKeySHA = "f9f76deb8ba61b8f4b4f8e5b434acc11fa95630ccb19306a71e8bff0dc6fb826"
let policySHA = "50910864e6d24236ac3ea98cda1456bedee8d9bf2f9365a8441c6d1e29b41806"
let receiptSHA = "edcdf664259b0eeec0ae2ed71919bbe5745183864abc2c3b221aa50e83570d19"

func refused(_ reason: String) -> Never {
    FileHandle.standardError.write(Data("C01_OWNER_STARTUP_REFUSED \(reason)\n".utf8))
    exit(3)
}

func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func isLowerHex(_ value: String, size: Int) -> Bool {
    value.utf8.count == size &&
        value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) } &&
        value.utf8.contains { $0 != 48 }
}

func readOwnerRequest(_ path: String) -> Data {
    let fd = Darwin.open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
    guard fd >= 0 else { refused("PRIVATE_REQUEST_OPEN") }
    defer { Darwin.close(fd) }
    var info = stat()
    guard fstat(fd, &info) == 0, info.st_uid == geteuid(), info.st_nlink == 1,
          info.st_mode & mode_t(S_IFMT | 0o7777) == mode_t(S_IFREG | 0o600),
          (1...4096).contains(info.st_size)
    else { refused("PRIVATE_REQUEST_METADATA") }
    let input = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
    guard let raw = try? input.read(upToCount: 4097), raw.count == info.st_size,
          (try? input.read(upToCount: 1)) == nil
    else { refused("PRIVATE_REQUEST_READ") }
    var final = stat()
    guard fstat(fd, &final) == 0, info.st_dev == final.st_dev, info.st_ino == final.st_ino,
          info.st_uid == final.st_uid, info.st_mode == final.st_mode, info.st_nlink == final.st_nlink,
          info.st_size == final.st_size,
          info.st_mtimespec.tv_sec == final.st_mtimespec.tv_sec,
          info.st_mtimespec.tv_nsec == final.st_mtimespec.tv_nsec,
          info.st_ctimespec.tv_sec == final.st_ctimespec.tv_sec,
          info.st_ctimespec.tv_nsec == final.st_ctimespec.tv_nsec
    else { refused("PRIVATE_REQUEST_CHANGED") }
    return raw
}

func validateRequest(_ raw: Data, now: Date) -> [Any] {
    guard let fields = (try? JSONSerialization.jsonObject(with: raw)) as? [Any],
          fields.count == 12, let strings = Array(fields.prefix(11)) as? [String],
          ["wolo-satchel", "wolo-reviewer"].contains(strings[0]), strings[1] == "wolo-1",
          isLowerHex(strings[2], size: 40),
          strings[3...8].allSatisfy({ isLowerHex($0, size: 64) }),
          strings[6] == policySHA, strings[7] == receiptSHA
    else { refused("REQUEST_SCOPE_OR_FIELDS") }

    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]
    iso.timeZone = TimeZone(secondsFromGMT: 0)
    guard let start = iso.date(from: strings[9]), let end = iso.date(from: strings[10]),
          iso.string(from: start) == strings[9], iso.string(from: end) == strings[10],
          start <= now, now < end, end.timeIntervalSince(start) <= 300
    else { refused("REQUEST_EXPIRED_OR_WINDOW_INVALID") }

    let canonical: [Any] = strings.map { $0 as Any } + [0]
    guard let encoded = try? JSONSerialization.data(withJSONObject: canonical), encoded == raw
    else { refused("REQUEST_NOT_CANONICAL_ZERO_FUNDS") }
    return canonical
}

func enrolledOwnerKey() -> SecKey {
    let query: [String: Any] = [
        kSecClass as String: kSecClassKey,
        kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
        kSecAttrKeyClass as String: kSecAttrKeyClassPrivate,
        kSecAttrApplicationTag as String: ownerKeyTag,
        kSecReturnRef as String: true,
        kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let ref = result, CFGetTypeID(ref) == SecKeyGetTypeID()
    else { refused("ENROLLED_OWNER_KEY_UNAVAILABLE") }
    let key = ref as! SecKey
    var error: Unmanaged<CFError>?
    guard let publicKey = SecKeyCopyPublicKey(key),
          let bytes = SecKeyCopyExternalRepresentation(publicKey, &error) as Data?,
          bytes.count == 65, bytes.first == 4, digest(bytes) == ownerKeySHA
    else { refused("ENROLLED_OWNER_KEY_MISMATCH") }
    return key
}

func writeExclusive(_ path: String, _ data: Data) {
    let fd = Darwin.open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
    guard fd >= 0 else { refused("PERMIT_OUTPUT_EXISTS_OR_UNSAFE") }
    defer { Darwin.close(fd) }
    let count = data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
    guard count == data.count, fsync(fd) == 0 else { refused("PERMIT_OUTPUT_FAILED") }
}

let args = CommandLine.arguments
guard geteuid() != 0, args.count == 3 || args.count == 4,
      (args[1] == "inspect" && args.count == 3) || (args[1] == "sign" && args.count == 4)
else { refused("USAGE_INSPECT_REQUEST_OR_SIGN_REQUEST_OUTPUT") }
let raw = readOwnerRequest(args[2])
let fields = validateRequest(raw, now: Date())
let payload = domain + raw
let names = ["role", "chain", "source_revision", "binary_sha256", "config_sha256",
             "key_fingerprint_sha256", "c08_policy_sha256", "c08_receipt_sha256",
             "nonce", "not_before", "expires_at", "funding_allowance_uwolo"]
for (name, value) in zip(names, fields) {
    print("\(name)=\(value)")
}
print("payload_sha256=\(digest(payload))")

if args[1] == "sign" {
    guard isatty(STDIN_FILENO) == 1, isatty(STDOUT_FILENO) == 1,
          let role = fields[0] as? String, let nonce = fields[8] as? String
    else { refused("OWNER_TERMINAL_REQUIRED") }
    print("Type ADMIT \(role) \(nonce) to sign this zero-funds scope.")
    guard readLine() == "ADMIT \(role) \(nonce)" else { refused("OWNER_DID_NOT_CONFIRM") }
    _ = validateRequest(raw, now: Date())
    let key = enrolledOwnerKey()
    var error: Unmanaged<CFError>?
    guard let signature = SecKeyCreateSignature(key, .ecdsaSignatureMessageX962SHA256,
                                                payload as CFData, &error) as Data?,
          signature.count >= 64, signature.count <= 80,
          let packet = try? JSONSerialization.data(withJSONObject: [
              "schema": schema, "request": fields, "signature_der_b64": signature.base64EncodedString()
          ], options: [.sortedKeys])
    else { refused("STARTUP_SCOPE_SIGNATURE_FAILED") }
    writeExclusive(args[3], packet)
    print("PASS_C01_OWNER_SIGNED_ZERO_FUNDS_STARTUP_SCOPE")
}
