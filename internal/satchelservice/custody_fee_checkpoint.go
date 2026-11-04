package satchelservice

// Fee obligations are read from the existing custody journal, not supplied by
// the reviewer. This checkpoint is not a bank proof or a coverage assertion.
import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"github.com/emaren/wolochain/internal/chainjson"
	bolt "go.etcd.io/bbolt"
	"google.golang.org/protobuf/proto"
)

const custodyFeeCheckpointMaxIDs = 1024
const custodyFeeCheckpointMaxBody = 64 << 10
const custodyFeeCheckpointMaxOutput = 4 << 20

var errCustodyFeeCheckpoint = errors.New("custody_fee_checkpoint_unverifiable")

type custodyFeeCheckpointRequest struct {
	Protocol     int      `json:"protocol"`
	OperationIDs []string `json:"operation_ids"`
}

func validateCustodyFeeIDs(ids []string) error {
	if len(ids) > custodyFeeCheckpointMaxIDs {
		return errCustodyFeeCheckpoint
	}
	seen := make(map[string]bool, len(ids))
	for _, id := range ids {
		if !wagerIDs.MatchString(id) || seen[id] {
			return errCustodyFeeCheckpoint
		}
		seen[id] = true
	}
	raw, err := json.Marshal(custodyFeeCheckpointRequest{1, ids})
	if err != nil || len(raw) > custodyFeeCheckpointMaxBody {
		return errCustodyFeeCheckpoint
	}
	return nil
}

