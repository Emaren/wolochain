package satchelservice

// The backend uses an existing isolated Cosmos file keyring. It never creates,
// imports, exports or migrates a key. Signing and broadcasting are separate so
// the service can durably fence the exact signed bytes before any transmission.

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode/utf8"

	bank "cosmossdk.io/api/cosmos/bank/v1beta1"
	base "cosmossdk.io/api/cosmos/base/v1beta1"
	secp "cosmossdk.io/api/cosmos/crypto/secp256k1"
	signapi "cosmossdk.io/api/cosmos/tx/signing/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	cmtjson "github.com/cometbft/cometbft/libs/json"
	core "github.com/cometbft/cometbft/rpc/core/types"
	cmttypes "github.com/cometbft/cometbft/types"
	"github.com/cosmos/btcutil/bech32"
	sdksecp "github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	cryptotypes "github.com/cosmos/cosmos-sdk/crypto/types"
	signing "github.com/cosmos/cosmos-sdk/types/tx/signing"
	"github.com/emaren/wolochain/internal/chainjson"
	"github.com/emaren/wolochain/internal/satchel"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/anypb"
)

var ErrBackend = errors.New("satchel_backend_refused")

// ErrPreSignRefused proves this invocation never entered the SDK signing call.
// It is safe to release the service's global sequence fence while retaining a
// terminal refusal for this exact operation ID. Other errors grant no such proof.
var ErrPreSignRefused = errors.New("satchel_pre_sign_refused")

// BackendConfig is server-owned configuration. The public key is public
// provisioning evidence, never a private-key input. Native confirmation remains
// NONCREDITING unless a separate authenticated consensus implementation is wired.
type BackendConfig struct {
	RPC, REST, WitnessRPC               string
	Vault, PublicKeyHex                 string
	KeyringDir, KeyName, PassphraseFile string
	FeesUWolo, MaxAmountUWolo           string
	GasLimit, TimeoutBlocks             uint64
	ApprovedDestinations                []string
	ProtectedAddresses                  []string
	WithdrawalVerifier                  func(TransferRequest) error
	WagerVerifier                       func(TransferRequest) error
	ConfirmTransaction                  func(context.Context, TransferRequest, SignedTransaction) (Confirmation, error)
}

type backendSigner interface {
	Sign(string, []byte, signing.SignMode) ([]byte, cryptotypes.PubKey, error)
}

type KeyringBackend struct {
	cfg          BackendConfig
	publicKey    *sdksecp.PubKey
	signer       backendSigner
	rpc, rest    *url.URL
	client       *http.Client
	reader       *satchel.ChainReader
	mu           sync.Mutex
	keyringLease *os.File
	closed       atomic.Bool
}

func NewKeyringBackend(cfg BackendConfig) (*KeyringBackend, error) {
	b, err := newBackend(cfg)
	if err != nil {
		return nil, err
	}
	lease, err := lockSatchelKeyring(cfg.KeyringDir)
	if err != nil {
		b.Close()
		return nil, ErrBackend
	}
	b.keyringLease = lease
	signer, err := openSatchelKeyring(cfg, b.publicKey)
	if err != nil {
		b.Close()
		return nil, ErrBackend
	}
	b.signer = signer
	return b, nil
}

