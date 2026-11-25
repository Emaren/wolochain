package cmd

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"time"

	"github.com/emaren/wolochain/internal/chainjson"
)

const settlementJSONLimit = 1 << 20

// Use the chain reader's duplicate/depth/trailing-value guard for requests too.
// Unknown fields remain compatible with existing callers, but the envelope must
// be one object. Decode only after the entire bounded input has passed the guard.
func decodeSettlementObject(reader io.Reader, dst any) error {
	data, err := io.ReadAll(io.LimitReader(reader, settlementJSONLimit+1))
	if err != nil || len(data) > settlementJSONLimit || !chainjson.ValidFolded(data) {
		return errors.New("invalid bounded JSON")
	}
	if _, ok := chainjson.Object(data); !ok {
		return errors.New("request must be a JSON object")
	}
	return json.Unmarshal(data, dst)
}

func decodeSettlementRequestJSON(w http.ResponseWriter, r *http.Request, dst any) error {
	if encoding := r.Header.Get("Content-Encoding"); encoding != "" && encoding != "identity" {
		return errors.New("unsupported request encoding")
	}
	r.Body = http.MaxBytesReader(w, r.Body, settlementJSONLimit)
	return decodeSettlementObject(r.Body, dst)
}

func (cfg settlementConfig) newSettlementHTTPServer() *http.Server {
	// A run may contain 250 sequential payouts. Keep its existing per-command
	// and confirmation budgets while bounding HTTP reads, idle time and writes.
	writeBudget := time.Minute + settlementMaxRunPayouts*(cfg.RequestTimeout+cfg.ConfirmTimeout+cfg.LookupTimeout)
	return &http.Server{
		Addr: cfg.ListenAddr, Handler: cfg.newSettlementHTTPHandler(),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second,
		WriteTimeout: writeBudget, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16384,
	}
}

func boundedSettlementHandler(next http.Handler) http.Handler {
	// Refuse excess work before parsing or entering financial execution. Never
	// queue or retry an accepted financial operation in this resource guard.
	slots := make(chan struct{}, 16)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
			next.ServeHTTP(w, r)
		default:
			writeJSONResponse(w, http.StatusServiceUnavailable, map[string]string{"detail": "settlement request capacity reached"})
		}
	})
}
