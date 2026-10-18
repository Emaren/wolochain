package satchelservice

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	base "cosmossdk.io/api/cosmos/base/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	cmttypes "github.com/cometbft/cometbft/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/crypto"
	cryptocodec "github.com/cosmos/cosmos-sdk/crypto/codec"
	"github.com/cosmos/cosmos-sdk/crypto/keyring"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	"google.golang.org/protobuf/proto"
)

// Fixed test-only key material; no production keyring, wallet or network exists.
type testBackendSigner struct {
	key   *sdksecp.PrivKey
	calls atomic.Int32
	wrong bool
}

func (s *testBackendSigner) Sign(_ string, b []byte, _ signing.SignMode) ([]byte, cryptotypes.PubKey, error) {
	s.calls.Add(1)
	if s.wrong {
		return nil, nil, errors.New("sensitive fake keyring failure")
	}
	sig, err := s.key.Sign(b)
	return sig, s.key.PubKey(), err
}

type backendFixture struct {
	b           *KeyringBackend
	request     TransferRequest
	signer      *testBackendSigner
	broadcasts  atomic.Int32
	mode        string
	statusMode  string
	accountMode string
}

func newBackendFixture(t *testing.T) *backendFixture {
	t.Helper()
	f := &backendFixture{signer: &testBackendSigner{key: &sdksecp.PrivKey{Key: bytes.Repeat([]byte{7}, 32)}}}
	vault, _ := backendPubAddress(f.signer.key.PubKey())
	recipient, _ := backendPubAddress((&sdksecp.PrivKey{Key: bytes.Repeat([]byte{9}, 32)}).PubKey())
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/status":
			if f.statusMode != "" {
				_, _ = w.Write([]byte(f.statusMode))
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"node_info": map[string]any{"network": "wolo-1"}, "sync_info": map[string]any{"latest_block_height": "100", "latest_block_hash": strings.Repeat("AB", 32), "latest_block_time": time.Now().UTC().Format(time.RFC3339Nano), "catching_up": false}}})
		case "/cosmos/auth/v1beta1/accounts/" + vault:
			if f.accountMode != "" {
				_, _ = w.Write([]byte(f.accountMode))
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"account": map[string]any{"@type": "/cosmos.auth.v1beta1.BaseAccount", "address": vault, "account_number": "2", "sequence": "3", "pub_key": map[string]string{"@type": "/cosmos.crypto.secp256k1.PubKey", "key": base64.StdEncoding.EncodeToString(f.signer.key.PubKey().Bytes())}}})
		case "/":
			f.broadcasts.Add(1)
			if r.Method != http.MethodPost {
				t.Error("broadcast must be JSON-RPC POST")
			}
			var request struct {
				Method string            `json:"method"`
				Params map[string]string `json:"params"`
			}
			if json.NewDecoder(r.Body).Decode(&request) != nil || request.Method != "broadcast_tx_sync" {
				t.Error("wrong broadcast method")
			}
			data, err := base64.StdEncoding.DecodeString(request.Params["tx"])
			if err != nil {
				t.Error(err)
			}
			hash := strings.ToUpper(hex.EncodeToString(cmttypes.Tx(data).Hash()))
			switch f.mode {
			case "missing":
				_, _ = w.Write([]byte(`{}`))
			case "forged":
				_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"hash": strings.Repeat("CD", 32), "code": 0}})
			case "duplicate":
				_, _ = w.Write([]byte(`{"result":{"hash":"` + hash + `","code":0,"code":5}}`))
			case "failed":
				_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"hash": hash, "code": 5}})
			case "large":
				_, _ = w.Write([]byte(strings.Repeat(" ", (1<<20)+1)))
			case "null":
				_, _ = w.Write([]byte(`{"result":{"hash":"` + hash + `","code":null}}`))
			case "unavailable":
				w.WriteHeader(http.StatusServiceUnavailable)
			default:
				_ = json.NewEncoder(w).Encode(map[string]any{"result": map[string]any{"hash": hash}}) // legitimate omitted zero code
			}
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(server.Close)
	b, err := newBackend(BackendConfig{RPC: server.URL, REST: server.URL, Vault: vault, PublicKeyHex: hex.EncodeToString(f.signer.key.PubKey().Bytes()), KeyName: "isolated-satchel", FeesUWolo: "2500", MaxAmountUWolo: "1000000000", GasLimit: 120000, TimeoutBlocks: 20, ApprovedDestinations: []string{recipient}})
	if err != nil {
		t.Fatal(err)
	}
	b.signer = f.signer
	f.b = b
	t.Cleanup(b.Close)
	f.request = TransferRequest{OperationID: "satchel:ticket:7", Kind: "wager", ChainID: "wolo-1", Denom: "uwolo", Sender: vault, Recipient: recipient, AmountUWolo: "7000000", Memo: "AoE2HDBets bet ticket v1 · ticket 7"}
	return f
}

