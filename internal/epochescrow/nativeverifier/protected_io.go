package nativeverifier

// The HD subprocess can read public enrollment pins, but cannot choose their
// location or replace their root-owned directory/file descriptors.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"strings"
	"syscall"
	"time"

	"golang.org/x/sys/unix"
)

const FixedPinsPath = "/etc/wolochain/epoch-v3-verifier/pins.json"
const maxExecutableBytes int64 = 256 << 20

var errProtectedPins = errors.New("PRODUCTION_TRUST_ENROLLMENT_REQUIRED")
var errRuntimeIdentity = errors.New("NATIVE_VERIFIER_IDENTITY_MISMATCH")

func LoadProtectedPins() (Pins, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	return LoadProtectedPinsContext(ctx)
}

func LoadProtectedPinsContext(ctx context.Context) (Pins, error) {
	if ctx == nil || ctx.Err() != nil {
		return Pins{}, errProtectedPins
	}
	f, err := openProtectedFile(FixedPinsPath, "/", 0, 0444, MaxPinsBytes)
	if err != nil {
		return Pins{}, errProtectedPins
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil {
		return Pins{}, errProtectedPins
	}
	data, err := io.ReadAll(io.LimitReader(f, MaxPinsBytes+1))
	after, afterErr := f.Stat()
	if err != nil || afterErr != nil || ctx.Err() != nil || len(data) == 0 || int64(len(data)) > MaxPinsBytes || !sameProtectedFile(before, after, 0, 0444, MaxPinsBytes) {
		return Pins{}, errProtectedPins
	}
	pins, err := DecodePins(data)
	if err != nil {
		return Pins{}, errProtectedPins
	}
	return pins, nil
}

func RuntimeIdentity() (Identity, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	return RuntimeIdentityContext(ctx)
}

func RuntimeIdentityContext(ctx context.Context) (Identity, error) {
	if ctx == nil || ctx.Err() != nil {
		return Identity{}, errRuntimeIdentity
	}
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return Identity{}, errRuntimeIdentity
	}
	identity, err := identityFromBuildInfo(info, runtime.Version())
	if err != nil {
		return Identity{}, errRuntimeIdentity
	}
	path, err := os.Executable()
	if err != nil {
		return Identity{}, errRuntimeIdentity
	}
	f, err := openProtectedFile(path, "/", 0, 0, maxExecutableBytes)
	if err != nil {
		return Identity{}, errRuntimeIdentity
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil {
		return Identity{}, errRuntimeIdentity
	}
	hash := sha256.New()
	buffer := make([]byte, 64<<10)
	var size int64
	for {
		if ctx.Err() != nil {
			return Identity{}, errRuntimeIdentity
		}
		n, readErr := f.Read(buffer)
		if n > 0 {
			size += int64(n)
			if size > maxExecutableBytes {
				return Identity{}, errRuntimeIdentity
			}
			_, _ = hash.Write(buffer[:n])
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return Identity{}, errRuntimeIdentity
		}
	}
	after, afterErr := f.Stat()
	if afterErr != nil || size != before.Size() || ctx.Err() != nil || !sameProtectedFile(before, after, 0, 0, maxExecutableBytes) {
		return Identity{}, errRuntimeIdentity
	}
	identity.BinarySHA256 = hex.EncodeToString(hash.Sum(nil))
	return identity, nil
}

// No linker variables, environment labels or request fields are provenance.
func identityFromBuildInfo(info *debug.BuildInfo, compiler string) (Identity, error) {
	if info == nil || info.GoVersion != compiler || compiler == "" {
		return Identity{}, errRuntimeIdentity
	}
	identity := Identity{Compiler: compiler, Modified: true}
	foundRevision, foundModified, foundVCS := false, false, false
	for _, setting := range info.Settings {
		switch setting.Key {
		case "vcs":
			if foundVCS || setting.Value != "git" {
				return Identity{}, errRuntimeIdentity
			}
			foundVCS = true
		case "vcs.revision":
			if foundRevision {
				return Identity{}, errRuntimeIdentity
			}
			identity.SourceCommit, foundRevision = setting.Value, true
		case "vcs.modified":
			if foundModified || (setting.Value != "true" && setting.Value != "false") {
				return Identity{}, errRuntimeIdentity
			}
			identity.Modified, foundModified = setting.Value != "false", true
		}
	}
	decoded, err := hex.DecodeString(identity.SourceCommit)
	if !foundVCS || !foundRevision || !foundModified || identity.Modified || err != nil || len(decoded) != 20 || identity.SourceCommit != strings.ToLower(identity.SourceCommit) || strings.Trim(identity.SourceCommit, "0") == "" {
		return Identity{}, errRuntimeIdentity
	}
	return identity, nil
}

// root and uid are private test seams. Public entrypoints always start at the
// filesystem root with uid0 and their fixed path or actual running executable.
// openat+NOFOLLOW pins every ancestor; writable or non-owned parents refuse.
func openProtectedFile(path, root string, uid uint32, mode os.FileMode, limit int64) (*os.File, error) {
	if !filepath.IsAbs(path) || !filepath.IsAbs(root) || filepath.Clean(path) != path || filepath.Clean(root) != root || limit <= 0 {
		return nil, errProtectedPins
	}
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return nil, errProtectedPins
	}
	components := strings.Split(relative, string(filepath.Separator))
	parent, err := unix.Open(root, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, errProtectedPins
	}
	defer func() { _ = unix.Close(parent) }()
	checkDirectory := func(fd int) bool {
		var st unix.Stat_t
		return unix.Fstat(fd, &st) == nil && st.Uid == uid && st.Mode&unix.S_IFMT == unix.S_IFDIR && st.Mode&0022 == 0
	}
	if !checkDirectory(parent) {
		return nil, errProtectedPins
	}
	for _, component := range components[:len(components)-1] {
		if component == "" || component == "." || component == ".." {
			return nil, errProtectedPins
		}
		next, openErr := unix.Openat(parent, component, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
		if openErr != nil {
			return nil, errProtectedPins
		}
		_ = unix.Close(parent)
		parent = next
		if !checkDirectory(parent) {
			return nil, errProtectedPins
		}
	}
	name := components[len(components)-1]
	if name == "" || name == "." || name == ".." {
		return nil, errProtectedPins
	}
	fd, err := unix.Openat(parent, name, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, errProtectedPins
	}
	f := os.NewFile(uintptr(fd), "epoch-v3-protected-public-file")
	info, err := f.Stat()
	if err != nil || !validProtectedFile(info, uid, mode, limit) {
		_ = f.Close()
		return nil, errProtectedPins
	}
	return f, nil
}

func validProtectedFile(info os.FileInfo, uid uint32, mode os.FileMode, limit int64) bool {
	if info == nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > limit || info.Mode().Perm()&0022 != 0 || info.Mode()&(os.ModeSetuid|os.ModeSetgid) != 0 || (mode != 0 && info.Mode().Perm() != mode) {
		return false
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && stat.Uid == uid && stat.Nlink == 1
}

func sameProtectedFile(before, after os.FileInfo, uid uint32, mode os.FileMode, limit int64) bool {
	return validProtectedFile(before, uid, mode, limit) && validProtectedFile(after, uid, mode, limit) && os.SameFile(before, after) && before.Size() == after.Size() && before.ModTime().Equal(after.ModTime()) && before.Mode() == after.Mode()
}
