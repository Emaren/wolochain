package satchelservice

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"os"
	"os/user"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/emaren/wolochain/internal/satchel"
	"golang.org/x/sys/unix"
)

const (
	C01CustodyRole  = "wolo-satchel"
	C01ReviewerRole = "wolo-reviewer"

	c01StartupSchema = "wolo.c01.zero-funded-startup-permit.v1"
	c01StartupDomain = "AOE2WAR-WOLO-C01-ZERO-FUNDED-STARTUP-V1\x00"
	c01MaxStartupAge = 5 * time.Minute
)

var ErrC01NonfundedAdmission = errors.New("c01_nonfunded_admission_refused")

// C01StartupConfig binds the actual service configuration already parsed by
// the caller. KeyFingerprintSHA256 is SHA-256 of the raw enrolled public key.
// The caller must still compare that pin with the real key before using it.
type C01StartupConfig struct {
	Role, ConfigFile, ConfigSHA256, KeyFingerprintSHA256 string
	C08ReceiptFile, C08OwnerPublicFile, PermitFile       string
}

type c01FilePin struct {
	path, sha256 string
	limit        int64
}

// C01NonfundedAdmission is a short-lived, revocable, zero-fund startup grant.
// It cannot authorize financial execution, transaction signing or approval.
type C01NonfundedAdmission struct {
	validFrom, expiresAt, monotonicDeadline time.Time
	role, requestSHA256, nonceSHA256        string
	files                                   []c01FilePin
	revoked                                 atomic.Bool
}

// Role identifies which isolated service this grant covers.
func (a *C01NonfundedAdmission) Role() string { return a.role }

// RequestSHA256 hashes the signed domain and the canonical request array.
func (a *C01NonfundedAdmission) RequestSHA256() string { return a.requestSHA256 }

// NonceSHA256 hashes the lowercase ASCII nonce encoding.
func (a *C01NonfundedAdmission) NonceSHA256() string { return a.nonceSHA256 }

func (a *C01NonfundedAdmission) ExpiresAt() time.Time { return a.expiresAt }

// Current checks expiry and the original exact protected files, including the
// committed nonce. An observed revocation stays latched for this process.
func (a *C01NonfundedAdmission) Current(ctx context.Context) bool {
	if !a.currentAt(ctx, time.Now()) {
		return false
	}
	if !a.unexpired(time.Now()) {
		a.revoked.Store(true)
		return false
	}
	return ctx.Err() == nil && !a.revoked.Load()
}

func (a *C01NonfundedAdmission) unexpired(now time.Time) bool {
	return !now.Before(a.validFrom) && now.Before(a.expiresAt) && now.Before(a.monotonicDeadline)
}

func (a *C01NonfundedAdmission) currentAt(ctx context.Context, now time.Time) bool {
	if a == nil || ctx == nil || ctx.Err() != nil || len(a.files) != 5 || a.revoked.Load() {
		return false
	}
	if !a.unexpired(now) {
		a.revoked.Store(true)
		return false
	}
	for _, pin := range a.files {
		b, err := ReadPrivateFile(pin.path, pin.limit)
		if err != nil || c08HexSHA(b) != pin.sha256 {
			a.revoked.Store(true)
			return false
		}
	}
	return ctx.Err() == nil && !a.revoked.Load()
}

type c01RuntimeBinding struct {
	uid, gid            uint32
	revision, binarySHA string
}

func c01CurrentRuntime(ctx context.Context, role string) (c01RuntimeBinding, error) {
	if !c01AdmissionProduction || ctx == nil || ctx.Err() != nil {
		return c01RuntimeBinding{}, ErrC01NonfundedAdmission
	}
	uid, gid, ok := c01RoleIdentity(role)
	if !ok {
		return c01RuntimeBinding{}, ErrC01NonfundedAdmission
	}
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return c01RuntimeBinding{}, ErrC01NonfundedAdmission
	}
	revision := c01SourceRevision(info)
	if revision == "" {
		return c01RuntimeBinding{}, ErrC01NonfundedAdmission
	}
	binarySHA, err := runtimeCustodyBinaryDigest()
	if err != nil {
		return c01RuntimeBinding{}, ErrC01NonfundedAdmission
	}
	return c01RuntimeBinding{uid, gid, revision, binarySHA}, nil
}