func newBackend(cfg BackendConfig) (*KeyringBackend, error) {
	key, err := hex.DecodeString(cfg.PublicKeyHex)
	if err != nil || len(key) != 33 || !backendAddress(cfg.Vault) || satchel.IsKnownRoleAddress(cfg.Vault) ||
		!backendAmount(cfg.FeesUWolo, "1000000") || !backendAmount(cfg.MaxAmountUWolo, "100000000000000") ||
		cfg.GasLimit == 0 || cfg.GasLimit > 500000 || cfg.TimeoutBlocks < 2 || cfg.TimeoutBlocks > 100 || len(cfg.ApprovedDestinations) == 0 {
		return nil, ErrBackend
	}
	public := &sdksecp.PubKey{Key: key}
	derived, err := backendPubAddress(public)
	if err != nil || derived != cfg.Vault {
		return nil, ErrBackend
	}
	for _, address := range cfg.ProtectedAddresses {
		if !backendAddress(address) || address == cfg.Vault {
			return nil, ErrBackend
		}
	}
	seen := map[string]bool{}
	for _, destination := range cfg.ApprovedDestinations {
		if !backendAddress(destination) || destination == cfg.Vault || seen[destination] {
			return nil, ErrBackend
		}
		seen[destination] = true
	}
	parse := func(raw string) (*url.URL, error) {
		u, err := url.Parse(raw)
		if err != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.RawPath != "" || u.Opaque != "" {
			return nil, ErrBackend
		}
		ip := net.ParseIP(u.Hostname())
		if u.Scheme != "https" && !(u.Scheme == "http" && ip != nil && ip.IsLoopback()) {
			return nil, ErrBackend
		}
		u.Path = strings.TrimRight(u.Path, "/")
		return u, nil
	}
	rpc, err := parse(cfg.RPC)
	if err != nil {
		return nil, err
	}
	rest, err := parse(cfg.REST)
	if err != nil {
		return nil, err
	}
	reader, err := satchel.NewChainReader(satchel.SourceConfig{RPC: cfg.RPC, REST: cfg.REST, WitnessRPC: cfg.WitnessRPC})
	if err != nil {
		return nil, ErrBackend
	}
	transport := &http.Transport{Proxy: nil, DialContext: (&net.Dialer{Timeout: 2 * time.Second}).DialContext, TLSHandshakeTimeout: 2 * time.Second, ResponseHeaderTimeout: 2 * time.Second, DisableCompression: true, MaxConnsPerHost: 2, MaxIdleConnsPerHost: 2, MaxResponseHeaderBytes: 16384}
	client := &http.Client{Transport: transport, Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return ErrBackend }}
	cfg.ApprovedDestinations = append([]string(nil), cfg.ApprovedDestinations...)
	cfg.ProtectedAddresses = append([]string(nil), cfg.ProtectedAddresses...)
	return &KeyringBackend{cfg: cfg, publicKey: public, rpc: rpc, rest: rest, client: client, reader: reader}, nil
}

func (b *KeyringBackend) Close() {
	if b != nil {
		b.mu.Lock()
		defer b.mu.Unlock()
		if b.closed.Swap(true) {
			return
		}
		if b.client != nil {
			b.client.CloseIdleConnections()
		}
		if b.reader != nil {
			b.reader.Close()
		}
		if b.keyringLease != nil {
			_ = b.keyringLease.Close()
			b.keyringLease = nil
		}
	}
}

func backendPubAddress(public cryptotypes.PubKey) (string, error) {
	if public == nil {
		return "", ErrBackend
	}
	words, err := bech32.ConvertBits(public.Address(), 8, 5, true)
	if err != nil {
		return "", ErrBackend
	}
	return bech32.Encode("wolo", words)
}
func backendAddress(address string) bool {
	if address != strings.ToLower(address) {
		return false
	}
	hrp, words, err := bech32.Decode(address, 90)
	if err != nil || hrp != "wolo" {
		return false
	}
	data, err := bech32.ConvertBits(words, 5, 8, false)
	return err == nil && len(data) == 20
}
func backendAmount(value, maximum string) bool {
	if len(value) == 0 || len(value) > 15 || value[0] < '1' || value[0] > '9' {
		return false
	}
	for _, c := range value {
		if c < '0' || c > '9' {
			return false
		}
	}
	n, err := strconv.ParseUint(value, 10, 64)
	m, e := strconv.ParseUint(maximum, 10, 64)
	return err == nil && e == nil && n <= m
}
func (b *KeyringBackend) validateRequest(r TransferRequest, fresh bool) error {
	if r.ChainID != "wolo-1" || r.Denom != "uwolo" || r.Sender != b.cfg.Vault || !backendAddress(r.Recipient) || r.Recipient == r.Sender || !backendAmount(r.AmountUWolo, b.cfg.MaxAmountUWolo) || !ids.MatchString(r.OperationID) || len(r.Memo) == 0 || len(r.Memo) > 256 || !utf8.ValidString(r.Memo) {
		return ErrBackend
	}
	switch r.Kind {
	case "wager":
		whole, err := strconv.ParseUint(r.AmountUWolo, 10, 64)
		if !wagerIDs.MatchString(r.OperationID) || r.Approval != nil || !ticketMemo.MatchString(r.Memo) || err != nil || whole%1000000 != 0 {
			return ErrBackend
		}
		if fresh && (r.Reservation == nil || r.Reservation.FeeUWolo != b.cfg.FeesUWolo || b.cfg.WagerVerifier == nil || b.cfg.WagerVerifier(r) != nil) {
			return ErrBackend
		}
		for _, destination := range b.cfg.ApprovedDestinations {
			if r.Recipient == destination {
				return nil
			}
		}
	case "withdrawal":
		for _, address := range b.cfg.ProtectedAddresses {
			if r.Recipient == address {
				return ErrBackend
			}
		}
		if satchel.IsKnownRoleAddress(r.Recipient) || r.Reservation != nil || r.Approval == nil || r.Memo != "aoe2war/satchel/withdraw/v1/"+r.Approval.WithdrawalID || (fresh && (b.cfg.WithdrawalVerifier == nil || b.cfg.WithdrawalVerifier(r) != nil)) {
			return ErrBackend
		}
		return nil
	}
	return ErrBackend
}

