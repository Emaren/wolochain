package chainjson

import "testing"

func TestFoldedJSONGuardRejectsDecoderAliasesWithoutChangingJSONContract(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name   string
		json   string
		valid  bool
		folded bool
	}{
		{"ASCII aliases", `{"memo":1,"MEMO":2}`, true, false},
		{"Unicode long s aliases", `{"source_app":1,"ſource_app":2}`, true, false},
		{"Unicode Kelvin aliases", `{"key":1,"Key":2}`, true, false},
		{"escaped aliases", `{"memo":1,"\u004dEMO":2}`, true, false},
		{"nested aliases", `{"payouts":[{"amount_uwolo":"1","AMOUNT_UWOLO":"2"}]}`, true, false},
		{"separate object scope", `{"payouts":[{"amount_uwolo":"1"},{"AMOUNT_UWOLO":"2"}]}`, true, true},
		{"single alternate spelling", `{"MEMO":"ordinary","ſource_app":"compatible"}`, true, true},
		{"distinct keys", `{"memo":"ordinary","note":"different"}`, true, true},
		{"exact duplicates remain forbidden", `{"memo":1,"memo":2}`, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := Valid([]byte(tc.json)); got != tc.valid {
				t.Fatalf("existing JSON contract changed: Valid=%v, want %v", got, tc.valid)
			}
			if got := ValidFolded([]byte(tc.json)); got != tc.folded {
				t.Fatalf("folded member ambiguity result=%v, want %v", got, tc.folded)
			}
		})
	}
}