// PrepareC01NonfundedStartup returns the canonical unsigned request array, with
// no prefix or trailing newline. It does not open the permit or any private
// signing key, and makes no changes to the nonce journal.
func PrepareC01NonfundedStartup(ctx context.Context, c C01StartupConfig) ([]byte, error) {
	rt, err := c01CurrentRuntime(ctx, c.Role)
	if err != nil {
		return nil, err
	}
	trust := productionC08V3Trust
	if _, _, err := readC01StartupInputs(c, rt.revision, rt.binarySHA, trust); err != nil {
		return nil, err
	}
	dir, err := openC01NonceJournal(c.Role, rt.uid, rt.gid)
	if err != nil {
		return nil, ErrC01NonfundedAdmission
	}
	if dir.Close() != nil || ctx.Err() != nil {
		return nil, ErrC01NonfundedAdmission
	}
	nonce := make([]byte, 32)
	if _, err := rand.Read(nonce); err != nil {
		return nil, ErrC01NonfundedAdmission
	}
	now := time.Now().UTC().Truncate(time.Second)
	request := append(c01StartupBinding(c, rt.revision, rt.binarySHA, trust),
		hex.EncodeToString(nonce), now.Format(time.RFC3339), now.Add(c01MaxStartupAge).Format(time.RFC3339), 0)
	return c08Canonical(request)
}

// AdmitC01NonfundedStartup verifies the real C08 owner and exact running build,
// then creates and fsyncs one replay tombstone in the fixed role-owned journal.
// No keyring, private signing key, financial journal, listener or network is
// opened here. A refused or canceled result can still have consumed its nonce
// if refusal occurred after the exclusive tombstone creation.
func AdmitC01NonfundedStartup(ctx context.Context, c C01StartupConfig) (*C01NonfundedAdmission, error) {
	rt, err := c01CurrentRuntime(ctx, c.Role)
	if err != nil {
		return nil, err
	}
	grant, nonce, record, err := verifyC01Startup(c, rt.revision, rt.binarySHA, productionC08V3Trust, time.Now())
	if err != nil || ctx.Err() != nil {
		return nil, ErrC01NonfundedAdmission
	}
	dir, err := openC01NonceJournal(c.Role, rt.uid, rt.gid)
	if err != nil {
		return nil, ErrC01NonfundedAdmission
	}
	defer dir.Close()
	// The complete signed permit was checked before the first state change.
	if !grant.unexpired(time.Now()) || ctx.Err() != nil ||
		consumeC01Nonce(dir, nonce, record, rt.uid, rt.gid) != nil {
		return nil, ErrC01NonfundedAdmission
	}
	grant.files = append(grant.files, c01FilePin{
		path: filepath.Join(dir.Name(), nonce), sha256: c08HexSHA(record), limit: 128,
	})
	if !grant.Current(ctx) {
		return nil, ErrC01NonfundedAdmission
	}
	return grant, nil
}

func c01StartupBinding(c C01StartupConfig, revision, binarySHA string, trust C08V3Trust) []any {
	return []any{c.Role, satchel.ChainID, revision, binarySHA, c.ConfigSHA256,
		c.KeyFingerprintSHA256, trust.PolicySHA, trust.ReceiptSHA}
}

