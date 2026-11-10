package satchelservice

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"path/filepath"

	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	"github.com/cosmos/cosmos-sdk/types/tx/signing"
	"github.com/emaren/wolochain/internal/satchel"
)

const c01FileSchema = "wolo.c01.zero-funded-startup-config.v1"
const c01KeyProofDomain = "AOE2WAR-WOLO-C01-KEY-POSSESSION-V1\x00"

type c01CustodyKey struct {
	Vault        string `json:"vault"`
	PublicKeyHex string `json:"public_key_hex"`
	KeyName      string `json:"key_name"`
}

type c01File struct {
	Schema               string         `json:"schema"`
	Role                 string         `json:"role"`
	KeyFingerprintSHA256 string         `json:"key_fingerprint_sha256"`
	C08ReceiptFile       string         `json:"c08_receipt_file"`
	C08OwnerPublicFile   string         `json:"c08_owner_public_file"`
	PermitFile           string         `json:"permit_file"`
	Custody              *c01CustodyKey `json:"custody,omitempty"`
}

// C01NonfundedKeyReceipt records possession without emitting a signing oracle,
// listener, or any financial permission.
type C01NonfundedKeyReceipt struct {
	Schema               string `json:"schema"`
	Role                 string `json:"role"`
	RequestSHA256        string `json:"request_sha256"`
	NonceSHA256          string `json:"nonce_sha256"`
	KeyFingerprintSHA256 string `json:"key_fingerprint_sha256"`
	ProofSHA256          string `json:"proof_sha256"`
	FundingAuthorized    bool   `json:"funding_authorized"`
}

func c01Digest(raw []byte) string {
	value := sha256.Sum256(raw)
	return hex.EncodeToString(value[:])
}

func readC01KeyConfig(path string) (c01File, C01StartupConfig, error) {
	var file c01File
	raw, err := ReadPrivateFile(path, 8192)
	if err != nil || json.Unmarshal(raw, &file) != nil {
		return file, C01StartupConfig{}, ErrBackend
	}
	canonical, err := json.Marshal(file)
	if err != nil || !bytes.Equal(canonical, raw) || file.Schema != c01FileSchema {
		return file, C01StartupConfig{}, ErrBackend
	}
	switch file.Role {
	case C01CustodyRole:
		if file.Custody == nil || file.Custody.KeyName == "" {
			return file, C01StartupConfig{}, ErrBackend
		}
		key, err := hex.DecodeString(file.Custody.PublicKeyHex)
		if err != nil || len(key) != 33 || hex.EncodeToString(key) != file.Custody.PublicKeyHex ||
			c01Digest(key) != file.KeyFingerprintSHA256 || satchel.IsKnownRoleAddress(file.Custody.Vault) {
			return file, C01StartupConfig{}, ErrBackend
		}
		address, err := backendPubAddress(&sdksecp.PubKey{Key: key})
		if err != nil || address != file.Custody.Vault {
			return file, C01StartupConfig{}, ErrBackend
		}
	case C01ReviewerRole:
		if file.Custody != nil {
			return file, C01StartupConfig{}, ErrBackend
		}
	default:
		return file, C01StartupConfig{}, ErrBackend
	}
	return file, C01StartupConfig{
		Role: file.Role, ConfigFile: path, ConfigSHA256: c01Digest(raw),
		KeyFingerprintSHA256: file.KeyFingerprintSHA256, C08ReceiptFile: file.C08ReceiptFile,
		C08OwnerPublicFile: file.C08OwnerPublicFile, PermitFile: file.PermitFile,
	}, nil
}

// PrepareC01KeyPossessionRequest prepares the exact owner-local challenge
// without accessing custody or reviewer keys.
func PrepareC01KeyPossessionRequest(ctx context.Context, path string) ([]byte, error) {
	_, config, err := readC01KeyConfig(path)
	if err != nil {
		return nil, err
	}
	return PrepareC01NonfundedStartup(ctx, config)
}