func TestBackendNativeSigningSeparatesBroadcastAndBindsSignature(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	signed, err := f.b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	if signed.AccountNumber != 2 || signed.Sequence != 3 || len(signed.Hash) != 64 || f.signer.calls.Load() != 1 || f.broadcasts.Load() != 0 {
		t.Fatalf("unexpected signing boundary: %+v", signed)
	}
	if err = f.b.ValidateSigned(f.request, signed); err != nil {
		t.Fatal(err)
	}
	result, err := f.b.Broadcast(t.Context(), signed)
	if err != nil || result.Status != "ACCEPTED" || f.broadcasts.Load() != 1 {
		t.Fatalf("legitimate zero-code acknowledgement: %+v, %v", result, err)
	}
	if result.Status == "CONFIRMED" {
		t.Fatal("CheckTx acknowledgement cannot confirm execution")
	}
}

func TestBackendRefusesPolicyBeforeSigning(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	cases := map[string]func(*TransferRequest){
		"fractional wager": func(r *TransferRequest) { r.AmountUWolo = "1000001" },
		"chain":            func(r *TransferRequest) { r.ChainID = "wolo-testnet" }, "denom": func(r *TransferRequest) { r.Denom = "wolo" }, "sender": func(r *TransferRequest) { r.Sender = r.Recipient }, "destination": func(r *TransferRequest) { r.Recipient = "wolo1invalid" }, "zero": func(r *TransferRequest) { r.AmountUWolo = "0" }, "padded zero": func(r *TransferRequest) { r.AmountUWolo = "00" }, "overflow": func(r *TransferRequest) { r.AmountUWolo = "18446744073709551615" }, "above cap": func(r *TransferRequest) { r.AmountUWolo = "1000000001" }, "memo": func(r *TransferRequest) { r.Memo = "" }, "memo control": func(r *TransferRequest) { r.Memo = "invalid\nsecret" }, "operation": func(r *TransferRequest) { r.OperationID = "arbitrary" }, "kind": func(r *TransferRequest) { r.Kind = "transfer" }, "unapproved withdrawal": func(r *TransferRequest) { r.Kind = "withdrawal"; r.Approval = &WithdrawalApproval{} },
	}
	for name, change := range cases {
		t.Run(name, func(t *testing.T) {
			r := f.request
			change(&r)
			if _, err := f.b.Sign(t.Context(), r); !errors.Is(err, ErrPreSignRefused) {
				t.Fatalf("policy accepted: %v", err)
			}
		})
	}
	if f.signer.calls.Load() != 0 || f.broadcasts.Load() != 0 {
		t.Fatal("invalid policy reached keyring or transmission")
	}
}