// Sign builds a Cosmos DIRECT transaction from the immutable transfer and a
// bounded canonical account observation. It never broadcasts or persists state.
func (b *KeyringBackend) Sign(ctx context.Context, r TransferRequest) (SignedTransaction, error) {
	if b == nil || b.signer == nil || b.validateRequest(r, true) != nil {
		return SignedTransaction{}, ErrPreSignRefused
	}
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.closed.Load() || ctx.Err() != nil {
		return SignedTransaction{}, ErrPreSignRefused
	}
	height, err := b.head(ctx)
	if err != nil {
		return SignedTransaction{}, ErrPreSignRefused
	}
	number, sequence, err := b.account(ctx)
	if err != nil {
		return SignedTransaction{}, ErrPreSignRefused
	}
	if uint64(height) > uint64(^uint64(0)>>1)-b.cfg.TimeoutBlocks {
		return SignedTransaction{}, ErrPreSignRefused
	}
	message, _ := proto.Marshal(&bank.MsgSend{FromAddress: r.Sender, ToAddress: r.Recipient, Amount: []*base.Coin{{Denom: "uwolo", Amount: r.AmountUWolo}}})
	bodyBytes, _ := proto.Marshal(&txapi.TxBody{Messages: []*anypb.Any{{TypeUrl: "/cosmos.bank.v1beta1.MsgSend", Value: message}}, Memo: r.Memo, TimeoutHeight: uint64(height) + b.cfg.TimeoutBlocks})
	publicBytes, _ := proto.Marshal(&secp.PubKey{Key: b.publicKey.Key})
	authBytes, _ := proto.Marshal(&txapi.AuthInfo{SignerInfos: []*txapi.SignerInfo{{PublicKey: &anypb.Any{TypeUrl: "/cosmos.crypto.secp256k1.PubKey", Value: publicBytes}, ModeInfo: &txapi.ModeInfo{Sum: &txapi.ModeInfo_Single_{Single: &txapi.ModeInfo_Single{Mode: signapi.SignMode_SIGN_MODE_DIRECT}}}, Sequence: sequence}}, Fee: &txapi.Fee{Amount: []*base.Coin{{Denom: "uwolo", Amount: b.cfg.FeesUWolo}}, GasLimit: b.cfg.GasLimit}})
	signBytes, _ := proto.Marshal(&txapi.SignDoc{BodyBytes: bodyBytes, AuthInfoBytes: authBytes, ChainId: "wolo-1", AccountNumber: number})
	// Account/head I/O must not allow owner consent or the independent approval
	// to expire between validation and entering the irreversible signing call.
	if ctx.Err() != nil || b.validateRequest(r, true) != nil || !b.keyringLeaseCurrent() {
		return SignedTransaction{}, ErrPreSignRefused
	}
	signature, public, err := b.signer.Sign(b.cfg.KeyName, signBytes, signing.SignMode_SIGN_MODE_DIRECT)
	if err != nil || ctx.Err() != nil || public == nil || !bytes.Equal(public.Bytes(), b.publicKey.Key) || !b.publicKey.VerifySignature(signBytes, signature) {
		return SignedTransaction{}, ErrBackend
	}
	raw, _ := proto.Marshal(&txapi.TxRaw{BodyBytes: bodyBytes, AuthInfoBytes: authBytes, Signatures: [][]byte{signature}})
	signed := SignedTransaction{Bytes: raw, Hash: strings.ToUpper(hex.EncodeToString(cmttypes.Tx(raw).Hash())), AccountNumber: number, Sequence: sequence}
	if b.ValidateSigned(r, signed) != nil {
		return SignedTransaction{}, ErrBackend
	}
	return signed, nil
}

