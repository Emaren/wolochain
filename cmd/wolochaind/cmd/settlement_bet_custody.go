package cmd

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	betCustodyStateVersion                   = 1
	betCustodyJournalVersion                 = 1
	betCustodyDepositMemoPrefix              = "wolo.bet.reserve.v1:"
	betCustodyDefaultMaxCreditedBalanceUWolo = uint64(10_000_000_000)
	betCustodyStateLockTTL                   = 2 * time.Minute
	betCustodyAccountKindUser                = "user"
	betCustodyAccountKindOperator            = "operator"
	betCustodyReservationStatusReserved      = "reserved"
	betCustodyReservationStatusPartial       = "partial"
	betCustodyReservationStatusReleased      = "released"
	betCustodyReservationStatusSettled       = "settled"
	betCustodyReservationLegStatusReserved   = "reserved"
	betCustodyReservationLegStatusReleased   = "released"
	betCustodyReservationLegStatusSettled    = "settled"
)

type betCustodyAccount struct {
	ID                 string    `json:"id"`
	Kind               string    `json:"kind"`
	SourceWallet       string    `json:"source_wallet,omitempty"`
	AvailableUWolo         uint64    `json:"available_uwolo"`
	ReservedUWolo          uint64    `json:"reserved_uwolo"`
	WithdrawalPendingUWolo uint64    `json:"withdrawal_pending_uwolo"`
	DepositedUWolo         uint64    `json:"deposited_uwolo"`
	WithdrawnUWolo     uint64    `json:"withdrawn_uwolo"`
	SettledDebitUWolo  uint64    `json:"settled_debit_uwolo"`
	SettledCreditUWolo uint64    `json:"settled_credit_uwolo"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}

type betCustodyDepositIntent struct {
	ID          string     `json:"id"`
	AccountID   string     `json:"account_id"`
	Sender      string     `json:"sender"`
	AmountUWolo uint64     `json:"amount_uwolo"`
	Memo        string     `json:"memo"`
	Status      string     `json:"status"`
	TxHash      string     `json:"tx_hash,omitempty"`
	CreatedAt   time.Time  `json:"created_at"`
	CreditedAt  *time.Time `json:"credited_at,omitempty"`
}

type betCustodyReservationLeg struct {
	ID          string `json:"id"`
	MarketID    string `json:"market_id"`
	MarketType  string `json:"market_type"`
	Side        string `json:"side"`
	AmountUWolo uint64 `json:"amount_uwolo"`
	Status      string `json:"status"`
}

type betCustodyReservation struct {
	ID                 string                     `json:"id"`
	RequestID          string                     `json:"request_id"`
	RequestFingerprint string                     `json:"request_fingerprint"`
	AccountID          string                     `json:"account_id"`
	GameIdentity       string                     `json:"game_identity"`
	PropositionHash    string                     `json:"proposition_hash"`
	Legs               []betCustodyReservationLeg `json:"legs"`
	Status             string                     `json:"status"`
	CreatedAt          time.Time                  `json:"created_at"`
	UpdatedAt          time.Time                  `json:"updated_at"`
}

type betCustodySettlementDebit struct {
	ReservationID string `json:"reservation_id"`
	LegID         string `json:"leg_id"`
	AmountUWolo   uint64 `json:"amount_uwolo"`
}

type betCustodySettlementCredit struct {
	AccountID   string `json:"account_id"`
	AmountUWolo uint64 `json:"amount_uwolo"`
	Kind        string `json:"kind"`
}

type betCustodyOperatorAllocation struct {
	AccountID   string `json:"account_id"`
	AmountUWolo uint64 `json:"amount_uwolo"`
}

type betCustodyWithdrawal struct {
	ID                 string     `json:"id"`
	RequestID          string     `json:"request_id"`
	RequestFingerprint string     `json:"request_fingerprint"`
	AccountID          string     `json:"account_id"`
	ToAddress          string     `json:"to_address"`
	AmountUWolo        uint64     `json:"amount_uwolo"`
	Memo               string     `json:"memo"`
	Status             string     `json:"status"`
	TxHash             string     `json:"tx_hash,omitempty"`
	AttemptCount       int        `json:"attempt_count"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
	ConfirmedAt        *time.Time `json:"confirmed_at,omitempty"`
}

type betCustodySettlementRun struct {
	ID                  string                         `json:"id"`
	RequestFingerprint  string                         `json:"request_fingerprint"`
	Debits              []betCustodySettlementDebit    `json:"debits"`
	Credits             []betCustodySettlementCredit   `json:"credits"`
	OperatorAllocations []betCustodyOperatorAllocation `json:"operator_allocations,omitempty"`
	Status              string                         `json:"status"`
	CreatedAt           time.Time                      `json:"created_at"`
}

type betCustodyIdempotencyRecord struct {
	Scope       string `json:"scope"`
	Key         string `json:"key"`
	Fingerprint string `json:"fingerprint"`
	ResourceID  string `json:"resource_id"`
}

type betCustodyLedgerEntry struct {
	AccountID       string `json:"account_id"`
	EntryType       string `json:"entry_type"`
	AmountUWolo     uint64 `json:"amount_uwolo"`
	DepositIntentID string `json:"deposit_intent_id,omitempty"`
	TxHash          string `json:"tx_hash,omitempty"`
	ReservationID   string `json:"reservation_id,omitempty"`
	LegID           string `json:"leg_id,omitempty"`
	SettlementRunID string `json:"settlement_run_id,omitempty"`
	WithdrawalID    string `json:"withdrawal_id,omitempty"`
	Detail          string `json:"detail,omitempty"`
}

type betCustodyStateDelta struct {
	AccountUpserts       []betCustodyAccount           `json:"account_upserts,omitempty"`
	DepositIntentUpserts []betCustodyDepositIntent     `json:"deposit_intent_upserts,omitempty"`
	ReservationUpserts   []betCustodyReservation       `json:"reservation_upserts,omitempty"`
	SettlementRunUpserts []betCustodySettlementRun      `json:"settlement_run_upserts,omitempty"`
	WithdrawalUpserts    []betCustodyWithdrawal         `json:"withdrawal_upserts,omitempty"`
	IdempotencyUpserts   []betCustodyIdempotencyRecord  `json:"idempotency_upserts,omitempty"`
	DepositTxBindings    map[string]string             `json:"deposit_tx_bindings,omitempty"`
}

type betCustodyJournalRecord struct {
	Version       int                     `json:"version"`
	Sequence      uint64                  `json:"sequence"`
	OperationID   string                  `json:"operation_id"`
	OperationType string                  `json:"operation_type"`
	Entries       []betCustodyLedgerEntry `json:"entries,omitempty"`
	Delta         betCustodyStateDelta    `json:"delta"`
	CreatedAt     time.Time               `json:"created_at"`
	PreviousHash  string                  `json:"previous_hash,omitempty"`
	Hash          string                  `json:"hash"`
}

type betCustodySnapshot struct {
	Version        int                                    `json:"version"`
	Sequence       uint64                                 `json:"sequence"`
	LastEventHash  string                                 `json:"last_event_hash,omitempty"`
	StateHash      string                                 `json:"state_hash"`
	Accounts       map[string]betCustodyAccount           `json:"accounts"`
	DepositIntents map[string]betCustodyDepositIntent     `json:"deposit_intents"`
	DepositTxs     map[string]string                      `json:"deposit_txs"`
	Reservations   map[string]betCustodyReservation       `json:"reservations"`
	SettlementRuns map[string]betCustodySettlementRun     `json:"settlement_runs"`
	Withdrawals    map[string]betCustodyWithdrawal        `json:"withdrawals"`
	Idempotency    map[string]betCustodyIdempotencyRecord `json:"idempotency"`
	UpdatedAt      time.Time                              `json:"updated_at"`
}

type betCustodyLoadedState struct {
	Snapshot  betCustodySnapshot
	Recovered bool
}

func newBetCustodySnapshot() betCustodySnapshot {
	return betCustodySnapshot{
		Version:        betCustodyStateVersion,
		Accounts:       map[string]betCustodyAccount{},
		DepositIntents: map[string]betCustodyDepositIntent{},
		DepositTxs:     map[string]string{},
		Reservations:   map[string]betCustodyReservation{},
		SettlementRuns: map[string]betCustodySettlementRun{},
		Withdrawals:    map[string]betCustodyWithdrawal{},
		Idempotency:    map[string]betCustodyIdempotencyRecord{},
	}
}

func (cfg settlementConfig) betCustodyRoot() string {
	if strings.TrimSpace(cfg.BetCustodyStateDir) != "" {
		return filepath.Clean(cfg.BetCustodyStateDir)
	}
	return filepath.Join(cfg.StateDir, "bet-custody")
}

func (cfg settlementConfig) betCustodySnapshotPath() string {
	return filepath.Join(cfg.betCustodyRoot(), "snapshot-v1.json")
}

func (cfg settlementConfig) betCustodyJournalPath() string {
	return filepath.Join(cfg.betCustodyRoot(), "journal-v1.jsonl")
}

func (cfg settlementConfig) betCustodyStateLockPath() string {
	return filepath.Join(cfg.betCustodyRoot(), "locks", "state.lock")
}

func (cfg settlementConfig) betCustodySignerLockPath() string {
	return filepath.Join(cfg.betCustodyRoot(), "locks", "signer.lock")
}

func (cfg settlementConfig) betCustodyConfigured() bool {
	return strings.TrimSpace(cfg.BetCustodyKeyName) != "" &&
		isWoloAddress(cfg.BetCustodyAddress, cfg.AddressPrefix) &&
		strings.TrimSpace(cfg.BetCustodyStateDir) != ""
}

func betCustodyRandomID(prefix string) (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return prefix + hex.EncodeToString(buf), nil
}

func betCustodyIdempotencyKey(scope, key string) string {
	return strings.TrimSpace(scope) + ":" + strings.TrimSpace(key)
}

