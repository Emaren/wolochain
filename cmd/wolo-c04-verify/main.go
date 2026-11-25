// wolo-c04-verify performs noncrediting read-only historical request -> chain proof correlation.
// It never unlocks keys, sends funds, creates an authority, or modifies settlement journals.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"

	"github.com/emaren/wolochain/internal/satchel"
)

var digest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var txDigest = regexp.MustCompile(`^[A-F0-9]{64}$`)

type original struct {
	Request struct {
		RequestID  string `json:"request_id"`
		ToAddress  string `json:"to_address"`
		Amount     string `json:"amount_uwolo"`
		Memo       string `json:"memo"`
		SignerRole string `json:"signer_role"`
	} `json:"request"`
	Response struct {
		RequestID     string `json:"request_id"`
		Status        string `json:"status"`
		TxHash        string `json:"tx_hash"`
		SignerAddress string `json:"signer_address"`
		SignerRole    string `json:"signer_role"`
	} `json:"response"`
}

func scan(root, fingerprint, hash string) (satchel.TransferIntent, error) {
	var result satchel.TransferIntent
	if !digest.MatchString(fingerprint) || !txDigest.MatchString(hash) {
		return result, errors.New("INVALID_INPUT")
	}
	info, err := os.Lstat(root)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return result, errors.New("INVALID_STATE_ROOT")
	}
	dir := filepath.Join(root, "requests")
	info, err = os.Lstat(dir)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return result, errors.New("INVALID_REQUESTS_DIR")
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return result, errors.New("REQUESTS_UNAVAILABLE")
	}
	if len(entries) > 10000 {
		return result, errors.New("REQUEST_CENSUS_UNBOUNDED")
	}
	matches := 0
	for _, entry := range entries {
		n := entry.Name()
		if !strings.HasPrefix(n, "aoe2-") || !strings.HasSuffix(n, ".json") {
			continue
		}
		id := strings.TrimSuffix(n, ".json")
		h := sha256.Sum256([]byte(id))
		if hex.EncodeToString(h[:]) != fingerprint {
			continue
		}
		matches++
		if matches > 1 {
			return result, errors.New("AMBIGUOUS_REQUEST_ID")
		}
		if entry.Type()&os.ModeSymlink != 0 || !entry.Type().IsRegular() {
			return result, errors.New("UNSAFE_REQUEST_FILE")
		}
		fd, err := syscall.Open(filepath.Join(dir, n), syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
		if err != nil {
			return result, errors.New("UNSAFE_REQUEST_OPEN")
		}
		f := os.NewFile(uintptr(fd), "protected-original")
		b, readErr := io.ReadAll(io.LimitReader(f, 1048577))
		f.Close()
		if readErr != nil || len(b) > 1048576 {
			return result, errors.New("INVALID_REQUEST_BYTES")
		}
		var v original
		if json.Unmarshal(b, &v) != nil {
			return result, errors.New("INVALID_REQUEST_JSON")
		}
		if v.Request.RequestID != id || v.Response.RequestID != id || v.Response.Status != "accepted" ||
			strings.ToUpper(v.Response.TxHash) != hash || v.Request.SignerRole != "escrow" ||
			v.Response.SignerRole != "escrow" || v.Request.Amount != "100000000" ||
			len(v.Request.Memo) == 0 || len(v.Request.Memo) > 256 ||
			v.Request.ToAddress == "" || v.Response.SignerAddress == "" {
			return result, errors.New("HISTORICAL_REQUEST_IDENTITY_HOLD")
		}
		result = satchel.TransferIntent{Sender: v.Response.SignerAddress, Recipient: v.Request.ToAddress, AmountUWolo: v.Request.Amount, Memo: v.Request.Memo}
	}
	if matches != 1 {
		return result, errors.New("ORIGINAL_REQUEST_NOT_FOUND")
	}
	return result, nil
}

func main() {
	root := flag.String("state-root", "", "original root-only settlement state")
	fingerprint := flag.String("request-fingerprint", "", "sha256 of original request id")
	hash := flag.String("tx-hash", "", "actual previously recorded public tx hash")
	rpc := flag.String("rpc", "", "fixed publicly readable RPC")
	rest := flag.String("rest", "", "fixed publicly readable REST")
	witness := flag.String("witness-rpc", "", "optional comparison only; not independent trust")
	flag.Parse()
	hold := func(code string) {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"schema": "wolo.c04.exact-transfer-noncrediting.v1", "status": "HOLD", "reason": code, "funds_moved": false, "retry_authorized": false, "c04_closed": false})
		os.Exit(3)
	}
	if os.Geteuid() != 0 || *root == "" || flag.NArg() != 0 {
		hold("ROOT_ONLY_EXACT_REQUEST")
	}
	intent, err := scan(*root, *fingerprint, strings.ToUpper(*hash))
	if err != nil {
		hold(err.Error())
	}
	reader, err := satchel.NewChainReader(satchel.SourceConfig{RPC: *rpc, REST: *rest, WitnessRPC: *witness})
	if err != nil {
		hold("SOURCE_CONFIGURATION_UNAVAILABLE")
	}
	defer reader.Close()
	found, err := reader.ReadTransfer(context.Background(), intent, strings.ToUpper(*hash))
	if err != nil {
		var evidence *satchel.EvidenceError
		if errors.As(err, &evidence) {
			hold(string(evidence.Code))
		}
		hold("CHAIN_OBSERVATION_UNAVAILABLE")
	}
	if found.CreditAuthorized() || found.ConsensusAuthenticated() || found.Status() != "NONCREDITING" {
		hold("UNEXPECTED_AUTHORITY")
	}
	result := map[string]any{
		"schema": "wolo.c04.exact-transfer-noncrediting.v1", "status": "HOLD",
		"source_evidence":   "ORIGINAL_REQUEST_AND_CRYPTOGRAPHICALLY_CHECKED_CHAIN_CANDIDATE",
		"request_id_sha256": *fingerprint, "tx_hash": strings.ToUpper(*hash),
		"block_height": found.Observation.Height, "block_hash": found.Observation.BlockHash,
		"chain_id": found.Observation.ChainID, "exact_original_msgsend": true,
		"witness_compared": found.WitnessCompared, "independent_consensus_authenticated": false,
		"authority": found.TrustStatus(), "funds_moved": false,
		"retry_authorized": false, "claim_889_reconciled": false, "c04_closed": false,
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, "OUTPUT_UNAVAILABLE")
		os.Exit(3)
	}
	os.Exit(3)
}