// ValidateSigned revalidates durable bytes on every restart. A hash alone is
// insufficient: it verifies the exact signer, chain-bound DIRECT signature,
// transfer, memo, fee, gas policy, sequence and supported transaction shape.
func (b *KeyringBackend) ValidateSigned(r TransferRequest, s SignedTransaction) error {
	if b == nil || b.closed.Load() || b.validateRequest(r, false) != nil || len(s.Bytes) == 0 || len(s.Bytes) > 65536 || len(s.Hash) != 64 || !strings.EqualFold(s.Hash, hex.EncodeToString(cmttypes.Tx(s.Bytes).Hash())) {
		return ErrBackend
	}
	var raw txapi.TxRaw
	var body txapi.TxBody
	var auth txapi.AuthInfo
	if proto.Unmarshal(s.Bytes, &raw) != nil || len(raw.ProtoReflect().GetUnknown()) != 0 || len(raw.Signatures) != 1 || len(raw.Signatures[0]) != 64 || proto.Unmarshal(raw.BodyBytes, &body) != nil || proto.Unmarshal(raw.AuthInfoBytes, &auth) != nil || len(body.ProtoReflect().GetUnknown()) != 0 || len(auth.ProtoReflect().GetUnknown()) != 0 {
		return ErrBackend
	}
	if len(body.Messages) != 1 || len(body.ExtensionOptions) != 0 || len(body.NonCriticalExtensionOptions) != 0 || body.Memo != r.Memo || body.TimeoutHeight == 0 || body.Unordered || body.TimeoutTimestamp != nil {
		return ErrBackend
	}
	m := body.Messages[0]
	var send bank.MsgSend
	if m == nil || m.TypeUrl != "/cosmos.bank.v1beta1.MsgSend" || len(m.ProtoReflect().GetUnknown()) != 0 || proto.Unmarshal(m.Value, &send) != nil || len(send.ProtoReflect().GetUnknown()) != 0 || send.FromAddress != r.Sender || send.ToAddress != r.Recipient || len(send.Amount) != 1 || send.Amount[0] == nil || len(send.Amount[0].ProtoReflect().GetUnknown()) != 0 || send.Amount[0].Denom != "uwolo" || send.Amount[0].Amount != r.AmountUWolo {
		return ErrBackend
	}
	if len(auth.SignerInfos) != 1 || auth.SignerInfos[0] == nil || auth.Fee == nil || auth.Tip != nil {
		return ErrBackend
	}
	info, fee := auth.SignerInfos[0], auth.Fee
	if len(info.ProtoReflect().GetUnknown()) != 0 || info.Sequence != s.Sequence || info.PublicKey == nil || info.PublicKey.TypeUrl != "/cosmos.crypto.secp256k1.PubKey" || len(info.PublicKey.ProtoReflect().GetUnknown()) != 0 || info.ModeInfo == nil || len(info.ModeInfo.ProtoReflect().GetUnknown()) != 0 || info.ModeInfo.GetSingle() == nil || len(info.ModeInfo.GetSingle().ProtoReflect().GetUnknown()) != 0 || info.ModeInfo.GetSingle().Mode != signapi.SignMode_SIGN_MODE_DIRECT {
		return ErrBackend
	}
	var key secp.PubKey
	if proto.Unmarshal(info.PublicKey.Value, &key) != nil || len(key.ProtoReflect().GetUnknown()) != 0 || !bytes.Equal(key.Key, b.publicKey.Key) || len(fee.ProtoReflect().GetUnknown()) != 0 || fee.Payer != "" || fee.Granter != "" || fee.GasLimit != b.cfg.GasLimit || len(fee.Amount) != 1 || fee.Amount[0] == nil || len(fee.Amount[0].ProtoReflect().GetUnknown()) != 0 || fee.Amount[0].Denom != "uwolo" || fee.Amount[0].Amount != b.cfg.FeesUWolo {
		return ErrBackend
	}
	signBytes, _ := proto.Marshal(&txapi.SignDoc{BodyBytes: raw.BodyBytes, AuthInfoBytes: raw.AuthInfoBytes, ChainId: "wolo-1", AccountNumber: s.AccountNumber})
	if !b.publicKey.VerifySignature(signBytes, raw.Signatures[0]) {
		return ErrBackend
	}
	return nil
}