func betCustodyHashValue(value any) (string, error) {
	payload, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func betCustodyJournalHash(record betCustodyJournalRecord) (string, error) {
	record.Hash = ""
	return betCustodyHashValue(record)
}

func betCustodySnapshotHash(snapshot betCustodySnapshot) (string, error) {
	snapshot.StateHash = ""
	return betCustodyHashValue(snapshot)
}

func applyBetCustodyDelta(snapshot *betCustodySnapshot, delta betCustodyStateDelta) {
	for _, account := range delta.AccountUpserts {
		snapshot.Accounts[account.ID] = account
	}
	for _, intent := range delta.DepositIntentUpserts {
		snapshot.DepositIntents[intent.ID] = intent
	}
	for _, reservation := range delta.ReservationUpserts {
		snapshot.Reservations[reservation.ID] = reservation
	}
	for _, run := range delta.SettlementRunUpserts {
		snapshot.SettlementRuns[run.ID] = run
	}
	for _, withdrawal := range delta.WithdrawalUpserts {
		snapshot.Withdrawals[withdrawal.ID] = withdrawal
	}
	for _, item := range delta.IdempotencyUpserts {
		snapshot.Idempotency[betCustodyIdempotencyKey(item.Scope, item.Key)] = item
	}
	for txHash, intentID := range delta.DepositTxBindings {
		snapshot.DepositTxs[normalizeTxHash(txHash)] = intentID
	}
}

func (cfg settlementConfig) withBetCustodyExclusiveLock(lockPath string, failureCode string, fn func() error) error {
	if err := os.MkdirAll(filepath.Dir(lockPath), 0o700); err != nil {
		return err
	}

	waitFor := cfg.RequestTimeout
	if waitFor <= 0 {
		waitFor = 30 * time.Second
	}
	deadline := time.Now().Add(waitFor)

	for {
		lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err == nil {
			_, _ = lockFile.WriteString(time.Now().UTC().Format(time.RFC3339Nano))
			if syncErr := lockFile.Sync(); syncErr != nil {
				_ = lockFile.Close()
				_ = os.Remove(lockPath)
				return syncErr
			}
			_ = lockFile.Close()
			defer os.Remove(lockPath)
			return fn()
		}
		if !errors.Is(err, os.ErrExist) {
			return err
		}
		info, statErr := os.Stat(lockPath)
		if statErr == nil && time.Since(info.ModTime()) > betCustodyStateLockTTL {
			if removeErr := os.Remove(lockPath); removeErr == nil {
				continue
			}
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("%s: custody lock remained busy for %s", failureCode, waitFor)
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func (cfg settlementConfig) withBetCustodyStateLock(fn func() error) error {
	return cfg.withBetCustodyExclusiveLock(cfg.betCustodyStateLockPath(), "CUSTODY_STATE_BUSY", fn)
}

func (cfg settlementConfig) withBetCustodySignerLock(fn func() error) error {
	return cfg.withBetCustodyExclusiveLock(cfg.betCustodySignerLockPath(), "CUSTODY_SIGNER_BUSY", fn)
}

func syncDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}

func writeBetCustodySnapshot(path string, snapshot betCustodySnapshot) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	snapshot.Version = betCustodyStateVersion
	snapshot.UpdatedAt = time.Now().UTC()
	hash, err := betCustodySnapshotHash(snapshot)
	if err != nil {
		return err
	}
	snapshot.StateHash = hash
	payload, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return err
	}
	tmpPath := path + ".tmp"
	file, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err = file.Write(append(payload, '\n')); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if closeErr != nil {
		_ = os.Remove(tmpPath)
		return closeErr
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	return syncDirectory(filepath.Dir(path))
}

func appendBetCustodyJournalRecord(path string, record betCustodyJournalRecord) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	hash, err := betCustodyJournalHash(record)
	if err != nil {
		return err
	}
	record.Hash = hash
	payload, err := json.Marshal(record)
	if err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err = file.Write(append(payload, '\n')); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return syncDirectory(filepath.Dir(path))
}

func readBetCustodyJournal(path string) ([]betCustodyJournalRecord, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return []betCustodyJournalRecord{}, nil
	}
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) == 1 && strings.TrimSpace(lines[0]) == "" {
		return []betCustodyJournalRecord{}, nil
	}

	records := make([]betCustodyJournalRecord, 0, len(lines))
	previousHash := ""
	for index, line := range lines {
		if strings.TrimSpace(line) == "" {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: blank record at line %d", index+1)
		}
		var record betCustodyJournalRecord
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: decode line %d: %w", index+1, err)
		}
		if record.Version != betCustodyJournalVersion {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: unsupported journal version %d", record.Version)
		}
		if record.Sequence != uint64(index+1) {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: sequence %d at line %d", record.Sequence, index+1)
		}
		if record.PreviousHash != previousHash {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: previous hash mismatch at sequence %d", record.Sequence)
		}
		expected, err := betCustodyJournalHash(record)
		if err != nil {
			return nil, err
		}
		if !strings.EqualFold(expected, record.Hash) {
			return nil, fmt.Errorf("CUSTODY_JOURNAL_CORRUPT: hash mismatch at sequence %d", record.Sequence)
		}
		records = append(records, record)
		previousHash = record.Hash
	}
	return records, nil
}

func rebuildBetCustodySnapshot(records []betCustodyJournalRecord) betCustodySnapshot {
	snapshot := newBetCustodySnapshot()
	for _, record := range records {
		applyBetCustodyDelta(&snapshot, record.Delta)
		snapshot.Sequence = record.Sequence
		snapshot.LastEventHash = record.Hash
	}
	return snapshot
}

func readBetCustodySnapshot(path string) (betCustodySnapshot, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return betCustodySnapshot{}, err
	}
	var snapshot betCustodySnapshot
	if err := json.Unmarshal(data, &snapshot); err != nil {
		return betCustodySnapshot{}, err
	}
	if snapshot.Version != betCustodyStateVersion {
		return betCustodySnapshot{}, fmt.Errorf("unsupported custody snapshot version %d", snapshot.Version)
	}
	expected, err := betCustodySnapshotHash(snapshot)
	if err != nil {
		return betCustodySnapshot{}, err
	}
	if !strings.EqualFold(expected, snapshot.StateHash) {
		return betCustodySnapshot{}, errors.New("custody snapshot integrity hash mismatch")
	}
	if snapshot.Accounts == nil || snapshot.DepositIntents == nil || snapshot.DepositTxs == nil ||
		snapshot.Reservations == nil || snapshot.SettlementRuns == nil || snapshot.Withdrawals == nil || snapshot.Idempotency == nil {
		return betCustodySnapshot{}, errors.New("custody snapshot is missing required maps")
	}
	return snapshot, nil
}

func (cfg settlementConfig) loadBetCustodyState() (betCustodyLoadedState, error) {
	records, err := readBetCustodyJournal(cfg.betCustodyJournalPath())
	if err != nil {
		return betCustodyLoadedState{}, err
	}
	journalSnapshot := rebuildBetCustodySnapshot(records)
	snapshot, snapshotErr := readBetCustodySnapshot(cfg.betCustodySnapshotPath())
	if errors.Is(snapshotErr, os.ErrNotExist) {
		if len(records) > 0 {
			if err := writeBetCustodySnapshot(cfg.betCustodySnapshotPath(), journalSnapshot); err != nil {
				return betCustodyLoadedState{}, err
			}
			return betCustodyLoadedState{Snapshot: journalSnapshot, Recovered: true}, nil
		}
		return betCustodyLoadedState{Snapshot: journalSnapshot}, nil
	}
	if snapshotErr != nil {
		return betCustodyLoadedState{}, fmt.Errorf("CUSTODY_SNAPSHOT_CORRUPT: %w", snapshotErr)
	}

	if snapshot.Sequence == journalSnapshot.Sequence && snapshot.LastEventHash == journalSnapshot.LastEventHash {
		return betCustodyLoadedState{Snapshot: snapshot}, nil
	}
	if snapshot.Sequence < journalSnapshot.Sequence {
		if err := writeBetCustodySnapshot(cfg.betCustodySnapshotPath(), journalSnapshot); err != nil {
			return betCustodyLoadedState{}, err
		}
		return betCustodyLoadedState{Snapshot: journalSnapshot, Recovered: true}, nil
	}
	return betCustodyLoadedState{}, errors.New("CUSTODY_STATE_DIVERGED: snapshot is ahead of or inconsistent with journal")
}

func (cfg settlementConfig) commitBetCustodyMutation(
	snapshot *betCustodySnapshot,
	operationID string,
	operationType string,
	entries []betCustodyLedgerEntry,
	delta betCustodyStateDelta,
) error {
	record := betCustodyJournalRecord{
		Version:       betCustodyJournalVersion,
		Sequence:      snapshot.Sequence + 1,
		OperationID:   strings.TrimSpace(operationID),
		OperationType: strings.TrimSpace(operationType),
		Entries:       entries,
		Delta:         delta,
		CreatedAt:     time.Now().UTC(),
		PreviousHash:  snapshot.LastEventHash,
	}
	hash, err := betCustodyJournalHash(record)
	if err != nil {
		return err
	}
	record.Hash = hash
	if err := appendBetCustodyJournalRecord(cfg.betCustodyJournalPath(), record); err != nil {
		return err
	}
	applyBetCustodyDelta(snapshot, delta)
	snapshot.Sequence = record.Sequence
	snapshot.LastEventHash = record.Hash
	return writeBetCustodySnapshot(cfg.betCustodySnapshotPath(), *snapshot)
}

func canonicalBetCustodyDepositMemo(accountID, depositID string, amountUWolo uint64) string {
	return fmt.Sprintf(
		"%sapp=aoe2hdbets&acct=%s&dep=%s&amt=%d",
		betCustodyDepositMemoPrefix,
		url.QueryEscape(accountID),
		url.QueryEscape(depositID),
		amountUWolo,
	)
}

func validateCanonicalBetCustodyDepositMemo(memo, accountID, depositID string, amountUWolo uint64) error {
	expected := canonicalBetCustodyDepositMemo(accountID, depositID, amountUWolo)
	if strings.TrimSpace(memo) != expected {
		return fmt.Errorf("deposit memo mismatch: expected %q", expected)
	}
	values, err := url.ParseQuery(strings.TrimPrefix(expected, betCustodyDepositMemoPrefix))
	if err != nil {
		return err
	}
	if len(values) != 4 || values.Get("app") != "aoe2hdbets" ||
		values.Get("acct") != accountID || values.Get("dep") != depositID ||
		values.Get("amt") != strconv.FormatUint(amountUWolo, 10) {
		return errors.New("deposit memo is not canonical")
	}
	return nil
}

func normalizeBetCustodyAccountKind(kind string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "", betCustodyAccountKindUser:
		return betCustodyAccountKindUser, nil
	case betCustodyAccountKindOperator:
		return betCustodyAccountKindOperator, nil
	default:
		return "", errors.New("account kind must be user or operator")
	}
}

func validateBetCustodyOpaqueID(field, value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", fmt.Errorf("%s is required", field)
	}
	if len(value) > 128 || !settlementRequestIDPattern.MatchString(value) {
		return "", fmt.Errorf("%s uses unsupported characters", field)
	}
	return value, nil
}

func cloneBetCustodyReservation(value betCustodyReservation) betCustodyReservation {
	out := value
	out.Legs = append([]betCustodyReservationLeg(nil), value.Legs...)
	return out
}

func sumBetCustodyReservationLegs(legs []betCustodyReservationLeg) (uint64, error) {
	var total uint64
	seen := map[string]bool{}
	for _, leg := range legs {
		if _, err := validateBetCustodyOpaqueID("leg_id", leg.ID); err != nil {
			return 0, err
		}
		if seen[leg.ID] {
			return 0, fmt.Errorf("duplicate leg_id %q", leg.ID)
		}
		seen[leg.ID] = true
		if strings.TrimSpace(leg.MarketID) == "" || strings.TrimSpace(leg.MarketType) == "" || strings.TrimSpace(leg.Side) == "" {
			return 0, errors.New("each reservation leg requires market_id, market_type, and side")
		}
		if leg.AmountUWolo == 0 {
			return 0, errors.New("reservation leg amount_uwolo must be positive")
		}
		if ^uint64(0)-total < leg.AmountUWolo {
			return 0, errors.New("reservation amount overflow")
		}
		total += leg.AmountUWolo
	}
	if len(legs) == 0 {
		return 0, errors.New("at least one reservation leg is required")
	}
	return total, nil
}

func recomputeBetCustodyReservationStatus(reservation *betCustodyReservation) {
	reserved := 0
	released := 0
	settled := 0
	for _, leg := range reservation.Legs {
		switch leg.Status {
		case betCustodyReservationLegStatusReserved:
			reserved++
		case betCustodyReservationLegStatusReleased:
			released++
		case betCustodyReservationLegStatusSettled:
			settled++
		}
	}
	switch {
	case reserved == len(reservation.Legs):
		reservation.Status = betCustodyReservationStatusReserved
	case released == len(reservation.Legs):
		reservation.Status = betCustodyReservationStatusReleased
	case settled == len(reservation.Legs):
		reservation.Status = betCustodyReservationStatusSettled
	default:
		reservation.Status = betCustodyReservationStatusPartial
	}
}