// ReviewerFeeCheckpoint captures the validated journal and fee inventory in
// ONE Bolt read snapshot while holding the existing execution mutex. Requested
// IDs affect only status lookup; they never filter unresolved obligations.
// No signing, broadcast, confirmation, journal update or fee release occurs.
func (e *Engine) ReviewerFeeCheckpoint(operationIDs []string) (ReviewerCustodyFeeCheckpoint, error) {
	if e == nil || validateCustodyFeeIDs(operationIDs) != nil {
		return ReviewerCustodyFeeCheckpoint{}, errCustodyFeeCheckpoint
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.db == nil || e.backend == nil || e.now == nil {
		return ReviewerCustodyFeeCheckpoint{}, errCustodyFeeCheckpoint
	}
	out := ReviewerCustodyFeeCheckpoint{Protocol: 1, Kind: "custody_fee_checkpoint", ChainID: "wolo-1", Denom: "uwolo", Vault: e.policy.Vault,
		UnresolvedFees: make([]ReviewerPendingFee, 0), AccountedOperations: make(map[string]string, len(operationIDs)),
		AccountedFingerprints: make(map[string]string, len(operationIDs))}
	// Identify the existing public policy only. A legacy/unconfigured policy
	// remains readable and acquires no approval or execution authority here.
	if len(e.policy.WagerApprovalKey) == ed25519.PublicKeySize && !bytesAllZero(e.policy.WagerApprovalKey) {
		digest := sha256.Sum256(e.policy.WagerApprovalKey)
		out.WagerApprovalKeyFingerprint = hex.EncodeToString(digest[:])
	}
	for _, id := range operationIDs {
		out.AccountedOperations[id] = "NOT_RECORDED"
		out.AccountedFingerprints[id] = ""
	}
	err := e.db.View(func(tx *bolt.Tx) error {
		journal, err := e.custodyJournalTx(tx)
		if err != nil || journal.UnresolvedCount > reviewerMaxPendingOperations {
			return errCustodyFeeCheckpoint
		}
		out.JournalDigest, out.PolicyDigest = journal.JournalDigest, journal.PolicyDigest
		var records, readBytes uint64
		// Bolt iterates bytewise lexicographically, making the entries canonical.
		err = tx.Bucket(operations).ForEach(func(id, value []byte) error {
			records++
			if value == nil || records > custodyJournalMaxRecords || uint64(len(id)+len(value)) > custodyJournalMaxBytes-readBytes {
				return errCustodyFeeCheckpoint
			}
			readBytes += uint64(len(id) + len(value))
			r, err := load(tx, string(id))
			if err != nil {
				return errCustodyFeeCheckpoint
			}
			if _, requested := out.AccountedOperations[string(id)]; requested {
				out.AccountedOperations[string(id)] = r.Result.Status
				out.AccountedFingerprints[string(id)] = e.custodyWagerFingerprint(r.Request)
			}
			switch r.Result.Status {
			case "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING":
				if len(out.UnresolvedFees) >= reviewerMaxPendingOperations {
					return errCustodyFeeCheckpoint
				}
				fee, err := e.custodyUnresolvedFee(r)
				if err != nil {
					return err
				}
				stage := "uncertain"
				if len(r.Signed.Bytes) == 0 {
					stage = "prepared"
				}
				out.UnresolvedFees = append(out.UnresolvedFees, ReviewerPendingFee{OperationID: string(id), Stage: stage, FeeUWolo: fee})
			}
			return nil
		})
		if err != nil || uint64(len(out.UnresolvedFees)) != journal.UnresolvedCount || records != journal.OperationsCount {
			return errCustodyFeeCheckpoint
		}
		return nil
	})
	if err != nil {
		return ReviewerCustodyFeeCheckpoint{}, err
	}
	out.ObservedAtMS = e.now().UnixMilli()
	if out.ObservedAtMS <= 0 {
		return ReviewerCustodyFeeCheckpoint{}, errCustodyFeeCheckpoint
	}
	raw, err := json.Marshal(out)
	if err != nil || len(raw) > custodyFeeCheckpointMaxOutput {
		return ReviewerCustodyFeeCheckpoint{}, errCustodyFeeCheckpoint
	}
	return out, nil
}

// Status alone cannot account for an issuer's outstanding approval. Bind only
// a fully authenticated original wager to the issuer's normalized identity;
// historical ownerless records and unverifiable reservations remain unbound.
func (e *Engine) custodyWagerFingerprint(r TransferRequest) string {
	a := r.Reservation
	if a == nil || a.IssuedAt <= 0 || e.policy.validate(r, time.Unix(a.IssuedAt, 0)) != nil {
		return ""
	}
	original := *a
	original.IssuedAt, original.ExpiresAt, original.Signature = 0, 0, ""
	return reviewerFingerprint(original)
}

func (e *Engine) custodyUnresolvedFee(r record) (string, error) {
	maximum := strconv.Itoa(reviewerMaxOperationFeeUWolo)
	if len(r.Signed.Bytes) == 0 {
		// Expiry does not release an existing unresolved obligation. Authenticate
		// the original canonical reservation at its issuance instant instead.
		if e.custodyWagerFingerprint(r.Request) != "" {
			return r.Request.Reservation.FeeUWolo, nil
		}
		return maximum, nil
	}
	// custodyJournalTx has already checked the stored byte hash and invoked
	// the real backend's ValidateSigned. Decode the fee from those exact bytes.
	var raw txapi.TxRaw
	var auth txapi.AuthInfo
	if proto.Unmarshal(r.Signed.Bytes, &raw) != nil || len(raw.ProtoReflect().GetUnknown()) != 0 || len(raw.Signatures) != 1 ||
		proto.Unmarshal(raw.AuthInfoBytes, &auth) != nil || len(auth.ProtoReflect().GetUnknown()) != 0 || auth.Fee == nil {
		return maximum, nil
	}
	f := auth.Fee
	if len(f.ProtoReflect().GetUnknown()) != 0 || f.Payer != "" || f.Granter != "" || auth.Tip != nil || len(f.Amount) != 1 || f.Amount[0] == nil ||
		len(f.Amount[0].ProtoReflect().GetUnknown()) != 0 || f.Amount[0].Denom != "uwolo" {
		return maximum, nil
	}
	// A proven fee above the protocol maximum cannot be bounded by that maximum.
	// Refuse the checkpoint rather than silently understating the actual debit.
	n, err := reviewerAmount(f.Amount[0].Amount, ^uint64(0), false)
	if err != nil || n > reviewerMaxOperationFeeUWolo {
		return "", errCustodyFeeCheckpoint
	}
	if n == 0 {
		return maximum, nil
	}
	return f.Amount[0].Amount, nil
}

func (h *privateHTTPHandler) custodyFeeCheckpoint(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		httpFailure(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}
	backend, ok := h.backend.(HTTPCustodyFeeCheckpointBackend)
	if !ok {
		httpFailure(w, http.StatusServiceUnavailable, "custody_fee_checkpoint_unavailable")
		return
	}
	media, params, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" || (params["charset"] != "" && !strings.EqualFold(params["charset"], "utf-8")) || r.Header.Get("Content-Encoding") != "" {
		httpFailure(w, http.StatusUnsupportedMediaType, "invalid_bounded_request")
		return
	}
	if r.ContentLength > custodyFeeCheckpointMaxBody {
		httpFailure(w, http.StatusRequestEntityTooLarge, "invalid_bounded_request")
		return
	}
	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, custodyFeeCheckpointMaxBody))
	if err != nil {
		var limit *http.MaxBytesError
		status := http.StatusBadRequest
		if errors.As(err, &limit) {
			status = http.StatusRequestEntityTooLarge
		}
		httpFailure(w, status, "invalid_bounded_request")
		return
	}
	var input custodyFeeCheckpointRequest
	if !utf8.Valid(data) || !chainjson.Valid(data) || strictHTTPJSON(data, &input) != nil || input.Protocol != 1 || input.OperationIDs == nil || validateCustodyFeeIDs(input.OperationIDs) != nil {
		httpFailure(w, http.StatusBadRequest, "invalid_fee_checkpoint_request")
		return
	}
	if ctx.Err() != nil {
		httpFailure(w, http.StatusRequestTimeout, "request_canceled")
		return
	}
	snapshot, err := backend.ReviewerFeeCheckpoint(input.OperationIDs)
	if err != nil || ctx.Err() != nil || snapshot.Protocol != 1 || snapshot.Kind != "custody_fee_checkpoint" || snapshot.ChainID != "wolo-1" || snapshot.Denom != "uwolo" ||
		snapshot.Vault != h.identity.VaultAddress || !httpDigestPattern.MatchString(snapshot.JournalDigest) || !httpDigestPattern.MatchString(snapshot.PolicyDigest) ||
		snapshot.ObservedAtMS <= 0 || len(snapshot.UnresolvedFees) > reviewerMaxPendingOperations || len(snapshot.AccountedOperations) != len(input.OperationIDs) ||
		len(snapshot.AccountedFingerprints) != len(input.OperationIDs) {
		httpFailure(w, http.StatusConflict, "custody_fee_checkpoint_unverifiable")
		return
	}
	for _, id := range input.OperationIDs {
		status, hasStatus := snapshot.AccountedOperations[id]
		fingerprint, hasFingerprint := snapshot.AccountedFingerprints[id]
		if !hasStatus || !hasFingerprint || (fingerprint != "" && !httpDigestPattern.MatchString(fingerprint)) ||
			(status == "NOT_RECORDED" && fingerprint != "") {
			httpFailure(w, http.StatusConflict, "custody_fee_checkpoint_unverifiable")
			return
		}
		switch status {
		case "NOT_RECORDED", "UNKNOWN", "ACCEPTED", "OBSERVED_NONCREDITING", "CONFIRMED", "FAILED", "REFUSED":
		default:
			httpFailure(w, http.StatusConflict, "custody_fee_checkpoint_unverifiable")
			return
		}
	}
	wire, err := json.Marshal(snapshot)
	if err != nil || len(wire) > custodyFeeCheckpointMaxOutput {
		httpFailure(w, http.StatusConflict, "custody_fee_checkpoint_unverifiable")
		return
	}
	httpWrite(w, http.StatusOK, snapshot)
}

var _ HTTPCustodyFeeCheckpointBackend = (*Engine)(nil)