func (b *KeyringBackend) get(ctx context.Context, base *url.URL, path string) ([]byte, error) {
	u := *base
	u.Path += path
	return b.request(ctx, http.MethodGet, u.String(), nil)
}
func (b *KeyringBackend) request(ctx context.Context, method, target string, body io.Reader) ([]byte, error) {
	request, err := http.NewRequestWithContext(ctx, method, target, body)
	if err != nil {
		return nil, ErrBackend
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Accept-Encoding", "identity")
	if method == http.MethodPost {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := b.client.Do(request)
	if err != nil {
		return nil, ErrBackend
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK || response.ContentLength > 1<<20 || response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" {
		return nil, ErrBackend
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, (1<<20)+1))
	if err != nil || len(data) > 1<<20 || !chainjson.Valid(data) {
		return nil, ErrBackend
	}
	return data, nil
}
func (b *KeyringBackend) head(ctx context.Context) (int64, error) {
	data, err := b.get(ctx, b.rpc, "/status")
	if err != nil {
		return 0, err
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
		Error  json.RawMessage `json:"error"`
	}
	if json.Unmarshal(data, &envelope) != nil || len(envelope.Error) > 0 && !bytes.Equal(envelope.Error, []byte("null")) {
		return 0, ErrBackend
	}
	fields, ok := chainjson.Object(envelope.Result)
	if !ok {
		return 0, ErrBackend
	}
	syncInfo, ok := chainjson.Object(fields["sync_info"])
	if !ok {
		return 0, ErrBackend
	}
	var catching *bool
	if json.Unmarshal(syncInfo["catching_up"], &catching) != nil || catching == nil || *catching {
		return 0, ErrBackend
	}
	var status core.ResultStatus
	if cmtjson.Unmarshal(envelope.Result, &status) != nil || status.NodeInfo.Network != "wolo-1" || status.SyncInfo.LatestBlockHeight <= 0 || len(status.SyncInfo.LatestBlockHash) != 32 || status.SyncInfo.LatestBlockTime.IsZero() || time.Since(status.SyncInfo.LatestBlockTime) > 30*time.Second || status.SyncInfo.LatestBlockTime.After(time.Now().Add(5*time.Second)) {
		return 0, ErrBackend
	}
	return status.SyncInfo.LatestBlockHeight, nil
}
func (b *KeyringBackend) account(ctx context.Context) (uint64, uint64, error) {
	data, err := b.get(ctx, b.rest, "/cosmos/auth/v1beta1/accounts/"+b.cfg.Vault)
	if err != nil {
		return 0, 0, err
	}
	var response struct {
		Account *struct {
			Type     string `json:"@type"`
			Address  string `json:"address"`
			Number   string `json:"account_number"`
			Sequence string `json:"sequence"`
			Public   *struct {
				Type string `json:"@type"`
				Key  string `json:"key"`
			} `json:"pub_key"`
		} `json:"account"`
	}
	if json.Unmarshal(data, &response) != nil || response.Account == nil || response.Account.Type != "/cosmos.auth.v1beta1.BaseAccount" || response.Account.Address != b.cfg.Vault {
		return 0, 0, ErrBackend
	}
	a := response.Account
	number, e1 := strconv.ParseUint(a.Number, 10, 64)
	sequence, e2 := strconv.ParseUint(a.Sequence, 10, 64)
	if e1 != nil || e2 != nil || strconv.FormatUint(number, 10) != a.Number || strconv.FormatUint(sequence, 10) != a.Sequence {
		return 0, 0, ErrBackend
	}
	if a.Public != nil {
		key, err := base64.StdEncoding.DecodeString(a.Public.Key)
		if err != nil || a.Public.Type != "/cosmos.crypto.secp256k1.PubKey" || !bytes.Equal(key, b.publicKey.Key) {
			return 0, 0, ErrBackend
		}
	}
	return number, sequence, nil
}

// Broadcast transmits exactly the supplied transaction once. Transport errors,
// malformed acknowledgements and cancellation are UNKNOWN, never safe retries.
// The engine must persist and validate these bytes before entering this method.
func (b *KeyringBackend) Broadcast(ctx context.Context, s SignedTransaction) (BroadcastResult, error) {
	unknown := BroadcastResult{Status: "UNKNOWN"}
	if b == nil || len(s.Bytes) == 0 || len(s.Bytes) > 65536 || len(s.Hash) != 64 || !strings.EqualFold(s.Hash, hex.EncodeToString(cmttypes.Tx(s.Bytes).Hash())) {
		return unknown, ErrBackend
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.closed.Load() {
		return unknown, ErrBackend
	}
	ctx, cancel := context.WithTimeout(ctx, 4*time.Second)
	defer cancel()
	encoded, _ := json.Marshal(struct {
		JSONRPC string            `json:"jsonrpc"`
		ID      int               `json:"id"`
		Method  string            `json:"method"`
		Params  map[string]string `json:"params"`
	}{"2.0", 1, "broadcast_tx_sync", map[string]string{"tx": base64.StdEncoding.EncodeToString(s.Bytes)}})
	data, err := b.request(ctx, http.MethodPost, b.rpc.String(), bytes.NewReader(encoded))
	if err != nil {
		return unknown, ErrBackend
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
		Error  json.RawMessage `json:"error"`
	}
	if json.Unmarshal(data, &envelope) != nil || len(envelope.Error) > 0 && !bytes.Equal(envelope.Error, []byte("null")) {
		return unknown, ErrBackend
	}
	fields, ok := chainjson.Object(envelope.Result)
	if !ok {
		return unknown, ErrBackend
	}
	code, ok := chainjson.ExecutionCode(fields)
	if !ok {
		return unknown, ErrBackend
	}
	var hash string
	if json.Unmarshal(fields["hash"], &hash) != nil || !strings.EqualFold(hash, s.Hash) {
		return unknown, ErrBackend
	}
	if code != 0 {
		return BroadcastResult{Status: "FAILED", Code: code}, nil
	}
	return BroadcastResult{Status: "ACCEPTED"}, nil
}

func (b *KeyringBackend) Confirm(ctx context.Context, r TransferRequest, s SignedTransaction) (Confirmation, error) {
	if b.ValidateSigned(r, s) != nil {
		return Confirmation{Status: "UNKNOWN"}, ErrBackend
	}
	if b.cfg.ConfirmTransaction != nil {
		return b.cfg.ConfirmTransaction(ctx, r, s)
	}
	evidence, err := b.reader.ReadTransfer(ctx, satchel.TransferIntent{Sender: r.Sender, Recipient: r.Recipient, AmountUWolo: r.AmountUWolo, Memo: r.Memo}, s.Hash)
	if err != nil {
		// An unauthenticated failure cannot release a real financial hold.
		return Confirmation{Status: "UNKNOWN"}, ErrBackend
	}
	return Confirmation{Status: "OBSERVED_NONCREDITING", ReceiptID: evidence.Receipt.ID(), Height: evidence.Observation.Height, BlockHash: evidence.Observation.BlockHash}, nil
}