func sortedBetCustodyAccounts(accounts map[string]betCustodyAccount) []betCustodyAccount {
	out := make([]betCustodyAccount, 0, len(accounts))
	for _, account := range accounts {
		out = append(out, account)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}

type betCustodyAccountRequest struct {
	RequestID string `json:"request_id"`
	Kind      string `json:"kind,omitempty"`
}

type betCustodyAccountResponse struct {
	OK               bool   `json:"ok"`
	FailureCode      string `json:"failure_code,omitempty"`
	Detail           string `json:"detail,omitempty"`
	IdempotentReplay bool   `json:"idempotent_replay"`
	AccountID        string `json:"account_id,omitempty"`
	Kind             string `json:"kind,omitempty"`
	SourceWallet     string `json:"source_wallet,omitempty"`
	AvailableUWolo   string `json:"available_uwolo,omitempty"`
	ReservedUWolo    string `json:"reserved_uwolo,omitempty"`
}

type betCustodyDepositIntentRequest struct {
	RequestID   string `json:"request_id"`
	DepositID   string `json:"deposit_id,omitempty"`
	AccountID   string `json:"account_id"`
	Sender      string `json:"sender"`
	AmountUWolo string `json:"amount_uwolo"`
}

type betCustodyDepositIntentResponse struct {
	OK               bool   `json:"ok"`
	FailureCode      string `json:"failure_code,omitempty"`
	Detail           string `json:"detail,omitempty"`
	IdempotentReplay bool   `json:"idempotent_replay"`
	DepositID        string `json:"deposit_id,omitempty"`
	AccountID        string `json:"account_id,omitempty"`
	Sender           string `json:"sender,omitempty"`
	Recipient        string `json:"recipient,omitempty"`
	AmountUWolo      string `json:"amount_uwolo,omitempty"`
	Memo             string `json:"memo,omitempty"`
	Status           string `json:"status,omitempty"`
}

type betCustodyDepositCreditRequest struct {
	DepositID string `json:"deposit_id"`
	TxHash    string `json:"tx_hash"`
}

type betCustodyDepositCreditResponse struct {
	OK               bool                      `json:"ok"`
	FailureCode      string                    `json:"failure_code,omitempty"`
	Detail           string                    `json:"detail,omitempty"`
	IdempotentReplay bool                      `json:"idempotent_replay"`
	DepositID        string                    `json:"deposit_id,omitempty"`
	AccountID        string                    `json:"account_id,omitempty"`
	TxHash           string                    `json:"tx_hash,omitempty"`
	AmountUWolo      string                    `json:"amount_uwolo,omitempty"`
	AvailableUWolo   string                    `json:"available_uwolo,omitempty"`
	Lookup           *settlementLookupResponse `json:"lookup,omitempty"`
}

type betCustodyReservationLegRequest struct {
	ID          string `json:"id"`
	MarketID    string `json:"market_id"`
	MarketType  string `json:"market_type"`
	Side        string `json:"side"`
	AmountUWolo string `json:"amount_uwolo"`
}

type betCustodyReservationRequest struct {
	RequestID       string                            `json:"request_id"`
	ReservationID   string                            `json:"reservation_id,omitempty"`
	AccountID       string                            `json:"account_id"`
	GameIdentity    string                            `json:"game_identity"`
	PropositionHash string                            `json:"proposition_hash"`
	Legs            []betCustodyReservationLegRequest `json:"legs"`
}

type betCustodyReservationResponse struct {
	OK               bool                       `json:"ok"`
	FailureCode      string                     `json:"failure_code,omitempty"`
	Detail           string                     `json:"detail,omitempty"`
	IdempotentReplay bool                       `json:"idempotent_replay"`
	ReservationID    string                     `json:"reservation_id,omitempty"`
	AccountID        string                     `json:"account_id,omitempty"`
	Status           string                     `json:"status,omitempty"`
	ReservedUWolo    string                     `json:"reserved_uwolo,omitempty"`
	AvailableUWolo   string                     `json:"available_uwolo,omitempty"`
	Reservation      *betCustodyReservationView `json:"reservation,omitempty"`
}

type betCustodyReleaseRequest struct {
	RequestID     string `json:"request_id"`
	ReservationID string `json:"reservation_id"`
	LegID         string `json:"leg_id"`
}

func betCustodyFailureAccount(code, detail string) betCustodyAccountResponse {
	return betCustodyAccountResponse{OK: false, FailureCode: code, Detail: detail}
}

func betCustodyAccountResponseFrom(account betCustodyAccount) betCustodyAccountResponse {
	return betCustodyAccountResponse{
		OK:             true,
		AccountID:      account.ID,
		Kind:           account.Kind,
		SourceWallet:   account.SourceWallet,
		AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10),
		ReservedUWolo:  strconv.FormatUint(account.ReservedUWolo, 10),
	}
}

func (cfg settlementConfig) ensureBetCustodyConfigured() error {
	if strings.TrimSpace(cfg.BetCustodyKeyName) == "" {
		return errors.New("WOLO_SETTLEMENT_BET_CUSTODY_KEY_NAME is not configured")
	}
	if !isWoloAddress(cfg.BetCustodyAddress, cfg.AddressPrefix) {
		return errors.New("WOLO_SETTLEMENT_BET_CUSTODY_ADDRESS is not a valid configured WOLO address")
	}
	if strings.TrimSpace(cfg.BetCustodyStateDir) == "" {
		return errors.New("WOLO_SETTLEMENT_BET_CUSTODY_STATE_DIR is not configured")
	}
	return nil
}

func (cfg settlementConfig) createBetCustodyAccount(request betCustodyAccountRequest) (betCustodyAccountResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyFailureAccount("CUSTODY_UNCONFIGURED", err.Error()), nil
	}
	requestID, err := validateBetCustodyOpaqueID("request_id", request.RequestID)
	if err != nil {
		return betCustodyFailureAccount("INVALID_REQUEST", err.Error()), nil
	}
	kind, err := normalizeBetCustodyAccountKind(request.Kind)
	if err != nil {
		return betCustodyFailureAccount("INVALID_REQUEST", err.Error()), nil
	}
	fingerprint, err := betCustodyHashValue(struct {
		RequestID string `json:"request_id"`
		Kind      string `json:"kind"`
	}{requestID, kind})
	if err != nil {
		return betCustodyAccountResponse{}, err
	}

	var response betCustodyAccountResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		idemKey := betCustodyIdempotencyKey("account", requestID)
		if existing, ok := snapshot.Idempotency[idemKey]; ok {
			if existing.Fingerprint != fingerprint {
				response = betCustodyFailureAccount("IDEMPOTENCY_CONFLICT", "request_id already exists with different account payload")
				return nil
			}
			account, ok := snapshot.Accounts[existing.ResourceID]
			if !ok {
				return errors.New("CUSTODY_STATE_DIVERGED: account idempotency points to missing account")
			}
			response = betCustodyAccountResponseFrom(account)
			response.IdempotentReplay = true
			return nil
		}

		accountID, err := betCustodyRandomID("betacct_")
		if err != nil {
			return err
		}
		now := time.Now().UTC()
		account := betCustodyAccount{
			ID:        accountID,
			Kind:      kind,
			CreatedAt: now,
			UpdatedAt: now,
		}
		delta := betCustodyStateDelta{
			AccountUpserts: []betCustodyAccount{account},
			IdempotencyUpserts: []betCustodyIdempotencyRecord{{
				Scope:       "account",
				Key:         requestID,
				Fingerprint: fingerprint,
				ResourceID:  accountID,
			}},
		}
		if err := cfg.commitBetCustodyMutation(
			&snapshot,
			"account:"+requestID,
			"account_opened",
			[]betCustodyLedgerEntry{{AccountID: accountID, EntryType: "account_opened"}},
			delta,
		); err != nil {
			return err
		}
		response = betCustodyAccountResponseFrom(account)
		response.Detail = "bet custody account opened; source wallet binds on first verified deposit"
		return nil
	})
	return response, err
}

func parsePositiveBetCustodyAmount(field, raw string) (uint64, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" || raw[0] < '1' || raw[0] > '9' {
		return 0, fmt.Errorf("%s must be a canonical positive uwolo integer", field)
	}
	for index := 1; index < len(raw); index++ {
		if raw[index] < '0' || raw[index] > '9' {
			return 0, fmt.Errorf("%s must be a canonical positive uwolo integer", field)
		}
	}
	value, err := strconv.ParseUint(raw, 10, 64)
	if err != nil || value == 0 {
		return 0, fmt.Errorf("%s must be a canonical positive uwolo integer", field)
	}
	return value, nil
}

func (cfg settlementConfig) createBetCustodyDepositIntent(request betCustodyDepositIntentRequest) (betCustodyDepositIntentResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyDepositIntentResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	requestID, err := validateBetCustodyOpaqueID("request_id", request.RequestID)
	if err != nil {
		return betCustodyDepositIntentResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	accountID, err := validateBetCustodyOpaqueID("account_id", request.AccountID)
	if err != nil {
		return betCustodyDepositIntentResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	sender := strings.TrimSpace(request.Sender)
	if !isWoloAddress(sender, cfg.AddressPrefix) {
		return betCustodyDepositIntentResponse{FailureCode: "INVALID_ADDRESS", Detail: "sender must be a valid WOLO address"}, nil
	}
	amount, err := parsePositiveBetCustodyAmount("amount_uwolo", request.AmountUWolo)
	if err != nil {
		return betCustodyDepositIntentResponse{FailureCode: "INVALID_AMOUNT", Detail: err.Error()}, nil
	}
	depositID := strings.TrimSpace(request.DepositID)
	if depositID == "" {
		depositID, err = betCustodyRandomID("betdep_")
		if err != nil {
			return betCustodyDepositIntentResponse{}, err
		}
	} else if depositID, err = validateBetCustodyOpaqueID("deposit_id", depositID); err != nil {
		return betCustodyDepositIntentResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}

	normalized := struct {
		RequestID string `json:"request_id"`
		DepositID string `json:"deposit_id"`
		AccountID string `json:"account_id"`
		Sender    string `json:"sender"`
		Amount    uint64 `json:"amount_uwolo"`
	}{requestID, depositID, accountID, sender, amount}
	fingerprint, err := betCustodyHashValue(normalized)
	if err != nil {
		return betCustodyDepositIntentResponse{}, err
	}

	var response betCustodyDepositIntentResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		idemKey := betCustodyIdempotencyKey("deposit_intent", requestID)
		if existing, ok := snapshot.Idempotency[idemKey]; ok {
			if existing.Fingerprint != fingerprint {
				response = betCustodyDepositIntentResponse{FailureCode: "IDEMPOTENCY_CONFLICT", Detail: "request_id already exists with different deposit intent"}
				return nil
			}
			intent, ok := snapshot.DepositIntents[existing.ResourceID]
			if !ok {
				return errors.New("CUSTODY_STATE_DIVERGED: deposit idempotency points to missing intent")
			}
			response = betCustodyDepositIntentResponse{
				OK: true, IdempotentReplay: true, DepositID: intent.ID, AccountID: intent.AccountID,
				Sender: intent.Sender, Recipient: cfg.BetCustodyAddress, AmountUWolo: strconv.FormatUint(intent.AmountUWolo, 10),
				Memo: intent.Memo, Status: intent.Status,
			}
			return nil
		}
		account, ok := snapshot.Accounts[accountID]
		if !ok {
			response = betCustodyDepositIntentResponse{FailureCode: "ACCOUNT_NOT_FOUND", Detail: "bet custody account was not found"}
			return nil
		}
		if account.SourceWallet != "" && !strings.EqualFold(account.SourceWallet, sender) {
			response = betCustodyDepositIntentResponse{FailureCode: "SOURCE_WALLET_MISMATCH", Detail: "deposit sender does not match the account source wallet"}
			return nil
		}
		if account.Kind == betCustodyAccountKindUser {
			current := account.AvailableUWolo + account.ReservedUWolo
			if current > cfg.BetCustodyMaxBalanceUWolo || amount > cfg.BetCustodyMaxBalanceUWolo-current {
				response = betCustodyDepositIntentResponse{
					FailureCode: "ACCOUNT_BALANCE_CAP_EXCEEDED",
					Detail:      fmt.Sprintf("credited user balance may not exceed %d uwolo", cfg.BetCustodyMaxBalanceUWolo),
				}
				return nil
			}
		}
		if _, exists := snapshot.DepositIntents[depositID]; exists {
			response = betCustodyDepositIntentResponse{FailureCode: "DEPOSIT_ID_CONFLICT", Detail: "deposit_id already exists"}
			return nil
		}

		now := time.Now().UTC()
		intent := betCustodyDepositIntent{
			ID: depositID, AccountID: accountID, Sender: sender, AmountUWolo: amount,
			Memo: canonicalBetCustodyDepositMemo(accountID, depositID, amount), Status: "pending", CreatedAt: now,
		}
		delta := betCustodyStateDelta{
			DepositIntentUpserts: []betCustodyDepositIntent{intent},
			IdempotencyUpserts: []betCustodyIdempotencyRecord{{
				Scope: "deposit_intent", Key: requestID, Fingerprint: fingerprint, ResourceID: depositID,
			}},
		}
		if err := cfg.commitBetCustodyMutation(&snapshot, "deposit_intent:"+requestID, "deposit_intent_created", nil, delta); err != nil {
			return err
		}
		response = betCustodyDepositIntentResponse{
			OK: true, Detail: "deposit intent created", DepositID: depositID, AccountID: accountID,
			Sender: sender, Recipient: cfg.BetCustodyAddress, AmountUWolo: strconv.FormatUint(amount, 10),
			Memo: intent.Memo, Status: intent.Status,
		}
		return nil
	})
	return response, err
}

