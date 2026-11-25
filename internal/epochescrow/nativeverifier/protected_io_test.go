package nativeverifier

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"
	"testing"

	"golang.org/x/sys/unix"
)

func TestProtectedPublicFileDescriptor(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(root, "public")
	if err = os.Mkdir(dir, 0755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "pins.json")
	if err = os.WriteFile(path, []byte(`{"public":"nonsecret"}`), 0444); err != nil {
		t.Fatal(err)
	}
	f, err := openProtectedFile(path, root, uint32(os.Getuid()), 0444, MaxPinsBytes)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	before, err := f.Stat()
	if err != nil {
		t.Fatal(err)
	}
	data, err := io.ReadAll(f)
	after, statErr := f.Stat()
	if err != nil || statErr != nil || string(data) != `{"public":"nonsecret"}` || !sameProtectedFile(before, after, uint32(os.Getuid()), 0444, MaxPinsBytes) {
		t.Fatal("protected public descriptor changed")
	}
	if err = os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	changed, err := f.Stat()
	if err != nil || sameProtectedFile(before, changed, uint32(os.Getuid()), 0444, MaxPinsBytes) {
		t.Fatal("metadata mutation accepted")
	}
}

func TestProtectedPublicFileRejectsUnsafeInstallations(t *testing.T) {
	for _, kind := range []string{"symlink", "ancestor-symlink", "hardlink", "fifo", "directory", "empty", "oversized", "writable-file", "private-file", "writable-directory", "wrong-owner", "outside-root", "relative", "unclean"} {
		t.Run(kind, func(t *testing.T) {
			root, err := filepath.EvalSymlinks(t.TempDir())
			if err != nil {
				t.Fatal(err)
			}
			dir := filepath.Join(root, "public")
			if err = os.Mkdir(dir, 0755); err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(dir, "pins.json")
			uid := uint32(os.Getuid())
			if err = os.WriteFile(path, []byte(`{}`), 0444); err != nil {
				t.Fatal(err)
			}
			switch kind {
			case "symlink":
				link := filepath.Join(dir, "link.json")
				err = os.Symlink(path, link)
				path = link
			case "ancestor-symlink":
				link := filepath.Join(root, "link")
				err = os.Symlink(dir, link)
				path = filepath.Join(link, "pins.json")
			case "hardlink":
				err = os.Link(path, filepath.Join(dir, "other.json"))
			case "fifo":
				path = filepath.Join(dir, "fifo")
				err = unix.Mkfifo(path, 0444)
			case "directory":
				path = dir
			case "empty":
				err = os.Truncate(path, 0)
			case "oversized":
				err = os.Truncate(path, MaxPinsBytes+1)
			case "writable-file":
				err = os.Chmod(path, 0664)
			case "private-file":
				err = os.Chmod(path, 0400)
			case "writable-directory":
				err = os.Chmod(dir, 0775)
			case "wrong-owner":
				uid++
			case "outside-root":
				root = dir
				path = filepath.Join(filepath.Dir(dir), "outside.json")
			case "relative":
				path = "pins.json"
			case "unclean":
				path = dir + "/../public/pins.json"
			}
			// Truncate of a readonly file may fail for the ordinary test user;
			// prepare size before reopening it with the mandated public mode.
			if err != nil && (kind == "empty" || kind == "oversized") {
				if err = os.Chmod(path, 0644); err != nil {
					t.Fatal(err)
				}
				size := int64(0)
				if kind == "oversized" {
					size = MaxPinsBytes + 1
				}
				if err = os.Truncate(path, size); err != nil {
					t.Fatal(err)
				}
				err = os.Chmod(path, 0444)
			}
			if err != nil {
				t.Fatal(err)
			}
			f, err := openProtectedFile(path, root, uid, 0444, MaxPinsBytes)
			if f != nil {
				f.Close()
			}
			if err == nil {
				t.Fatal("unsafe public pins accepted")
			}
		})
	}
}

func TestBuildIdentityRequiresActualCleanVCSMetadata(t *testing.T) {
	compiler := "go1.27.1"
	valid := func() *debug.BuildInfo {
		return &debug.BuildInfo{GoVersion: compiler, Settings: []debug.BuildSetting{{Key: "vcs", Value: "git"}, {Key: "vcs.revision", Value: strings.Repeat("a", 40)}, {Key: "vcs.modified", Value: "false"}}}
	}
	id, err := identityFromBuildInfo(valid(), compiler)
	if err != nil || id.SourceCommit != strings.Repeat("a", 40) || id.Compiler != compiler || id.Modified {
		t.Fatal(id, err)
	}
	for _, kind := range []string{"nil", "compiler", "missing-vcs", "missing-revision", "missing-modified", "dirty", "unknown-modified", "zero", "uppercase", "short", "nonhex", "duplicate"} {
		t.Run(kind, func(t *testing.T) {
			info := valid()
			switch kind {
			case "nil":
				info = nil
			case "compiler":
				info.GoVersion = "go1.26"
			case "missing-vcs":
				info.Settings = info.Settings[1:]
			case "missing-revision":
				info.Settings = append(info.Settings[:1], info.Settings[2:]...)
			case "missing-modified":
				info.Settings = info.Settings[:2]
			case "dirty":
				info.Settings[2].Value = "true"
			case "unknown-modified":
				info.Settings[2].Value = "no"
			case "zero":
				info.Settings[1].Value = strings.Repeat("0", 40)
			case "uppercase":
				info.Settings[1].Value = strings.Repeat("A", 40)
			case "short":
				info.Settings[1].Value = "abcd"
			case "nonhex":
				info.Settings[1].Value = strings.Repeat("z", 40)
			case "duplicate":
				info.Settings = append(info.Settings, info.Settings[1])
			}
			if _, err := identityFromBuildInfo(info, compiler); err == nil {
				t.Fatal("untrusted build identity accepted")
			}
		})
	}
}

func TestProtectedIOCancelledContextHasFixedErrors(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := LoadProtectedPinsContext(ctx); err != errProtectedPins {
		t.Fatal(err)
	}
	if _, err := RuntimeIdentityContext(ctx); err != errRuntimeIdentity {
		t.Fatal(err)
	}
	if _, err := LoadProtectedPinsContext(nil); err != errProtectedPins {
		t.Fatal(err)
	}
	if _, err := RuntimeIdentityContext(nil); err != errRuntimeIdentity {
		t.Fatal(err)
	}
}
