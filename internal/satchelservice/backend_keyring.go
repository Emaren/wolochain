package satchelservice

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	cryptocodec "github.com/cosmos/cosmos-sdk/crypto/codec"
	"github.com/cosmos/cosmos-sdk/crypto/keyring"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"golang.org/x/crypto/bcrypt"
)

// secureBackendFile refuses symlinks, nonregular files, shared permissions and
// a different owner. Error text deliberately contains no path or file content.
func secureBackendFile(path string, limit int64) ([]byte, error) {
	data, err := ReadPrivateFile(path, limit)
	if err != nil {
		return nil, ErrBackend
	}
	return data, nil
}
func secureBackendDir(path string) error {
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
		return ErrBackend
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != uint32(os.Geteuid()) {
		return ErrBackend
	}
	return nil
}

// The journal lock alone cannot prevent two processes using different journal
// paths with the same signing key. Lease the existing SDK keyring directory's
// inode for this backend's lifetime; no file/key/password is created or changed.
// This is cooperative exclusion, not evidence that another OS principal lacks
// a copy of the key. Operator key isolation remains an independent requirement.
func lockSatchelKeyring(directory string) (*os.File, error) {
	if !filepath.IsAbs(directory) || secureBackendDir(directory) != nil {
		return nil, ErrBackend
	}
	path := filepath.Join(directory, "keyring-file")
	if real, err := filepath.EvalSymlinks(path); err != nil || real != path || secureBackendDir(path) != nil {
		return nil, ErrBackend
	}
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, ErrBackend
	}
	lease := os.NewFile(uintptr(fd), "satchel-keyring-lease")
	info, err := lease.Stat()
	observed, observeErr := os.Lstat(path)
	if err != nil || observeErr != nil || !info.IsDir() || !os.SameFile(info, observed) || syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB) != nil {
		lease.Close()
		return nil, ErrBackend
	}
	return lease, nil
}

// An operator's directory replacement must not turn a lease on an old inode
// into apparent authority over a new SDK keyring path. Called while the native
// backend mutex excludes Close, immediately before the SDK signing invocation.
func (b *KeyringBackend) keyringLeaseCurrent() bool {
	if b.keyringLease == nil {
		return true
	} // Injected test signer, not native SDK.
	path := filepath.Join(b.cfg.KeyringDir, "keyring-file")
	if real, err := filepath.EvalSymlinks(path); err != nil || real != path || secureBackendDir(path) != nil {
		return false
	}
	leased, err := b.keyringLease.Stat()
	current, currentErr := os.Lstat(path)
	return err == nil && currentErr == nil && leased.IsDir() && os.SameFile(leased, current)
}

func openSatchelKeyring(cfg BackendConfig, expected *secp256k1.PubKey) (backendSigner, error) {
	if !filepath.IsAbs(cfg.KeyringDir) || !filepath.IsAbs(cfg.PassphraseFile) || cfg.KeyName == "" || len(cfg.KeyName) > 128 || strings.ContainsAny(cfg.KeyName, "/\\\x00\r\n") {
		return nil, ErrBackend
	}
	if real, err := filepath.EvalSymlinks(cfg.KeyringDir); err != nil || real != cfg.KeyringDir {
		return nil, ErrBackend
	}
	if real, err := filepath.EvalSymlinks(cfg.PassphraseFile); err != nil || real != cfg.PassphraseFile {
		return nil, ErrBackend
	}
	if secureBackendDir(cfg.KeyringDir) != nil || secureBackendDir(filepath.Join(cfg.KeyringDir, "keyring-file")) != nil {
		return nil, ErrBackend
	}
	entries, err := os.ReadDir(filepath.Join(cfg.KeyringDir, "keyring-file"))
	if err != nil || len(entries) < 3 || len(entries) > 8 {
		return nil, ErrBackend
	}
	for _, entry := range entries {
		if _, err := secureBackendFile(filepath.Join(cfg.KeyringDir, "keyring-file", entry.Name()), 1<<20); err != nil {
			return nil, ErrBackend
		}
	}
	// Requiring the existing keyhash prevents the SDK's first-use password
	// initialization path. No key or password-hash creation is performed here.
	keyhash, err := secureBackendFile(filepath.Join(cfg.KeyringDir, "keyring-file", "keyhash"), 1024)
	if err != nil {
		return nil, ErrBackend
	}
	cost, err := bcrypt.Cost(keyhash)
	if err != nil || cost > 14 {
		return nil, ErrBackend
	}
	secret, err := secureBackendFile(cfg.PassphraseFile, 4096)
	if err != nil {
		return nil, ErrBackend
	}
	defer func() {
		for i := range secret {
			secret[i] = 0
		}
	}()
	password := bytes.TrimSuffix(secret, []byte("\n"))
	if len(password) < 8 || bytes.ContainsAny(password, "\r\n\x00") || bcrypt.CompareHashAndPassword(keyhash, password) != nil {
		return nil, ErrBackend
	}
	registry := codectypes.NewInterfaceRegistry()
	cryptocodec.RegisterInterfaces(registry)
	keys, err := keyring.New("cosmos", keyring.BackendFile, cfg.KeyringDir, bytes.NewReader(append(append([]byte(nil), password...), '\n')), codec.NewProtoCodec(registry))
	if err != nil {
		return nil, ErrBackend
	}
	records, err := keys.List()
	if err != nil || len(records) != 1 || records[0].Name != cfg.KeyName || records[0].GetLocal() == nil {
		return nil, ErrBackend
	}
	public, err := records[0].GetPubKey()
	if err != nil || public.Type() != expected.Type() || !bytes.Equal(public.Bytes(), expected.Key) {
		return nil, ErrBackend
	}
	return keys, nil
}