func (cfg settlementConfig) creditBetCustodyDeposit(ctx context.Context, request betCustodyDepositCreditRequest) (betCustodyDepositCreditResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyDepositCreditResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	depositID, err := validateBetCustodyOpaqueID("deposit_id", request.DepositID)
	if err != nil {
		return betCustodyDepositCreditResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	txHash := normalizeTxHash(request.TxHash)
	if txHash == "" || !isHexHash(txHash) {
		return betCustodyDepositCreditResponse{FailureCode: "INVALID_TX_HASH", Detail: "tx_hash must be hex"}, nil
	}

	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyDepositCreditResponse{}, err
	}
	intent, ok := loaded.Snapshot.DepositIntents[depositID]
	if !ok {
		return betCustodyDepositCreditResponse{FailureCode: "DEPOSIT_NOT_FOUND", Detail: "deposit intent was not found"}, nil
	}
	if intent.Status == "credited" {
		if strings.EqualFold(intent.TxHash, txHash) {
			account := loaded.Snapshot.Accounts[intent.AccountID]
			return betCustodyDepositCreditResponse{
				OK: true, IdempotentReplay: true, Detail: "deposit was already credited",
				DepositID: intent.ID, AccountID: intent.AccountID, TxHash: intent.TxHash,
				AmountUWolo:    strconv.FormatUint(intent.AmountUWolo, 10),
				AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10),
			}, nil
		}
		return betCustodyDepositCreditResponse{FailureCode: "DEPOSIT_ALREADY_CREDITED", Detail: "deposit intent is already bound to another tx"}, nil
	}

	lookup, err := cfg.lookupSettlementTx(ctx, txHash, settlementLookupExpectations{
		Sender: intent.Sender, Recipient: cfg.BetCustodyAddress, AmountUWolo: strconv.FormatUint(intent.AmountUWolo, 10),
	})
	if err != nil {
		return betCustodyDepositCreditResponse{}, err
	}
	if !lookup.OK || !lookup.Found {
		return betCustodyDepositCreditResponse{
			FailureCode: firstNonEmpty(lookup.FailureCode, "TX_NOT_FOUND"), Detail: lookup.Detail, Lookup: &lookup,
		}, nil
	}
	if !lookup.TxSuccess {
		return betCustodyDepositCreditResponse{FailureCode: "TX_FAILED", Detail: "deposit transaction was not successful", Lookup: &lookup}, nil
	}
	if lookup.MatchedTransfer == nil || lookup.MatchedTransfer.Denom != cfg.BaseDenom {
		return betCustodyDepositCreditResponse{FailureCode: "DEPOSIT_TRANSFER_MISMATCH", Detail: "transaction does not contain the exact expected uwolo custody transfer", Lookup: &lookup}, nil
	}
	if err := validateCanonicalBetCustodyDepositMemo(lookup.Memo, intent.AccountID, intent.ID, intent.AmountUWolo); err != nil {
		return betCustodyDepositCreditResponse{FailureCode: "INVALID_DEPOSIT_MEMO", Detail: err.Error(), Lookup: &lookup}, nil
	}

	var response betCustodyDepositCreditResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		currentIntent, ok := snapshot.DepositIntents[depositID]
		if !ok {
			response = betCustodyDepositCreditResponse{FailureCode: "DEPOSIT_NOT_FOUND", Detail: "deposit intent disappeared before credit"}
			return nil
		}
		if currentIntent.Status == "credited" {
			if strings.EqualFold(currentIntent.TxHash, txHash) {
				account := snapshot.Accounts[currentIntent.AccountID]
				response = betCustodyDepositCreditResponse{
					OK: true, IdempotentReplay: true, Detail: "deposit was already credited",
					DepositID: currentIntent.ID, AccountID: currentIntent.AccountID, TxHash: currentIntent.TxHash,
					AmountUWolo:    strconv.FormatUint(currentIntent.AmountUWolo, 10),
					AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10), Lookup: &lookup,
				}
				return nil
			}
			response = betCustodyDepositCreditResponse{FailureCode: "DEPOSIT_ALREADY_CREDITED", Detail: "deposit intent is already bound to another tx"}
			return nil
		}
		if boundIntent, exists := snapshot.DepositTxs[txHash]; exists && boundIntent != depositID {
			response = betCustodyDepositCreditResponse{FailureCode: "TX_ALREADY_CREDITED", Detail: "transaction hash has already credited another deposit"}
			return nil
		}
		account, ok := snapshot.Accounts[currentIntent.AccountID]
		if !ok {
			return errors.New("CUSTODY_STATE_DIVERGED: deposit account is missing")
		}
		if account.SourceWallet != "" && !strings.EqualFold(account.SourceWallet, currentIntent.Sender) {
			response = betCustodyDepositCreditResponse{FailureCode: "SOURCE_WALLET_MISMATCH", Detail: "verified sender does not match bound source wallet"}
			return nil
		}
		if account.Kind == betCustodyAccountKindUser {
			current := account.AvailableUWolo + account.ReservedUWolo
			if current > cfg.BetCustodyMaxBalanceUWolo || currentIntent.AmountUWolo > cfg.BetCustodyMaxBalanceUWolo-current {
				response = betCustodyDepositCreditResponse{FailureCode: "ACCOUNT_BALANCE_CAP_EXCEEDED", Detail: "credit would exceed the user custody balance cap"}
				return nil
			}
		}

		now := time.Now().UTC()
		account.SourceWallet = currentIntent.Sender
		account.AvailableUWolo += currentIntent.AmountUWolo
		account.DepositedUWolo += currentIntent.AmountUWolo
		account.UpdatedAt = now
		currentIntent.Status = "credited"
		currentIntent.TxHash = txHash
		currentIntent.CreditedAt = &now
		delta := betCustodyStateDelta{
			AccountUpserts:       []betCustodyAccount{account},
			DepositIntentUpserts: []betCustodyDepositIntent{currentIntent},
			DepositTxBindings:    map[string]string{txHash: currentIntent.ID},
		}
		entries := []betCustodyLedgerEntry{{
			AccountID: account.ID, EntryType: "deposit_credit", AmountUWolo: currentIntent.AmountUWolo,
			DepositIntentID: currentIntent.ID, TxHash: txHash, Detail: "verified prefunded betting deposit credited",
		}}
		if err := cfg.commitBetCustodyMutation(&snapshot, "deposit_credit:"+txHash, "deposit_credited", entries, delta); err != nil {
			return err
		}
		response = betCustodyDepositCreditResponse{
			OK: true, Detail: "deposit credited", DepositID: currentIntent.ID, AccountID: account.ID, TxHash: txHash,
			AmountUWolo:    strconv.FormatUint(currentIntent.AmountUWolo, 10),
			AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10), Lookup: &lookup,
		}
		return nil
	})
	return response, err
}

func normalizeBetCustodyReservationRequest(request betCustodyReservationRequest) (betCustodyReservation, string, error) {
	requestID, err := validateBetCustodyOpaqueID("request_id", request.RequestID)
	if err != nil {
		return betCustodyReservation{}, "", err
	}
	accountID, err := validateBetCustodyOpaqueID("account_id", request.AccountID)
	if err != nil {
		return betCustodyReservation{}, "", err
	}
	gameIdentity, err := validateBetCustodyOpaqueID("game_identity", request.GameIdentity)
	if err != nil {
		return betCustodyReservation{}, "", err
	}
	propositionHash := strings.TrimSpace(request.PropositionHash)
	if propositionHash == "" || len(propositionHash) > 128 {
		return betCustodyReservation{}, "", errors.New("proposition_hash is required and must be at most 128 characters")
	}
	if len(request.Legs) < 1 || len(request.Legs) > 2 {
		return betCustodyReservation{}, "", errors.New("reservation requires one winner leg and at most one optional secondary leg")
	}
	reservationID := strings.TrimSpace(request.ReservationID)
	if reservationID == "" {
		reservationID, err = betCustodyRandomID("betres_")
		if err != nil {
			return betCustodyReservation{}, "", err
		}
	} else if reservationID, err = validateBetCustodyOpaqueID("reservation_id", reservationID); err != nil {
		return betCustodyReservation{}, "", err
	}
	legs := make([]betCustodyReservationLeg, 0, len(request.Legs))
	for _, raw := range request.Legs {
		amount, err := parsePositiveBetCustodyAmount("leg amount_uwolo", raw.AmountUWolo)
		if err != nil {
			return betCustodyReservation{}, "", err
		}
		legID, err := validateBetCustodyOpaqueID("leg_id", raw.ID)
		if err != nil {
			return betCustodyReservation{}, "", err
		}
		marketID, err := validateBetCustodyOpaqueID("market_id", raw.MarketID)
		if err != nil {
			return betCustodyReservation{}, "", err
		}
		legs = append(legs, betCustodyReservationLeg{
			ID: legID, MarketID: marketID, MarketType: strings.TrimSpace(raw.MarketType),
			Side: strings.TrimSpace(raw.Side), AmountUWolo: amount, Status: betCustodyReservationLegStatusReserved,
		})
	}
	if _, err := sumBetCustodyReservationLegs(legs); err != nil {
		return betCustodyReservation{}, "", err
	}
	reservation := betCustodyReservation{
		ID: reservationID, RequestID: requestID, AccountID: accountID, GameIdentity: gameIdentity,
		PropositionHash: propositionHash, Legs: legs, Status: betCustodyReservationStatusReserved,
	}
	fingerprint, err := betCustodyHashValue(struct {
		RequestID       string                     `json:"request_id"`
		AccountID       string                     `json:"account_id"`
		GameIdentity    string                     `json:"game_identity"`
		PropositionHash string                     `json:"proposition_hash"`
		Legs            []betCustodyReservationLeg `json:"legs"`
	}{requestID, accountID, gameIdentity, propositionHash, legs})
	if err != nil {
		return betCustodyReservation{}, "", err
	}
	reservation.RequestFingerprint = fingerprint
	return reservation, fingerprint, nil
}