func TestBackendRevalidatesEveryDurableEconomicField(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	signed, err := f.b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	for name, change := range map[string]func(*TransferRequest){"amount": func(r *TransferRequest) { r.AmountUWolo = "1000000" }, "memo": func(r *TransferRequest) { r.Memo = "AoE2HDBets bet ticket v1 · ticket 8" }, "sender": func(r *TransferRequest) { r.Sender = r.Recipient }, "recipient": func(r *TransferRequest) { r.Recipient = r.Sender }, "chain": func(r *TransferRequest) { r.ChainID = "other" }, "denom": func(r *TransferRequest) { r.Denom = "stake" }} {
		t.Run(name, func(t *testing.T) {
			r := f.request
			change(&r)
			if f.b.ValidateSigned(r, signed) == nil {
				t.Fatal("changed economic request accepted")
			}
		})
	}
	for name, change := range map[string]func(*SignedTransaction){"hash": func(s *SignedTransaction) { s.Hash = strings.Repeat("A", 64) }, "account number": func(s *SignedTransaction) { s.AccountNumber++ }, "sequence": func(s *SignedTransaction) { s.Sequence++ }, "signature": func(s *SignedTransaction) {
		s.Bytes = append([]byte(nil), s.Bytes...)
		s.Bytes[len(s.Bytes)-1] ^= 1
		s.Hash = hex.EncodeToString(cmttypes.Tx(s.Bytes).Hash())
	}} {
		t.Run(name, func(t *testing.T) {
			s := signed
			change(&s)
			if f.b.ValidateSigned(f.request, s) == nil {
				t.Fatal("changed signed transaction accepted")
			}
		})
	}
}

func TestBackendRejectsCryptographicallyValidUnsupportedTransactions(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	original, err := f.b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	cases := map[string]func(*txapi.TxBody, *txapi.AuthInfo){"extra message": func(b *txapi.TxBody, a *txapi.AuthInfo) { b.Messages = append(b.Messages, b.Messages[0]) }, "fee grant": func(b *txapi.TxBody, a *txapi.AuthInfo) { a.Fee.Granter = f.request.Recipient }, "gas": func(b *txapi.TxBody, a *txapi.AuthInfo) { a.Fee.GasLimit++ }, "fee amount": func(b *txapi.TxBody, a *txapi.AuthInfo) { a.Fee.Amount[0].Amount = "999999" }, "fee coin": func(b *txapi.TxBody, a *txapi.AuthInfo) {
		a.Fee.Amount = append(a.Fee.Amount, &base.Coin{Denom: "stake", Amount: "1"})
	}, "unbounded expiry": func(b *txapi.TxBody, a *txapi.AuthInfo) { b.TimeoutHeight = 0 }, "unordered": func(b *txapi.TxBody, a *txapi.AuthInfo) { b.Unordered = true }, "extra transfer coin": func(b *txapi.TxBody, a *txapi.AuthInfo) {
		var send bank.MsgSend
		_ = proto.Unmarshal(b.Messages[0].Value, &send)
		send.Amount = append(send.Amount, &base.Coin{Denom: "stake", Amount: "1"})
		b.Messages[0].Value, _ = proto.Marshal(&send)
	}}
	for name, change := range cases {
		t.Run(name, func(t *testing.T) {
			var raw txapi.TxRaw
			var body txapi.TxBody
			var auth txapi.AuthInfo
			_ = proto.Unmarshal(original.Bytes, &raw)
			_ = proto.Unmarshal(raw.BodyBytes, &body)
			_ = proto.Unmarshal(raw.AuthInfoBytes, &auth)
			change(&body, &auth)
			raw.BodyBytes, _ = proto.Marshal(&body)
			raw.AuthInfoBytes, _ = proto.Marshal(&auth)
			doc, _ := proto.Marshal(&txapi.SignDoc{BodyBytes: raw.BodyBytes, AuthInfoBytes: raw.AuthInfoBytes, ChainId: "wolo-1", AccountNumber: original.AccountNumber})
			raw.Signatures[0], _ = f.signer.key.Sign(doc)
			s := original
			s.Bytes, _ = proto.Marshal(&raw)
			s.Hash = hex.EncodeToString(cmttypes.Tx(s.Bytes).Hash())
			if f.b.ValidateSigned(f.request, s) == nil {
				t.Fatal("unsupported signed transaction accepted")
			}
		})
	}
}

