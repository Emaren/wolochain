package satchelservice

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"

	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
)

type Config struct {
	Version                   int                 `json:"version"`
	Vault                     string              `json:"vault"`
	PublicKeyHex              string              `json:"public_key_hex"`
	BettingEscrow             string              `json:"betting_escrow"`
	ProtectedAddresses        []string            `json:"protected_addresses"`
	MaxAmountUWolo            uint64              `json:"max_amount_uwolo"`
	RPC                       string              `json:"rpc"`
	REST                      string              `json:"rest"`
	WitnessRPC                string              `json:"witness_rpc"`
	TrustAnchor               satchel.TrustAnchor `json:"trust_anchor"`
	KeyringDir                string              `json:"keyring_dir"`
	KeyName                   string              `json:"key_name"`
	PassphraseFile            string              `json:"passphrase_file"`
	TokenFile                 string              `json:"token_file"`
	StatePath                 string              `json:"state_path"`
	FeesUWolo                 string              `json:"fees_uwolo"`
	GasLimit                  uint64              `json:"gas_limit"`
	TimeoutBlocks             uint64              `json:"timeout_blocks"`
	WithdrawalApprovalKeyHex  string              `json:"withdrawal_approval_key_hex"`
	ActivationAuthorityKeyHex string              `json:"activation_authority_key_hex"`
	PermitFile                string              `json:"permit_file"`
}

// ExecutionPermit is an independent operator's scoped authorization to execute
// this exact software/configuration. Proof digests identify reviewed artifacts;
// signatures cannot themselves establish that a vault is solvent or isolated.
// The software ships no approval key, permit, checkpoint, or vault address.
type ExecutionPermit struct {
	Version                  int    `json:"version"`
	Scope                    string `json:"scope"`
	ConfigSHA256             string `json:"config_sha256"`
	BinarySHA256             string `json:"binary_sha256"`
	Vault                    string `json:"vault"`
	IsolationEvidenceSHA256  string `json:"isolation_evidence_sha256"`
	AccountingEvidenceSHA256 string `json:"accounting_evidence_sha256"`
	RecoveryEvidenceSHA256   string `json:"recovery_evidence_sha256"`
	Reviewer                 string `json:"reviewer"`
	Reference                string `json:"reference"`
	IssuedAt                 int64  `json:"issued_at"`
	ExpiresAt                int64  `json:"expires_at"`
	Signature                string `json:"signature"`
}

func PermitMessage(p ExecutionPermit) []byte {
	b, _ := json.Marshal([]any{"aoe2war/satchel/execution-permit/v1", p.Version, p.Scope, p.ConfigSHA256, p.BinarySHA256, p.Vault, p.IsolationEvidenceSHA256, p.AccountingEvidenceSHA256, p.RecoveryEvidenceSHA256, p.Reviewer, p.Reference, p.IssuedAt, p.ExpiresAt})
	return b
}