func readC01StartupInputs(c C01StartupConfig, revision, binarySHA string, trust C08V3Trust) ([]c01FilePin, []byte, error) {
	if (c.Role != C01CustodyRole && c.Role != C01ReviewerRole) || !c01Hex(revision, 20) ||
		!c01Hex(binarySHA, 32) || !c01Hex(c.ConfigSHA256, 32) ||
		!c01Hex(c.KeyFingerprintSHA256, 32) || !c01Hex(trust.PolicySHA, 32) ||
		!c01Hex(trust.ReceiptSHA, 32) || !c01Hex(trust.OwnerKeySHA, 32) {
		return nil, nil, ErrC01NonfundedAdmission
	}
	files := []c01FilePin{
		{c.ConfigFile, c.ConfigSHA256, 64 << 10},
		{c.C08ReceiptFile, trust.ReceiptSHA, 16 << 10},
		{c.C08OwnerPublicFile, trust.OwnerKeySHA, 256},
		{c.PermitFile, "", 4096},
	}
	seen := map[string]bool{}
	for _, pin := range files {
		if !filepath.IsAbs(pin.path) || filepath.Clean(pin.path) != pin.path || seen[pin.path] {
			return nil, nil, ErrC01NonfundedAdmission
		}
		seen[pin.path] = true
	}
	var inputs [3][]byte
	for i, pin := range files[:len(inputs)] {
		b, err := ReadPrivateFile(pin.path, pin.limit)
		if err != nil || c08HexSHA(b) != pin.sha256 {
			return nil, nil, ErrC01NonfundedAdmission
		}
		inputs[i] = b
	}
	if verifyC08KeychainV3Receipt(inputs[2], inputs[1], trust) != nil {
		return nil, nil, ErrC01NonfundedAdmission
	}
	return files, inputs[2], nil
}

func verifyC01Startup(c C01StartupConfig, revision, binarySHA string, trust C08V3Trust, now time.Time) (*C01NonfundedAdmission, string, []byte, error) {
	fail := func() (*C01NonfundedAdmission, string, []byte, error) {
		return nil, "", nil, ErrC01NonfundedAdmission
	}
	files, ownerPublic, err := readC01StartupInputs(c, revision, binarySHA, trust)
	if err != nil || now.IsZero() {
		return fail()
	}
	rawPermit, err := ReadPrivateFile(c.PermitFile, files[3].limit)
	if err != nil {
		return fail()
	}
	packet, err := c08Decode(rawPermit)
	if err != nil || !c08ExactKeys(packet, []string{"schema", "request", "signature_der_b64"}) ||
		packet["schema"] != c01StartupSchema {
		return fail()
	}
	request, ok := packet["request"].([]any)
	if !ok || len(request) != 12 || !c08Int(request[11], "0") {
		return fail()
	}
	for i, value := range c01StartupBinding(c, revision, binarySHA, trust) {
		if request[i] != value {
			return fail()
		}
	}
	nonce, ok := request[8].(string)
	validFrom, startOK := c08Time(request[9])
	expiresAt, expiryOK := c08Time(request[10])
	if !ok || !c01Hex(nonce, 32) || !startOK || !expiryOK ||
		!expiresAt.After(validFrom) || expiresAt.Sub(validFrom) > c01MaxStartupAge ||
		now.Before(validFrom) || !now.Before(expiresAt) {
		return fail()
	}
	encoded, ok := packet["signature_der_b64"].(string)
	if !ok || len(encoded) < 80 || len(encoded) > 108 {
		return fail()
	}
	der, err := base64.StdEncoding.Strict().DecodeString(encoded)
	if err != nil || len(der) < 64 || len(der) > 80 || base64.StdEncoding.EncodeToString(der) != encoded {
		return fail()
	}
	message, err := c08Canonical(request)
	if err != nil {
		return fail()
	}
	digest := sha256.Sum256(append([]byte(c01StartupDomain), message...))
	curve := elliptic.P256()
	x, y := elliptic.Unmarshal(curve, ownerPublic)
	if x == nil || y == nil || !ecdsa.VerifyASN1(&ecdsa.PublicKey{Curve: curve, X: x, Y: y}, digest[:], der) {
		return fail()
	}
	files[3].sha256 = c08HexSHA(rawPermit)
	grant := &C01NonfundedAdmission{
		validFrom: validFrom, expiresAt: expiresAt,
		monotonicDeadline: now.Add(expiresAt.Sub(now)), files: files,
		role: c.Role, requestSHA256: hex.EncodeToString(digest[:]), nonceSHA256: c08HexSHA([]byte(nonce)),
	}
	record := []byte("c01-zero-fund-startup-v1 " + grant.requestSHA256 + "\n")
	return grant, nonce, record, nil
}