func TestBackendBroadcastUncertaintyNeverClaimsConfirmation(t *testing.T) {
	t.Parallel()
	for _, mode := range []string{"missing", "forged", "duplicate", "large", "null", "unavailable", "failed"} {
		t.Run(mode, func(t *testing.T) {
			f := newBackendFixture(t)
			s, err := f.b.Sign(t.Context(), f.request)
			if err != nil {
				t.Fatal(err)
			}
			f.mode = mode
			result, err := f.b.Broadcast(t.Context(), s)
			if mode == "failed" {
				if result.Status != "FAILED" || result.Code != 5 || err != nil {
					t.Fatalf("failed CheckTx lost: %+v %v", result, err)
				}
			} else if result.Status != "UNKNOWN" || err == nil {
				t.Fatalf("uncertainty not held: %+v %v", result, err)
			}
			if f.broadcasts.Load() != 1 {
				t.Fatal("backend automatically retried")
			}
		})
	}
}

func TestBackendRefusesForgedAccountAndHeadBeforeKeyring(t *testing.T) {
	t.Parallel()
	for name, mode := range map[string]string{"missing result": `{}`, "wrong chain": `{"result":{"node_info":{"network":"wolo-testnet"},"sync_info":{"catching_up":false}}}`, "missing syncing status": `{"result":{"node_info":{"network":"wolo-1"},"sync_info":{}}}`, "duplicate result": `{"result":{},"result":{}}`} {
		t.Run(name, func(t *testing.T) {
			f := newBackendFixture(t)
			f.statusMode = mode
			if _, err := f.b.Sign(t.Context(), f.request); !errors.Is(err, ErrPreSignRefused) || f.signer.calls.Load() != 0 {
				t.Fatal("forged head reached signer")
			}
		})
	}
	for name, mode := range map[string]string{"missing account": `{}`, "null": `{"account":null}`, "wrong address": `{"account":{"@type":"/cosmos.auth.v1beta1.BaseAccount","address":"other","account_number":"2","sequence":"3"}}`, "unknown wrapper": `{"account":{"@type":"/cosmos.vesting.v1beta1.ContinuousVestingAccount"}}`} {
		t.Run(name, func(t *testing.T) {
			f := newBackendFixture(t)
			f.accountMode = mode
			if _, err := f.b.Sign(t.Context(), f.request); !errors.Is(err, ErrPreSignRefused) || f.signer.calls.Load() != 0 {
				t.Fatal("forged account reached signer")
			}
		})
	}
}