func (cfg settlementConfig) createBetCustodyReservation(request betCustodyReservationRequest) (betCustodyReservationResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyReservationResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	reservation, fingerprint, err := normalizeBetCustodyReservationRequest(request)
	if err != nil {
		return betCustodyReservationResponse{FailureCode: "INVALID_RESERVATION", Detail: err.Error()}, nil
	}
	total, _ := sumBetCustodyReservationLegs(reservation.Legs)
	var response betCustodyReservationResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		idemKey := betCustodyIdempotencyKey("reservation", reservation.RequestID)
		if existing, ok := snapshot.Idempotency[idemKey]; ok {
			if existing.Fingerprint != fingerprint {
				response = betCustodyReservationResponse{FailureCode: "IDEMPOTENCY_CONFLICT", Detail: "request_id already exists with different reservation payload"}
				return nil
			}
			stored, ok := snapshot.Reservations[existing.ResourceID]
			if !ok {
				return errors.New("CUSTODY_STATE_DIVERGED: reservation idempotency points to missing reservation")
			}
			account := snapshot.Accounts[stored.AccountID]
			copy := cloneBetCustodyReservation(stored)
			view := betCustodyReservationViewFrom(copy)
			response = betCustodyReservationResponse{
				OK: true, IdempotentReplay: true, ReservationID: stored.ID, AccountID: stored.AccountID, Status: stored.Status,
				ReservedUWolo:  strconv.FormatUint(account.ReservedUWolo, 10),
				AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10), Reservation: &view,
			}
			return nil
		}
		if _, exists := snapshot.Reservations[reservation.ID]; exists {
			response = betCustodyReservationResponse{FailureCode: "RESERVATION_ID_CONFLICT", Detail: "reservation_id already exists"}
			return nil
		}
		account, ok := snapshot.Accounts[reservation.AccountID]
		if !ok {
			response = betCustodyReservationResponse{FailureCode: "ACCOUNT_NOT_FOUND", Detail: "bet custody account was not found"}
			return nil
		}
		if account.AvailableUWolo < total {
			response = betCustodyReservationResponse{FailureCode: "INSUFFICIENT_AVAILABLE_BALANCE", Detail: "account does not have enough available custody balance"}
			return nil
		}
		now := time.Now().UTC()
		account.AvailableUWolo -= total
		account.ReservedUWolo += total
		account.UpdatedAt = now
		reservation.CreatedAt = now
		reservation.UpdatedAt = now
		entries := make([]betCustodyLedgerEntry, 0, len(reservation.Legs))
		for _, leg := range reservation.Legs {
			entries = append(entries, betCustodyLedgerEntry{
				AccountID: account.ID, EntryType: "reservation_hold", AmountUWolo: leg.AmountUWolo,
				ReservationID: reservation.ID, LegID: leg.ID, Detail: "available moved to reserved",
			})
		}
		delta := betCustodyStateDelta{
			AccountUpserts:     []betCustodyAccount{account},
			ReservationUpserts: []betCustodyReservation{reservation},
			IdempotencyUpserts: []betCustodyIdempotencyRecord{{
				Scope: "reservation", Key: reservation.RequestID, Fingerprint: fingerprint, ResourceID: reservation.ID,
			}},
		}
		if err := cfg.commitBetCustodyMutation(&snapshot, "reservation:"+reservation.RequestID, "reservation_created", entries, delta); err != nil {
			return err
		}
		copy := cloneBetCustodyReservation(reservation)
		view := betCustodyReservationViewFrom(copy)
		response = betCustodyReservationResponse{
			OK: true, Detail: "reservation created", ReservationID: reservation.ID, AccountID: account.ID, Status: reservation.Status,
			ReservedUWolo:  strconv.FormatUint(account.ReservedUWolo, 10),
			AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10), Reservation: &view,
		}
		return nil
	})
	return response, err
}

func (cfg settlementConfig) releaseBetCustodyReservationLeg(request betCustodyReleaseRequest) (betCustodyReservationResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyReservationResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	requestID, err := validateBetCustodyOpaqueID("request_id", request.RequestID)
	if err != nil {
		return betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	reservationID, err := validateBetCustodyOpaqueID("reservation_id", request.ReservationID)
	if err != nil {
		return betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	legID, err := validateBetCustodyOpaqueID("leg_id", request.LegID)
	if err != nil {
		return betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	fingerprint, err := betCustodyHashValue(struct{ ReservationID, LegID string }{reservationID, legID})
	if err != nil {
		return betCustodyReservationResponse{}, err
	}

	var response betCustodyReservationResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		idemKey := betCustodyIdempotencyKey("release_leg", requestID)
		if existing, ok := snapshot.Idempotency[idemKey]; ok {
			if existing.Fingerprint != fingerprint {
				response = betCustodyReservationResponse{FailureCode: "IDEMPOTENCY_CONFLICT", Detail: "request_id already exists with different release payload"}
				return nil
			}
			stored := snapshot.Reservations[reservationID]
			account := snapshot.Accounts[stored.AccountID]
			copy := cloneBetCustodyReservation(stored)
			view := betCustodyReservationViewFrom(copy)
			response = betCustodyReservationResponse{
				OK: true, IdempotentReplay: true, ReservationID: stored.ID, AccountID: stored.AccountID, Status: stored.Status,
				ReservedUWolo: strconv.FormatUint(account.ReservedUWolo, 10), AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10),
				Reservation: &view,
			}
			return nil
		}
		reservation, ok := snapshot.Reservations[reservationID]
		if !ok {
			response = betCustodyReservationResponse{FailureCode: "RESERVATION_NOT_FOUND", Detail: "reservation was not found"}
			return nil
		}
		legIndex := -1
		for index := range reservation.Legs {
			if reservation.Legs[index].ID == legID {
				legIndex = index
				break
			}
		}
		if legIndex < 0 {
			response = betCustodyReservationResponse{FailureCode: "RESERVATION_LEG_NOT_FOUND", Detail: "reservation leg was not found"}
			return nil
		}
		leg := reservation.Legs[legIndex]
		if leg.Status == betCustodyReservationLegStatusSettled {
			response = betCustodyReservationResponse{FailureCode: "RESERVATION_LEG_SETTLED", Detail: "settled reservation leg cannot be released"}
			return nil
		}
		if leg.Status == betCustodyReservationLegStatusReleased {
			response = betCustodyReservationResponse{FailureCode: "RELEASE_ALREADY_RECORDED", Detail: "reservation leg was already released; use the original request_id for idempotent replay"}
			return nil
		}
		account, ok := snapshot.Accounts[reservation.AccountID]
		if !ok || account.ReservedUWolo < leg.AmountUWolo {
			return errors.New("CUSTODY_STATE_DIVERGED: reservation balance does not cover leg release")
		}
		now := time.Now().UTC()
		account.ReservedUWolo -= leg.AmountUWolo
		account.AvailableUWolo += leg.AmountUWolo
		account.UpdatedAt = now
		reservation.Legs[legIndex].Status = betCustodyReservationLegStatusReleased
		reservation.UpdatedAt = now
		recomputeBetCustodyReservationStatus(&reservation)
		delta := betCustodyStateDelta{
			AccountUpserts:     []betCustodyAccount{account},
			ReservationUpserts: []betCustodyReservation{reservation},
			IdempotencyUpserts: []betCustodyIdempotencyRecord{{
				Scope: "release_leg", Key: requestID, Fingerprint: fingerprint, ResourceID: reservation.ID,
			}},
		}
		entries := []betCustodyLedgerEntry{{
			AccountID: account.ID, EntryType: "reservation_release", AmountUWolo: leg.AmountUWolo,
			ReservationID: reservation.ID, LegID: leg.ID, Detail: "reserved returned to available",
		}}
		if err := cfg.commitBetCustodyMutation(&snapshot, "release_leg:"+requestID, "reservation_leg_released", entries, delta); err != nil {
			return err
		}
		copy := cloneBetCustodyReservation(reservation)
		view := betCustodyReservationViewFrom(copy)
		response = betCustodyReservationResponse{
			OK: true, Detail: "reservation leg released", ReservationID: reservation.ID, AccountID: account.ID, Status: reservation.Status,
			ReservedUWolo: strconv.FormatUint(account.ReservedUWolo, 10), AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10),
			Reservation: &view,
		}
		return nil
	})
	return response, err
}

type betCustodySettlementDebitRequest struct {
	ReservationID string `json:"reservation_id"`
	LegID         string `json:"leg_id"`
}

type betCustodySettlementCreditRequest struct {
	AccountID   string `json:"account_id"`
	AmountUWolo string `json:"amount_uwolo"`
	Kind        string `json:"kind"`
}

type betCustodyOperatorAllocationRequest struct {
	AccountID   string `json:"account_id"`
	AmountUWolo string `json:"amount_uwolo"`
}

type betCustodySettlementRunRequest struct {
	SettlementRunID     string                                `json:"settlement_run_id"`
	PropositionHash     string                                `json:"proposition_hash"`
	Debits              []betCustodySettlementDebitRequest    `json:"debits"`
	Credits             []betCustodySettlementCreditRequest   `json:"credits"`
	OperatorAllocations []betCustodyOperatorAllocationRequest `json:"operator_allocations,omitempty"`
}

type betCustodySettlementRunResponse struct {
	OK               bool                         `json:"ok"`
	DryRun           bool                         `json:"dry_run"`
	FailureCode      string                       `json:"failure_code,omitempty"`
	Detail           string                       `json:"detail,omitempty"`
	IdempotentReplay bool                         `json:"idempotent_replay"`
	SettlementRunID  string                       `json:"settlement_run_id,omitempty"`
	DebitedUWolo     string                       `json:"debited_uwolo,omitempty"`
	OperatorUWolo    string                       `json:"operator_uwolo,omitempty"`
	CreditedUWolo    string                       `json:"credited_uwolo,omitempty"`
	Run              *betCustodySettlementRunView `json:"run,omitempty"`
}

type betCustodyNormalizedSettlementRequest struct {
	SettlementRunID     string
	PropositionHash     string
	Debits              []betCustodySettlementDebitRequest
	Credits             []betCustodySettlementCredit
	OperatorAllocations []betCustodyOperatorAllocation
	Fingerprint         string
}

type betCustodyLiabilitiesResponse struct {
	OK                     bool   `json:"ok"`
	FailureCode            string `json:"failure_code,omitempty"`
	Detail                 string `json:"detail,omitempty"`
	Sequence               uint64 `json:"sequence"`
	UserAvailableUWolo     string `json:"user_available_uwolo"`
	UserReservedUWolo      string `json:"user_reserved_uwolo"`
	UserLiabilityUWolo     string `json:"user_liability_uwolo"`
	OperatorAvailableUWolo string `json:"operator_available_uwolo"`
	OperatorReservedUWolo  string `json:"operator_reserved_uwolo"`
	OperatorCapitalUWolo   string `json:"operator_capital_uwolo"`
	TotalLedgerUWolo       string `json:"total_ledger_uwolo"`
	AccountCount           int    `json:"account_count"`
}

