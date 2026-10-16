package satchel

import (
	"encoding/json"
	"github.com/emaren/wolochain/internal/chainjson"
)

// Preserve the C3 contracts while sharing its JSON presence and resource guards.
func strictJSON(data []byte) bool                           { return chainjson.Valid(data) }
func object(data []byte) (map[string]json.RawMessage, bool) { return chainjson.Object(data) }
func executionCode(fields map[string]json.RawMessage) (uint32, bool) {
	return chainjson.ExecutionCode(fields)
}