func TestBackendErrorsDoNotExposeSignerMaterial(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	f.signer.wrong = true
	_, err := f.b.Sign(t.Context(), f.request)
	if err == nil || strings.Contains(err.Error(), "sensitive") {
		t.Fatalf("unsanitized keyring error: %v", err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err = f.b.Sign(ctx, f.request); err == nil {
		t.Fatal("canceled signing accepted")
	}
}

func TestBackendPrivateSecretFilesAndNoProvisioning(t *testing.T) {
	t.Parallel()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(dir, "passphrase")
	if err := os.WriteFile(file, []byte("not-a-real-secret"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := secureBackendFile(file, 100); err != nil {
		t.Fatal(err)
	}
	if _, err := secureBackendFile(file, 2); err == nil {
		t.Fatal("unbounded secret file accepted")
	}
	if err := os.Chmod(file, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := secureBackendFile(file, 100); err == nil {
		t.Fatal("shared secret accepted")
	}
	link := filepath.Join(dir, "link")
	if err := os.Symlink(file, link); err != nil {
		t.Fatal(err)
	}
	if _, err := secureBackendFile(link, 100); err == nil {
		t.Fatal("symlinked secret accepted")
	}
	f := newBackendFixture(t)
	cfg := f.b.cfg
	cfg.KeyringDir = filepath.Join(dir, "missing-keyring")
	cfg.PassphraseFile = file
	if _, err := NewKeyringBackend(cfg); err == nil {
		t.Fatal("unprovisioned keyring accepted")
	}
	if _, err := os.Lstat(cfg.KeyringDir); !os.IsNotExist(err) {
		t.Fatal("constructor created keyring state")
	}
}

func TestBackendWithdrawalFreshAuthorizationAndExpiredRecovery(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	r := f.request
	r.Kind = "withdrawal"
	r.OperationID = "satchel:withdrawal:a0000000-0000-4000-8000-000000000007"
	r.Memo = "aoe2war/satchel/withdraw/v1/a0000000-0000-4000-8000-000000000007"
	r.Approval = &WithdrawalApproval{WithdrawalID: "a0000000-0000-4000-8000-000000000007"}
	r.AmountUWolo = "1234567"
	var expired bool
	f.b.cfg.WithdrawalVerifier = func(TransferRequest) error {
		if expired {
			return ErrBackend
		}
		return nil
	}
	s, err := f.b.Sign(t.Context(), r)
	if err != nil {
		t.Fatal(err)
	}
	expired = true
	if f.b.ValidateSigned(r, s) != nil {
		t.Fatal("expired approval blocked reconciliation of already fenced bytes")
	}
	if _, err = f.b.Sign(t.Context(), r); err == nil {
		t.Fatal("expired approval authorized a new signature")
	}
	if f.signer.calls.Load() != 1 {
		t.Fatal("withdrawal signed more than once")
	}
}

func TestBackendRejectsPublicKeyAndProtectedRoleCollision(t *testing.T) {
	t.Parallel()
	f := newBackendFixture(t)
	for name, change := range map[string]func(*BackendConfig){"wrong public key": func(c *BackendConfig) { c.PublicKeyHex = strings.Repeat("00", 33) }, "dynamic protected role": func(c *BackendConfig) { c.ProtectedAddresses = []string{c.Vault} }, "remote plaintext RPC": func(c *BackendConfig) { c.RPC = "http://example.com" }, "url credential": func(c *BackendConfig) { c.RPC = "https://secret@example.com" }, "fee cap": func(c *BackendConfig) { c.FeesUWolo = "1000001" }, "unbounded timeout": func(c *BackendConfig) { c.TimeoutBlocks = 101 }} {
		t.Run(name, func(t *testing.T) {
			cfg := f.b.cfg
			change(&cfg)
			if b, err := newBackend(cfg); err == nil {
				b.Close()
				t.Fatal("unsafe custody configuration accepted")
			}
		})
	}
}

func TestBackendOpensOnlyExistingSDKEncryptedFileKeyring(t *testing.T) {
	// This fixture provisions one deterministic synthetic SDK key in a temporary
	// directory, then exercises the actual production opening/signing path. It
	// never uses an operator keyring, production address or network endpoint.
	f := newBackendFixture(t)
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	registry := codectypes.NewInterfaceRegistry()
	cryptocodec.RegisterInterfaces(registry)
	const password = "test-fixture-password-only"
	keys, err := keyring.New("cosmos", keyring.BackendFile, dir, strings.NewReader(password+"\n"+password+"\n"), codec.NewProtoCodec(registry))
	if err != nil {
		t.Fatal(err)
	}
	armor := crypto.EncryptArmorPrivKey(f.signer.key, "fixture-import-only", f.signer.key.Type())
	if err = keys.ImportPrivKey(f.b.cfg.KeyName, armor, "fixture-import-only"); err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(filepath.Join(dir, "keyring-file"), 0700); err != nil {
		t.Fatal(err)
	}
	passfile := filepath.Join(dir, "unlock")
	if err = os.WriteFile(passfile, []byte(password+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg := f.b.cfg
	cfg.KeyringDir = dir
	cfg.PassphraseFile = passfile
	b, err := NewKeyringBackend(cfg)
	if err != nil {
		t.Fatal("existing isolated SDK keyring refused:", err)
	}
	defer b.Close()
	s, err := b.Sign(t.Context(), f.request)
	if err != nil || b.ValidateSigned(f.request, s) != nil {
		t.Fatalf("native keyring signature failed: %v", err)
	}
	if f.broadcasts.Load() != 0 {
		t.Fatal("opening/signing keyring transmitted a transaction")
	}
	cfg.KeyName = "different-key"
	if other, err := NewKeyringBackend(cfg); err == nil {
		other.Close()
		t.Fatal("unprovisioned selector accepted")
	}
	cfg.KeyName = f.b.cfg.KeyName
	if err = os.WriteFile(passfile, []byte("incorrect-unlock-secret\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if other, err := NewKeyringBackend(cfg); err == nil {
		other.Close()
		t.Fatal("incorrect unlock accepted")
	}
}