type betCustodyReconcileResponse struct {
	OK                  bool   `json:"ok"`
	FailureCode         string `json:"failure_code,omitempty"`
	Detail              string `json:"detail,omitempty"`
	LedgerTotalUWolo    string `json:"ledger_total_uwolo,omitempty"`
	OnChainBalanceUWolo string `json:"on_chain_balance_uwolo,omitempty"`
	UnallocatedUWolo    string `json:"unallocated_uwolo,omitempty"`
	ShortfallUWolo      string `json:"shortfall_uwolo,omitempty"`
	CustodyAddress      string `json:"custody_address,omitempty"`
	Sequence            uint64 `json:"sequence"`
}

type betCustodyLedgerResponse struct {
	OK          bool                     `json:"ok"`
	FailureCode string                   `json:"failure_code,omitempty"`
	Detail      string                   `json:"detail,omitempty"`
	AccountID   string                   `json:"account_id,omitempty"`
	Count       int                      `json:"count"`
	Entries     []betCustodyLedgerRecord `json:"entries,omitempty"`
}

type betCustodyLedgerRecord struct {
	Sequence      uint64                    `json:"sequence"`
	OperationID   string                    `json:"operation_id"`
	OperationType string                    `json:"operation_type"`
	CreatedAt     time.Time                 `json:"created_at"`
	Entry         betCustodyLedgerEntryView `json:"entry"`
}

func normalizeBetCustodySettlementRequest(request betCustodySettlementRunRequest) (betCustodyNormalizedSettlementRequest, error) {
	runID, err := validateBetCustodyOpaqueID("settlement_run_id", request.SettlementRunID)
	if err != nil {
		return betCustodyNormalizedSettlementRequest{}, err
	}
	propositionHash := strings.TrimSpace(request.PropositionHash)
	if propositionHash == "" || len(propositionHash) > 128 {
		return betCustodyNormalizedSettlementRequest{}, errors.New("proposition_hash is required and must be at most 128 characters")
	}
	if len(request.Debits) == 0 {
		return betCustodyNormalizedSettlementRequest{}, errors.New("settlement run requires at least one reservation debit")
	}
	if len(request.Credits) == 0 {
		return betCustodyNormalizedSettlementRequest{}, errors.New("settlement run requires at least one account credit")
	}

	debits := make([]betCustodySettlementDebitRequest, 0, len(request.Debits))
	seenDebits := map[string]bool{}
	for _, raw := range request.Debits {
		reservationID, err := validateBetCustodyOpaqueID("reservation_id", raw.ReservationID)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		legID, err := validateBetCustodyOpaqueID("leg_id", raw.LegID)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		key := reservationID + ":" + legID
		if seenDebits[key] {
			return betCustodyNormalizedSettlementRequest{}, fmt.Errorf("duplicate settlement debit %s", key)
		}
		seenDebits[key] = true
		debits = append(debits, betCustodySettlementDebitRequest{ReservationID: reservationID, LegID: legID})
	}

	credits := make([]betCustodySettlementCredit, 0, len(request.Credits))
	for _, raw := range request.Credits {
		accountID, err := validateBetCustodyOpaqueID("credit account_id", raw.AccountID)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		amount, err := parsePositiveBetCustodyAmount("credit amount_uwolo", raw.AmountUWolo)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		kind := strings.TrimSpace(raw.Kind)
		if kind == "" {
			kind = "settlement"
		}
		if len(kind) > 64 || !settlementRequestIDPattern.MatchString(kind) {
			return betCustodyNormalizedSettlementRequest{}, errors.New("credit kind uses unsupported characters")
		}
		credits = append(credits, betCustodySettlementCredit{AccountID: accountID, AmountUWolo: amount, Kind: kind})
	}

	allocations := make([]betCustodyOperatorAllocation, 0, len(request.OperatorAllocations))
	for _, raw := range request.OperatorAllocations {
		accountID, err := validateBetCustodyOpaqueID("operator account_id", raw.AccountID)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		amount, err := parsePositiveBetCustodyAmount("operator amount_uwolo", raw.AmountUWolo)
		if err != nil {
			return betCustodyNormalizedSettlementRequest{}, err
		}
		allocations = append(allocations, betCustodyOperatorAllocation{AccountID: accountID, AmountUWolo: amount})
	}

	normalized := betCustodyNormalizedSettlementRequest{
		SettlementRunID:     runID,
		PropositionHash:     propositionHash,
		Debits:              debits,
		Credits:             credits,
		OperatorAllocations: allocations,
	}
	fingerprint, err := betCustodyHashValue(struct {
		ID          string                             `json:"id"`
		Proposition string                             `json:"proposition_hash"`
		Debits      []betCustodySettlementDebitRequest `json:"debits"`
		Credits     []betCustodySettlementCredit       `json:"credits"`
		Allocations []betCustodyOperatorAllocation     `json:"operator_allocations"`
	}{runID, propositionHash, debits, credits, allocations})
	if err != nil {
		return betCustodyNormalizedSettlementRequest{}, err
	}
	normalized.Fingerprint = fingerprint
	return normalized, nil
}

func addBetCustodyAmount(total *uint64, amount uint64) error {
	if ^uint64(0)-*total < amount {
		return errors.New("uwolo amount overflow")
	}
	*total += amount
	return nil
}