// ReadPrivateFile opens the same descriptor whose ownership/type are checked.
// No final-component or ancestor symlinks, FIFOs, shared files, remote URLs,
// environment substitutions, or executable configuration are accepted.
func ReadPrivateFile(path string, limit int64) ([]byte, error) {
	if !filepath.IsAbs(path) || limit <= 0 || limit > 1<<20 {
		return nil, errors.New("private_file_refused")
	}
	real, err := filepath.EvalSymlinks(path)
	if err != nil || real != path {
		return nil, errors.New("private_file_refused")
	}
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, errors.New("private_file_refused")
	}
	f := os.NewFile(uintptr(fd), "satchel-private-file")
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, errors.New("private_file_refused")
	}
	sys, ok := st.Sys().(*syscall.Stat_t)
	if !ok || sys.Uid != uint32(os.Geteuid()) || sys.Nlink != 1 || !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() <= 0 || st.Size() > limit {
		return nil, errors.New("private_file_refused")
	}
	data, err := io.ReadAll(io.LimitReader(f, limit+1))
	after, err2 := f.Stat()
	if err != nil || err2 != nil || int64(len(data)) > limit || after.Size() != st.Size() || !after.ModTime().Equal(st.ModTime()) {
		return nil, errors.New("private_file_refused")
	}
	return data, nil
}
func decodePrivate(data []byte, dst any) error {
	if !utf8.Valid(data) || !chainjson.Valid(data) {
		return errors.New("configuration_invalid")
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(dst); err != nil {
		return errors.New("configuration_invalid")
	}
	return nil
}
func LoadConfig(path string) (Config, string, error) {
	var c Config
	b, err := ReadPrivateFile(path, 65536)
	if err != nil {
		return c, "", err
	}
	if err = decodePrivate(b, &c); err != nil {
		return c, "", err
	}
	if c.Version != 1 || !validAddress(c.Vault) || satchel.IsKnownRoleAddress(c.Vault) || !validAddress(c.BettingEscrow) || c.Vault == c.BettingEscrow || c.MaxAmountUWolo == 0 || c.MaxAmountUWolo > 50000000000 || len(c.ProtectedAddresses) == 0 || len(c.ProtectedAddresses) > 128 {
		return c, "", errors.New("configuration_invalid")
	}
	public, e := hex.DecodeString(c.PublicKeyHex)
	if e != nil || len(public) != 33 {
		return c, "", errors.New("configuration_invalid")
	}
	a, e := hex.DecodeString(c.ActivationAuthorityKeyHex)
	if e != nil || len(a) != ed25519.PublicKeySize {
		return c, "", errors.New("configuration_invalid")
	}
	w, e := hex.DecodeString(c.WithdrawalApprovalKeyHex)
	if e != nil || len(w) != ed25519.PublicKeySize || bytes.Equal(a, w) {
		return c, "", errors.New("independent_approval_keys_required")
	}
	for _, p := range []string{c.KeyringDir, c.PassphraseFile, c.TokenFile, c.StatePath, c.PermitFile} {
		if !filepath.IsAbs(p) || filepath.Clean(p) != p {
			return c, "", errors.New("configuration_invalid")
		}
	}
	for _, address := range c.ProtectedAddresses {
		if !validAddress(address) || address == c.Vault {
			return c, "", errors.New("signer_role_collision")
		}
	}
	r, e := satchel.NewTrustedReader(satchel.SourceConfig{RPC: c.RPC, REST: c.REST, WitnessRPC: c.WitnessRPC}, c.TrustAnchor)
	if e != nil {
		return c, "", errors.New("authenticated_chain_configuration_required")
	}
	r.Close()
	sum := sha256.Sum256(b)
	return c, hex.EncodeToString(sum[:]), nil
}
func VerifyPermit(c Config, configDigest, binaryDigest string) bool {
	return verifyPermitAt(c, configDigest, binaryDigest, time.Now())
}
func verifyPermitAt(c Config, configDigest, binaryDigest string, now time.Time) bool {
	data, err := ReadPrivateFile(c.PermitFile, 16384)
	if err != nil {
		return false
	}
	var p ExecutionPermit
	if decodePrivate(data, &p) != nil {
		return false
	}
	if p.Version != 1 || p.Scope != "satchel-execution-v1" || p.ConfigSHA256 != configDigest || p.BinarySHA256 != binaryDigest || p.Vault != c.Vault ||
		!digestRE.MatchString(configDigest) || !digestRE.MatchString(binaryDigest) || !nonzeroDigest(p.IsolationEvidenceSHA256) || !nonzeroDigest(p.AccountingEvidenceSHA256) || !nonzeroDigest(p.RecoveryEvidenceSHA256) ||
		strings.TrimSpace(p.Reviewer) == "" || len(p.Reviewer) > 128 || strings.TrimSpace(p.Reference) == "" || len(p.Reference) > 512 || p.IssuedAt > now.Unix() || p.ExpiresAt <= now.Unix() || p.ExpiresAt <= p.IssuedAt || uint64(p.ExpiresAt)-uint64(p.IssuedAt) > 86400 {
		return false
	}
	key, err := hex.DecodeString(c.ActivationAuthorityKeyHex)
	if err != nil || len(key) != ed25519.PublicKeySize {
		return false
	}
	sig, err := base64.StdEncoding.Strict().DecodeString(p.Signature)
	return err == nil && len(sig) == ed25519.SignatureSize && base64.StdEncoding.EncodeToString(sig) == p.Signature && ed25519.Verify(key, PermitMessage(p), sig)
}
func nonzeroDigest(s string) bool { return digestRE.MatchString(s) && strings.Trim(s, "0") != "" }