func c01Hex(s string, size int) bool {
	if len(s) != size*2 || strings.Trim(s, "0") == "" {
		return false
	}
	raw, err := hex.DecodeString(s)
	return err == nil && hex.EncodeToString(raw) == s
}

func c01SourceRevision(info *debug.BuildInfo) string {
	settings := map[string]string{}
	for _, setting := range info.Settings {
		switch setting.Key {
		case "vcs", "vcs.modified", "vcs.revision":
			if _, ok := settings[setting.Key]; ok {
				return ""
			}
			settings[setting.Key] = setting.Value
		}
	}
	revision := settings["vcs.revision"]
	if settings["vcs"] != "git" || settings["vcs.modified"] != "false" || !c01Hex(revision, 20) {
		return ""
	}
	return revision
}

func c01RoleIdentity(role string) (uint32, uint32, bool) {
	if runtime.GOOS != "linux" || os.Getuid() == 0 ||
		(role != C01CustodyRole && role != C01ReviewerRole) {
		return 0, 0, false
	}
	account, err := user.Lookup(role)
	if err != nil {
		return 0, 0, false
	}
	uid, uidErr := strconv.ParseUint(account.Uid, 10, 32)
	gid, gidErr := strconv.ParseUint(account.Gid, 10, 32)
	ok := uidErr == nil && gidErr == nil && uid != 0 && gid != 0 &&
		uint64(os.Getuid()) == uid && uint64(os.Geteuid()) == uid &&
		uint64(os.Getgid()) == gid && uint64(os.Getegid()) == gid
	return uint32(uid), uint32(gid), ok
}

func openC01NonceJournal(role string, uid, gid uint32) (*os.File, error) {
	var roleDir string
	switch role {
	case C01CustodyRole:
		roleDir = "custody"
	case C01ReviewerRole:
		roleDir = "reviewer"
	default:
		return nil, ErrC01NonfundedAdmission
	}
	parts := []string{"", "var", "lib", "wolo-financial-role-state", "v1", roleDir, "c01-admission"}
	flags := unix.O_RDONLY | unix.O_DIRECTORY | unix.O_NOFOLLOW | unix.O_CLOEXEC
	fd, err := unix.Open("/", flags, 0)
	if err != nil {
		return nil, err
	}
	for i, component := range parts {
		if i != 0 {
			next, err := unix.Openat(fd, component, flags, 0)
			_ = unix.Close(fd)
			if err != nil {
				return nil, err
			}
			fd = next
		}
		var st unix.Stat_t
		err := unix.Fstat(fd, &st)
		private := i >= len(parts)-2
		if err != nil || st.Mode&unix.S_IFMT != unix.S_IFDIR ||
			(!private && (st.Uid != 0 || st.Mode&0022 != 0)) ||
			(private && (st.Uid != uid || st.Gid != gid || st.Mode&07777 != 0700)) {
			_ = unix.Close(fd)
			return nil, ErrC01NonfundedAdmission
		}
	}
	return os.NewFile(uintptr(fd), strings.Join(parts, "/")), nil
}

// Creation is exclusive and a tombstone is never deleted, including after an
// incomplete write or late fsync error. An uncertain claim therefore denies
// replay instead of falling back to an earlier state.
func consumeC01Nonce(dir *os.File, nonce string, record []byte, uid, gid uint32) error {
	if !c01Hex(nonce, 32) || len(record) == 0 || len(record) > 128 {
		return ErrC01NonfundedAdmission
	}
	fd, err := unix.Openat(int(dir.Fd()), nonce, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0600)
	if err != nil {
		return err
	}
	f := os.NewFile(uintptr(fd), "c01-nonce-tombstone")
	defer f.Close()
	var st unix.Stat_t
	if err := f.Chmod(0600); err != nil || unix.Fstat(fd, &st) != nil ||
		st.Mode&(unix.S_IFMT|07777) != unix.S_IFREG|0600 || st.Uid != uid || st.Gid != gid || st.Nlink != 1 {
		return ErrC01NonfundedAdmission
	}
	if n, err := f.Write(record); err != nil || n != len(record) {
		return ErrC01NonfundedAdmission
	}
	if err := f.Sync(); err != nil {
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return dir.Sync()
}