func (cfg settlementConfig) buildBetCustodySettlementPlan(
	snapshot betCustodySnapshot,
	normalized betCustodyNormalizedSettlementRequest,
) (
	[]betCustodyAccount,
	[]betCustodyReservation,
	betCustodySettlementRun,
	[]betCustodyLedgerEntry,
	uint64,
	uint64,
	uint64,
	*betCustodySettlementRunResponse,
	error,
) {
	accountCopies := map[string]betCustodyAccount{}
	reservationCopies := map[string]betCustodyReservation{}
	getAccount := func(id string) (betCustodyAccount, bool) {
		if account, ok := accountCopies[id]; ok {
			return account, true
		}
		account, ok := snapshot.Accounts[id]
		if ok {
			accountCopies[id] = account
		}
		return account, ok
	}
	putAccount := func(account betCustodyAccount) { accountCopies[account.ID] = account }

	var debited uint64
	var operatorTotal uint64
	var credited uint64
	entries := []betCustodyLedgerEntry{}
	now := time.Now().UTC()

	for _, debit := range normalized.Debits {
		reservation, ok := reservationCopies[debit.ReservationID]
		if !ok {
			stored, exists := snapshot.Reservations[debit.ReservationID]
			if !exists {
				failure := betCustodySettlementRunResponse{
					FailureCode:     "RESERVATION_NOT_FOUND",
					Detail:          fmt.Sprintf("reservation %s was not found", debit.ReservationID),
					SettlementRunID: normalized.SettlementRunID,
				}
				return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
			}
			reservation = cloneBetCustodyReservation(stored)
		}
		if reservation.PropositionHash != normalized.PropositionHash {
			failure := betCustodySettlementRunResponse{
				FailureCode:     "PROPOSITION_MISMATCH",
				Detail:          fmt.Sprintf("reservation %s does not match settlement proposition", reservation.ID),
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		legIndex := -1
		for index := range reservation.Legs {
			if reservation.Legs[index].ID == debit.LegID {
				legIndex = index
				break
			}
		}
		if legIndex < 0 {
			failure := betCustodySettlementRunResponse{
				FailureCode:     "RESERVATION_LEG_NOT_FOUND",
				Detail:          fmt.Sprintf("leg %s was not found on reservation %s", debit.LegID, reservation.ID),
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		leg := reservation.Legs[legIndex]
		if leg.Status != betCustodyReservationLegStatusReserved {
			failure := betCustodySettlementRunResponse{
				FailureCode:     "RESERVATION_LEG_NOT_RESERVED",
				Detail:          fmt.Sprintf("leg %s is %s and cannot be consumed", leg.ID, leg.Status),
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		account, ok := getAccount(reservation.AccountID)
		if !ok || account.ReservedUWolo < leg.AmountUWolo {
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, errors.New("CUSTODY_STATE_DIVERGED: reserved balance does not cover settlement debit")
		}
		account.ReservedUWolo -= leg.AmountUWolo
		account.SettledDebitUWolo += leg.AmountUWolo
		account.UpdatedAt = now
		putAccount(account)
		reservation.Legs[legIndex].Status = betCustodyReservationLegStatusSettled
		reservation.UpdatedAt = now
		recomputeBetCustodyReservationStatus(&reservation)
		reservationCopies[reservation.ID] = reservation
		if err := addBetCustodyAmount(&debited, leg.AmountUWolo); err != nil {
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, err
		}
		entries = append(entries, betCustodyLedgerEntry{
			AccountID: account.ID, EntryType: "settlement_debit", AmountUWolo: leg.AmountUWolo,
			ReservationID: reservation.ID, LegID: leg.ID, SettlementRunID: normalized.SettlementRunID,
			Detail: "reserved leg consumed by settlement",
		})
	}

	for _, allocation := range normalized.OperatorAllocations {
		account, ok := getAccount(allocation.AccountID)
		if !ok {
			failure := betCustodySettlementRunResponse{
				FailureCode: "OPERATOR_ACCOUNT_NOT_FOUND", Detail: "operator allocation account was not found",
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		if account.Kind != betCustodyAccountKindOperator {
			failure := betCustodySettlementRunResponse{
				FailureCode: "OPERATOR_ACCOUNT_REQUIRED", Detail: "operator allocation may debit only an operator account",
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		if account.AvailableUWolo < allocation.AmountUWolo {
			failure := betCustodySettlementRunResponse{
				FailureCode: "INSUFFICIENT_OPERATOR_CAPITAL", Detail: "operator account lacks available capital",
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		account.AvailableUWolo -= allocation.AmountUWolo
		account.SettledDebitUWolo += allocation.AmountUWolo
		account.UpdatedAt = now
		putAccount(account)
		if err := addBetCustodyAmount(&operatorTotal, allocation.AmountUWolo); err != nil {
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, err
		}
		entries = append(entries, betCustodyLedgerEntry{
			AccountID: account.ID, EntryType: "operator_allocation", AmountUWolo: allocation.AmountUWolo,
			SettlementRunID: normalized.SettlementRunID, Detail: "explicit operator capital allocated to settlement",
		})
	}

	for _, credit := range normalized.Credits {
		account, ok := getAccount(credit.AccountID)
		if !ok {
			failure := betCustodySettlementRunResponse{
				FailureCode: "CREDIT_ACCOUNT_NOT_FOUND", Detail: fmt.Sprintf("credit account %s was not found", credit.AccountID),
				SettlementRunID: normalized.SettlementRunID,
			}
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, &failure, nil
		}
		if ^uint64(0)-account.AvailableUWolo < credit.AmountUWolo {
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, errors.New("account balance overflow")
		}
		account.AvailableUWolo += credit.AmountUWolo
		account.SettledCreditUWolo += credit.AmountUWolo
		account.UpdatedAt = now
		putAccount(account)
		if err := addBetCustodyAmount(&credited, credit.AmountUWolo); err != nil {
			return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, err
		}
		entries = append(entries, betCustodyLedgerEntry{
			AccountID: account.ID, EntryType: "settlement_credit", AmountUWolo: credit.AmountUWolo,
			SettlementRunID: normalized.SettlementRunID, Detail: credit.Kind,
		})
	}

	sources := debited
	if err := addBetCustodyAmount(&sources, operatorTotal); err != nil {
		return nil, nil, betCustodySettlementRun{}, nil, 0, 0, 0, nil, err
	}
	if sources != credited {
		failure := betCustodySettlementRunResponse{
			FailureCode:     "SETTLEMENT_NOT_CONSERVING",
			Detail:          fmt.Sprintf("credits=%d uwolo must exactly equal reserved debits + explicit operator allocation=%d uwolo", credited, sources),
			SettlementRunID: normalized.SettlementRunID,
		}
		return nil, nil, betCustodySettlementRun{}, nil, debited, operatorTotal, credited, &failure, nil
	}

	accounts := make([]betCustodyAccount, 0, len(accountCopies))
	for _, account := range accountCopies {
		accounts = append(accounts, account)
	}
	sort.Slice(accounts, func(i, j int) bool { return accounts[i].ID < accounts[j].ID })
	reservations := make([]betCustodyReservation, 0, len(reservationCopies))
	for _, reservation := range reservationCopies {
		reservations = append(reservations, reservation)
	}
	sort.Slice(reservations, func(i, j int) bool { return reservations[i].ID < reservations[j].ID })

	run := betCustodySettlementRun{
		ID:                  normalized.SettlementRunID,
		RequestFingerprint:  normalized.Fingerprint,
		Debits:              make([]betCustodySettlementDebit, 0, len(normalized.Debits)),
		Credits:             append([]betCustodySettlementCredit(nil), normalized.Credits...),
		OperatorAllocations: append([]betCustodyOperatorAllocation(nil), normalized.OperatorAllocations...),
		Status:              "settled",
		CreatedAt:           now,
	}
	for _, debit := range normalized.Debits {
		reservation := reservationCopies[debit.ReservationID]
		for _, leg := range reservation.Legs {
			if leg.ID == debit.LegID {
				run.Debits = append(run.Debits, betCustodySettlementDebit{
					ReservationID: reservation.ID, LegID: leg.ID, AmountUWolo: leg.AmountUWolo,
				})
				break
			}
		}
	}
	return accounts, reservations, run, entries, debited, operatorTotal, credited, nil, nil
}

func (cfg settlementConfig) executeBetCustodySettlementRun(request betCustodySettlementRunRequest, dryRun bool) (betCustodySettlementRunResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodySettlementRunResponse{DryRun: dryRun, FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	normalized, err := normalizeBetCustodySettlementRequest(request)
	if err != nil {
		return betCustodySettlementRunResponse{DryRun: dryRun, FailureCode: "INVALID_SETTLEMENT_RUN", Detail: err.Error()}, nil
	}

	var response betCustodySettlementRunResponse
	err = cfg.withBetCustodyStateLock(func() error {
		loaded, err := cfg.loadBetCustodyState()
		if err != nil {
			return err
		}
		snapshot := loaded.Snapshot
		if stored, exists := snapshot.SettlementRuns[normalized.SettlementRunID]; exists {
			if stored.RequestFingerprint != normalized.Fingerprint {
				response = betCustodySettlementRunResponse{
					DryRun: dryRun, FailureCode: "IDEMPOTENCY_CONFLICT",
					Detail:          "settlement_run_id already exists with different payload",
					SettlementRunID: normalized.SettlementRunID,
				}
				return nil
			}
			copy := stored
			view := betCustodySettlementRunViewFrom(copy)
			var debited, operatorTotal, credited uint64
			for _, item := range stored.Debits {
				_ = addBetCustodyAmount(&debited, item.AmountUWolo)
			}
			for _, item := range stored.OperatorAllocations {
				_ = addBetCustodyAmount(&operatorTotal, item.AmountUWolo)
			}
			for _, item := range stored.Credits {
				_ = addBetCustodyAmount(&credited, item.AmountUWolo)
			}
			response = betCustodySettlementRunResponse{
				OK: true, DryRun: dryRun, IdempotentReplay: true, Detail: "settlement run already recorded",
				SettlementRunID: stored.ID, DebitedUWolo: strconv.FormatUint(debited, 10),
				OperatorUWolo: strconv.FormatUint(operatorTotal, 10), CreditedUWolo: strconv.FormatUint(credited, 10), Run: &view,
			}
			return nil
		}

		accounts, reservations, run, entries, debited, operatorTotal, credited, failure, err :=
			cfg.buildBetCustodySettlementPlan(snapshot, normalized)
		if err != nil {
			return err
		}
		if failure != nil {
			failure.DryRun = dryRun
			failure.DebitedUWolo = strconv.FormatUint(debited, 10)
			failure.OperatorUWolo = strconv.FormatUint(operatorTotal, 10)
			failure.CreditedUWolo = strconv.FormatUint(credited, 10)
			response = *failure
			return nil
		}
		copy := run
		view := betCustodySettlementRunViewFrom(copy)
		response = betCustodySettlementRunResponse{
			OK: true, DryRun: dryRun, Detail: "settlement run is conserving and valid",
			SettlementRunID: run.ID, DebitedUWolo: strconv.FormatUint(debited, 10),
			OperatorUWolo: strconv.FormatUint(operatorTotal, 10), CreditedUWolo: strconv.FormatUint(credited, 10), Run: &view,
		}
		if dryRun {
			return nil
		}
		delta := betCustodyStateDelta{
			AccountUpserts:       accounts,
			ReservationUpserts:   reservations,
			SettlementRunUpserts: []betCustodySettlementRun{run},
			IdempotencyUpserts: []betCustodyIdempotencyRecord{{
				Scope: "settlement_run", Key: run.ID, Fingerprint: normalized.Fingerprint, ResourceID: run.ID,
			}},
		}
		if err := cfg.commitBetCustodyMutation(&snapshot, "settlement_run:"+run.ID, "settlement_run_committed", entries, delta); err != nil {
			return err
		}
		response.Detail = "settlement run committed"
		return nil
	})
	return response, err
}

func summarizeBetCustodyLiabilities(snapshot betCustodySnapshot) (betCustodyLiabilitiesResponse, error) {
	response := betCustodyLiabilitiesResponse{OK: true, Sequence: snapshot.Sequence, AccountCount: len(snapshot.Accounts)}
	var userAvailable, userReserved, operatorAvailable, operatorReserved uint64
	for _, account := range snapshot.Accounts {
		switch account.Kind {
		case betCustodyAccountKindUser:
			if err := addBetCustodyAmount(&userAvailable, account.AvailableUWolo); err != nil {
				return betCustodyLiabilitiesResponse{}, err
			}
			if err := addBetCustodyAmount(&userReserved, account.ReservedUWolo); err != nil {
				return betCustodyLiabilitiesResponse{}, err
			}
		case betCustodyAccountKindOperator:
			if err := addBetCustodyAmount(&operatorAvailable, account.AvailableUWolo); err != nil {
				return betCustodyLiabilitiesResponse{}, err
			}
			if err := addBetCustodyAmount(&operatorReserved, account.ReservedUWolo); err != nil {
				return betCustodyLiabilitiesResponse{}, err
			}
		default:
			return betCustodyLiabilitiesResponse{}, fmt.Errorf("CUSTODY_STATE_DIVERGED: unknown account kind %q", account.Kind)
		}
	}
	userLiability := userAvailable
	if err := addBetCustodyAmount(&userLiability, userReserved); err != nil {
		return betCustodyLiabilitiesResponse{}, err
	}
	operatorCapital := operatorAvailable
	if err := addBetCustodyAmount(&operatorCapital, operatorReserved); err != nil {
		return betCustodyLiabilitiesResponse{}, err
	}
	total := userLiability
	if err := addBetCustodyAmount(&total, operatorCapital); err != nil {
		return betCustodyLiabilitiesResponse{}, err
	}
	response.UserAvailableUWolo = strconv.FormatUint(userAvailable, 10)
	response.UserReservedUWolo = strconv.FormatUint(userReserved, 10)
	response.UserLiabilityUWolo = strconv.FormatUint(userLiability, 10)
	response.OperatorAvailableUWolo = strconv.FormatUint(operatorAvailable, 10)
	response.OperatorReservedUWolo = strconv.FormatUint(operatorReserved, 10)
	response.OperatorCapitalUWolo = strconv.FormatUint(operatorCapital, 10)
	response.TotalLedgerUWolo = strconv.FormatUint(total, 10)
	return response, nil
}

func (cfg settlementConfig) getBetCustodyLiabilities() (betCustodyLiabilitiesResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyLiabilitiesResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyLiabilitiesResponse{}, err
	}
	return summarizeBetCustodyLiabilities(loaded.Snapshot)
}

func (cfg settlementConfig) reconcileBetCustody(ctx context.Context) (betCustodyReconcileResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyReconcileResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyReconcileResponse{}, err
	}
	liabilities, err := summarizeBetCustodyLiabilities(loaded.Snapshot)
	if err != nil {
		return betCustodyReconcileResponse{}, err
	}
	ledgerTotal, _ := strconv.ParseUint(liabilities.TotalLedgerUWolo, 10, 64)
	balance, err := cfg.fetchAccountBalanceUWolo(ctx, cfg.BetCustodyAddress)
	if err != nil {
		return betCustodyReconcileResponse{
			FailureCode: "CUSTODY_BALANCE_LOOKUP_FAILED", Detail: err.Error(), CustodyAddress: cfg.BetCustodyAddress,
			LedgerTotalUWolo: liabilities.TotalLedgerUWolo, Sequence: loaded.Snapshot.Sequence,
		}, nil
	}
	response := betCustodyReconcileResponse{
		OK: true, Detail: "custody ledger is fully backed", CustodyAddress: cfg.BetCustodyAddress,
		LedgerTotalUWolo: liabilities.TotalLedgerUWolo, OnChainBalanceUWolo: strconv.FormatUint(balance, 10),
		Sequence: loaded.Snapshot.Sequence,
	}
	if balance < ledgerTotal {
		response.OK = false
		response.FailureCode = "CUSTODY_LIABILITY_SHORTFALL"
		response.ShortfallUWolo = strconv.FormatUint(ledgerTotal-balance, 10)
		response.Detail = "on-chain custody balance is below materialized ledger liabilities"
		return response, nil
	}
	response.UnallocatedUWolo = strconv.FormatUint(balance-ledgerTotal, 10)
	return response, nil
}

func (cfg settlementConfig) getBetCustodyAccount(accountID string) (betCustodyAccountResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyFailureAccount("CUSTODY_UNCONFIGURED", err.Error()), nil
	}
	accountID, err := validateBetCustodyOpaqueID("account_id", accountID)
	if err != nil {
		return betCustodyFailureAccount("INVALID_REQUEST", err.Error()), nil
	}
	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyAccountResponse{}, err
	}
	account, ok := loaded.Snapshot.Accounts[accountID]
	if !ok {
		return betCustodyFailureAccount("ACCOUNT_NOT_FOUND", "bet custody account was not found"), nil
	}
	return betCustodyAccountResponseFrom(account), nil
}

func (cfg settlementConfig) getBetCustodyReservation(reservationID string) (betCustodyReservationResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyReservationResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	reservationID, err := validateBetCustodyOpaqueID("reservation_id", reservationID)
	if err != nil {
		return betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyReservationResponse{}, err
	}
	reservation, ok := loaded.Snapshot.Reservations[reservationID]
	if !ok {
		return betCustodyReservationResponse{FailureCode: "RESERVATION_NOT_FOUND", Detail: "reservation was not found"}, nil
	}
	account := loaded.Snapshot.Accounts[reservation.AccountID]
	copy := cloneBetCustodyReservation(reservation)
	view := betCustodyReservationViewFrom(copy)
	return betCustodyReservationResponse{
		OK: true, ReservationID: reservation.ID, AccountID: reservation.AccountID, Status: reservation.Status,
		ReservedUWolo: strconv.FormatUint(account.ReservedUWolo, 10), AvailableUWolo: strconv.FormatUint(account.AvailableUWolo, 10),
		Reservation: &view,
	}, nil
}

func (cfg settlementConfig) getBetCustodyLedger(accountID string) (betCustodyLedgerResponse, error) {
	if err := cfg.ensureBetCustodyConfigured(); err != nil {
		return betCustodyLedgerResponse{FailureCode: "CUSTODY_UNCONFIGURED", Detail: err.Error()}, nil
	}
	accountID, err := validateBetCustodyOpaqueID("account_id", accountID)
	if err != nil {
		return betCustodyLedgerResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()}, nil
	}
	loaded, err := cfg.loadBetCustodyState()
	if err != nil {
		return betCustodyLedgerResponse{}, err
	}
	if _, ok := loaded.Snapshot.Accounts[accountID]; !ok {
		return betCustodyLedgerResponse{FailureCode: "ACCOUNT_NOT_FOUND", Detail: "bet custody account was not found"}, nil
	}
	records, err := readBetCustodyJournal(cfg.betCustodyJournalPath())
	if err != nil {
		return betCustodyLedgerResponse{}, err
	}
	items := []betCustodyLedgerRecord{}
	for _, record := range records {
		for _, entry := range record.Entries {
			if entry.AccountID == accountID {
				items = append(items, betCustodyLedgerRecord{
					Sequence: record.Sequence, OperationID: record.OperationID, OperationType: record.OperationType,
					CreatedAt: record.CreatedAt, Entry: betCustodyLedgerEntryViewFrom(entry),
				})
			}
		}
	}
	return betCustodyLedgerResponse{OK: true, AccountID: accountID, Count: len(items), Entries: items}, nil
}

type betCustodyReservationLegView struct {
	ID          string `json:"id"`
	MarketID    string `json:"market_id"`
	MarketType  string `json:"market_type"`
	Side        string `json:"side"`
	AmountUWolo string `json:"amount_uwolo"`
	Status      string `json:"status"`
}

type betCustodyReservationView struct {
	ID              string                         `json:"id"`
	RequestID       string                         `json:"request_id"`
	AccountID       string                         `json:"account_id"`
	GameIdentity    string                         `json:"game_identity"`
	PropositionHash string                         `json:"proposition_hash"`
	Legs            []betCustodyReservationLegView `json:"legs"`
	Status          string                         `json:"status"`
	CreatedAt       time.Time                      `json:"created_at"`
	UpdatedAt       time.Time                      `json:"updated_at"`
}

type betCustodySettlementDebitView struct {
	ReservationID string `json:"reservation_id"`
	LegID         string `json:"leg_id"`
	AmountUWolo   string `json:"amount_uwolo"`
}

type betCustodySettlementCreditView struct {
	AccountID   string `json:"account_id"`
	AmountUWolo string `json:"amount_uwolo"`
	Kind        string `json:"kind"`
}

type betCustodyOperatorAllocationView struct {
	AccountID   string `json:"account_id"`
	AmountUWolo string `json:"amount_uwolo"`
}

type betCustodySettlementRunView struct {
	ID                  string                             `json:"id"`
	Debits              []betCustodySettlementDebitView    `json:"debits"`
	Credits             []betCustodySettlementCreditView   `json:"credits"`
	OperatorAllocations []betCustodyOperatorAllocationView `json:"operator_allocations,omitempty"`
	Status              string                             `json:"status"`
	CreatedAt           time.Time                          `json:"created_at"`
}

type betCustodyLedgerEntryView struct {
	AccountID       string `json:"account_id"`
	EntryType       string `json:"entry_type"`
	AmountUWolo     string `json:"amount_uwolo"`
	DepositIntentID string `json:"deposit_intent_id,omitempty"`
	TxHash          string `json:"tx_hash,omitempty"`
	ReservationID   string `json:"reservation_id,omitempty"`
	LegID           string `json:"leg_id,omitempty"`
	SettlementRunID string `json:"settlement_run_id,omitempty"`
	WithdrawalID    string `json:"withdrawal_id,omitempty"`
	Detail          string `json:"detail,omitempty"`
}

func betCustodyReservationViewFrom(value betCustodyReservation) betCustodyReservationView {
	legs := make([]betCustodyReservationLegView, 0, len(value.Legs))
	for _, leg := range value.Legs {
		legs = append(legs, betCustodyReservationLegView{
			ID: leg.ID, MarketID: leg.MarketID, MarketType: leg.MarketType, Side: leg.Side,
			AmountUWolo: strconv.FormatUint(leg.AmountUWolo, 10), Status: leg.Status,
		})
	}
	return betCustodyReservationView{
		ID: value.ID, RequestID: value.RequestID, AccountID: value.AccountID,
		GameIdentity: value.GameIdentity, PropositionHash: value.PropositionHash,
		Legs: legs, Status: value.Status, CreatedAt: value.CreatedAt, UpdatedAt: value.UpdatedAt,
	}
}

func betCustodySettlementRunViewFrom(value betCustodySettlementRun) betCustodySettlementRunView {
	debits := make([]betCustodySettlementDebitView, 0, len(value.Debits))
	for _, item := range value.Debits {
		debits = append(debits, betCustodySettlementDebitView{
			ReservationID: item.ReservationID, LegID: item.LegID,
			AmountUWolo: strconv.FormatUint(item.AmountUWolo, 10),
		})
	}
	credits := make([]betCustodySettlementCreditView, 0, len(value.Credits))
	for _, item := range value.Credits {
		credits = append(credits, betCustodySettlementCreditView{
			AccountID: item.AccountID, AmountUWolo: strconv.FormatUint(item.AmountUWolo, 10), Kind: item.Kind,
		})
	}
	allocations := make([]betCustodyOperatorAllocationView, 0, len(value.OperatorAllocations))
	for _, item := range value.OperatorAllocations {
		allocations = append(allocations, betCustodyOperatorAllocationView{
			AccountID: item.AccountID, AmountUWolo: strconv.FormatUint(item.AmountUWolo, 10),
		})
	}
	return betCustodySettlementRunView{
		ID: value.ID, Debits: debits, Credits: credits, OperatorAllocations: allocations,
		Status: value.Status, CreatedAt: value.CreatedAt,
	}
}

func betCustodyLedgerEntryViewFrom(value betCustodyLedgerEntry) betCustodyLedgerEntryView {
	return betCustodyLedgerEntryView{
		AccountID: value.AccountID, EntryType: value.EntryType, AmountUWolo: strconv.FormatUint(value.AmountUWolo, 10),
		DepositIntentID: value.DepositIntentID, TxHash: value.TxHash, ReservationID: value.ReservationID,
		LegID: value.LegID, SettlementRunID: value.SettlementRunID, WithdrawalID: value.WithdrawalID, Detail: value.Detail,
	}
}

func betCustodyHTTPStatus(ok bool, failureCode string) int {
	if ok {
		return http.StatusOK
	}
	switch strings.TrimSpace(failureCode) {
	case "INVALID_REQUEST", "INVALID_AMOUNT", "INVALID_ADDRESS", "INVALID_TX_HASH",
		"INVALID_RESERVATION", "INVALID_SETTLEMENT_RUN", "INVALID_DEPOSIT_MEMO":
		return http.StatusBadRequest
	case "ACCOUNT_NOT_FOUND", "DEPOSIT_NOT_FOUND", "RESERVATION_NOT_FOUND", "RESERVATION_LEG_NOT_FOUND":
		return http.StatusNotFound
	case "CUSTODY_UNCONFIGURED":
		return http.StatusServiceUnavailable
	default:
		return http.StatusConflict
	}
}

func decodeBetCustodyJSON(r *http.Request, dst any) error {
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dst); err != nil {
		return err
	}
	if decoder.More() {
		return errors.New("request body must contain exactly one JSON object")
	}
	return nil
}

func (cfg settlementConfig) requireBetCustodyAuth(w http.ResponseWriter, r *http.Request) bool {
	if err := cfg.checkAuth(r); err != nil {
		writeJSONResponse(w, http.StatusUnauthorized, map[string]string{
			"failure_code": "UNAUTHORIZED",
			"detail":       err.Error(),
		})
		return false
	}
	return true
}

func (cfg settlementConfig) registerBetCustodyHTTPHandlers(mux *http.ServeMux) {
	const root = "/settlement/v1/bet-custody"

	mux.HandleFunc(root+"/accounts", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodyAccountRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyFailureAccount("INVALID_REQUEST", err.Error()))
			return
		}
		response, err := cfg.createBetCustodyAccount(request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/accounts/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		suffix := strings.Trim(strings.TrimPrefix(r.URL.Path, root+"/accounts/"), "/")
		if strings.HasSuffix(suffix, "/ledger") {
			accountID := strings.TrimSuffix(suffix, "/ledger")
			response, err := cfg.getBetCustodyLedger(accountID)
			if err != nil {
				writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
				return
			}
			writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
			return
		}
		response, err := cfg.getBetCustodyAccount(suffix)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/deposit-intents", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodyDepositIntentRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyDepositIntentResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		response, err := cfg.createBetCustodyDepositIntent(request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/deposits/credit", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodyDepositCreditRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyDepositCreditResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		response, err := cfg.creditBetCustodyDeposit(r.Context(), request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/reservations", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodyReservationRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		response, err := cfg.createBetCustodyReservation(request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/reservations/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		reservationID := strings.Trim(strings.TrimPrefix(r.URL.Path, root+"/reservations/"), "/")
		response, err := cfg.getBetCustodyReservation(reservationID)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/reservation-legs/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		suffix := strings.Trim(strings.TrimPrefix(r.URL.Path, root+"/reservation-legs/"), "/")
		if !strings.HasSuffix(suffix, "/release") {
			writeJSONResponse(w, http.StatusNotFound, map[string]string{"detail": "unknown custody route"})
			return
		}
		pathLegID := strings.TrimSuffix(suffix, "/release")
		var request betCustodyReleaseRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyReservationResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		if strings.TrimSpace(request.LegID) == "" {
			request.LegID = pathLegID
		} else if request.LegID != pathLegID {
			writeJSONResponse(w, http.StatusBadRequest, betCustodyReservationResponse{
				FailureCode: "INVALID_REQUEST", Detail: "leg_id body value must match route leg id",
			})
			return
		}
		response, err := cfg.releaseBetCustodyReservationLeg(request)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/settlement-runs/validate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodySettlementRunRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodySettlementRunResponse{DryRun: true, FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		response, err := cfg.executeBetCustodySettlementRun(request, true)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/settlement-runs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		var request betCustodySettlementRunRequest
		if err := decodeBetCustodyJSON(r, &request); err != nil {
			writeJSONResponse(w, http.StatusBadRequest, betCustodySettlementRunResponse{FailureCode: "INVALID_REQUEST", Detail: err.Error()})
			return
		}
		response, err := cfg.executeBetCustodySettlementRun(request, false)
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/liabilities", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		response, err := cfg.getBetCustodyLiabilities()
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})

	mux.HandleFunc(root+"/reconcile", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSONResponse(w, http.StatusMethodNotAllowed, map[string]string{"detail": "method not allowed"})
			return
		}
		if !cfg.requireBetCustodyAuth(w, r) {
			return
		}
		response, err := cfg.reconcileBetCustody(r.Context())
		if err != nil {
			writeJSONResponse(w, http.StatusInternalServerError, map[string]string{"detail": err.Error()})
			return
		}
		writeJSONResponse(w, betCustodyHTTPStatus(response.OK, response.FailureCode), response)
	})
}