// CheckC01AdmittedKey consumes the signed startup nonce before key access. The
// fixed proof prefix is outside both Cosmos transaction and reviewer approval
// domains. The caller cannot supply a message or receive signature bytes.
func CheckC01AdmittedKey(ctx context.Context, path string) (C01NonfundedKeyReceipt, error) {
	file, config, err := readC01KeyConfig(path)
	if err != nil {
		return C01NonfundedKeyReceipt{}, err
	}
	receipt, _, err := checkC01AdmittedKey(ctx, file, config)
	return receipt, err
}

func checkC01AdmittedKey(ctx context.Context, file c01File, config C01StartupConfig) (C01NonfundedKeyReceipt, *C01NonfundedAdmission, error) {
	grant, err := AdmitC01NonfundedStartup(ctx, config)
	if err != nil || !grant.Current(ctx) {
		return C01NonfundedKeyReceipt{}, nil, ErrBackend
	}
	message := []byte(c01KeyProofDomain + grant.RequestSHA256())
	var signature []byte
	if file.Role == C01CustodyRole {
		signature, err = c01ProveCustodyKey(ctx, file.Custody, message, grant.Current)
	} else {
		signature, err = c01ProveReviewerKey(ctx, file.KeyFingerprintSHA256, message, grant.Current)
	}
	if err != nil || !grant.Current(ctx) {
		return C01NonfundedKeyReceipt{}, nil, ErrBackend
	}
	return C01NonfundedKeyReceipt{
		Schema: "wolo.c01.zero-funded-key-possession-receipt.v1", Role: grant.Role(),
		RequestSHA256: grant.RequestSHA256(), NonceSHA256: grant.NonceSHA256(),
		KeyFingerprintSHA256: file.KeyFingerprintSHA256, ProofSHA256: c01Digest(signature),
	}, grant, nil
}

func c01ProveCustodyKey(ctx context.Context, cfg *c01CustodyKey, message []byte, current func(context.Context) bool) ([]byte, error) {
	const state = "/var/lib/wolo-financial-role-state/v1/custody"
	keys := BackendConfig{KeyringDir: filepath.Join(state, "keyring"), KeyName: cfg.KeyName,
		PassphraseFile: filepath.Join(state, "unlock.secret")}
	lease, err := lockSatchelKeyring(keys.KeyringDir)
	if err != nil {
		return nil, err
	}
	defer lease.Close()
	key, _ := hex.DecodeString(cfg.PublicKeyHex) // checked before admission
	expected := &sdksecp.PubKey{Key: key}
	signer, err := openSatchelKeyring(keys, expected)
	if err != nil || !current(ctx) {
		return nil, ErrBackend
	}
	signature, public, err := signer.Sign(cfg.KeyName, message, signing.SignMode_SIGN_MODE_DIRECT)
	if err != nil || public == nil || !bytes.Equal(public.Bytes(), expected.Key) ||
		!expected.VerifySignature(message, signature) {
		return nil, ErrBackend
	}
	return signature, nil
}

func c01ProveReviewerKey(ctx context.Context, fingerprint string, message []byte, current func(context.Context) bool) ([]byte, error) {
	const path = "/var/lib/wolo-financial-role-state/v1/reviewer/wager-reviewer-ed25519.key"
	raw, err := ReadPrivateFile(path, ed25519.PrivateKeySize)
	defer clear(raw)
	if err != nil || len(raw) != ed25519.PrivateKeySize {
		return nil, ErrBackend
	}
	key := ed25519.NewKeyFromSeed(raw[:ed25519.SeedSize])
	defer clear(key)
	public := ed25519.PublicKey(key[ed25519.SeedSize:])
	if !bytes.Equal(raw, key) || !ValidAuthorityPublicKey(public) ||
		c01Digest(public) != fingerprint || !current(ctx) {
		return nil, ErrBackend
	}
	signature := ed25519.Sign(key, message)
	if !ed25519.Verify(public, message, signature) {
		return nil, ErrBackend
	}
	return signature, nil
}
