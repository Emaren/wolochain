// Package chainjson contains bounded JSON guards shared by chain consumers and financial requests.
package chainjson

import (
	"bytes"
	"encoding/json"
	"io"
	"strconv"
	"strings"
	"unicode"
)

// Bound JSON structure and reject duplicate members before either JSON decoder
// sees it. This prevents last-member-wins execution code/envelope substitution.
func Valid(data []byte) bool {
	return valid(data, false)
}

// ValidFolded also rejects members whose names encoding/json treats as aliases
// for the same struct field. A single alternate spelling remains compatible;
// two colliding spellings may not silently substitute a financial request field.
func ValidFolded(data []byte) bool {
	return valid(data, true)
}

func valid(data []byte, folded bool) bool {
	d := json.NewDecoder(bytes.NewReader(data))
	d.UseNumber()
	nodes := 0
	var value func(int) bool
	value = func(depth int) bool {
		nodes++
		if depth > 32 || nodes > 100000 {
			return false
		}
		t, err := d.Token()
		if err != nil {
			return false
		}
		switch t {
		case json.Delim('{'):
			seen := map[string]bool{}
			for d.More() {
				key, err := d.Token()
				if err != nil {
					return false
				}
				k, ok := key.(string)
				if folded {
					k = foldKey(k)
				}
				if !ok || seen[k] {
					return false
				}
				seen[k] = true
				if !value(depth + 1) {
					return false
				}
			}
			end, err := d.Token()
			return err == nil && end == json.Delim('}')
		case json.Delim('['):
			for d.More() {
				if !value(depth + 1) {
					return false
				}
			}
			end, err := d.Token()
			return err == nil && end == json.Delim(']')
		case json.Delim('}'), json.Delim(']'):
			return false
		default:
			return true
		}
	}
	if !value(0) {
		return false
	}
	_, err := d.Token()
	return err == io.EOF
}

// Match encoding/json's Unicode simple-fold equivalence, including the long s
// and Kelvin sign. Lowercasing alone does not cover every decoder alias.
func foldKey(key string) string {
	return strings.Map(func(r rune) rune {
		for {
			next := unicode.SimpleFold(r)
			if next <= r {
				return next
			}
			r = next
		}
	}, key)
}

func Object(data []byte) (map[string]json.RawMessage, bool) {
	if len(bytes.TrimSpace(data)) == 0 || bytes.TrimSpace(data)[0] != '{' {
		return nil, false
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(data, &fields) != nil || fields == nil {
		return nil, false
	}
	return fields, true
}

// Proto3 JSON may omit a zero uint32 code. Absence is accepted only INSIDE
// an already-required complete transaction/result object. Null is never zero.
func ExecutionCode(fields map[string]json.RawMessage) (uint32, bool) {
	raw, exists := fields["code"]
	if !exists {
		return 0, true
	}
	s := string(bytes.TrimSpace(raw))
	if len(s) > 0 && s[0] == '"' {
		var decoded string
		if json.Unmarshal(raw, &decoded) != nil {
			return 0, false
		}
		s = decoded
	}
	if s == "" || (len(s) > 1 && s[0] == '0') {
		return 0, false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, false
		}
	}
	n, err := strconv.ParseUint(s, 10, 32)
	return uint32(n), err == nil
}
