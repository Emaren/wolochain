package chainevents

import (
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func transfer(sender, recipient, amount string) Event {
	return Event{Type: "transfer", Attributes: []Attribute{{"sender", sender}, {"recipient", recipient}, {"amount", amount}}}
}

func TestExtractPreservesCompleteOrdinalOrdering(t *testing.T) {
	t.Parallel()
	logs := []LogItem{
		{Events: []Event{{Type: "message"}, transfer(" fee-payer ", " fee-collector ", " 2uwolo ")}},
		{Events: []Event{transfer("owner", "vault", "5uother,7uwolo"), transfer("another", "elsewhere", "9uwolo")}},
	}
	fallback := []Event{transfer("unselected", "unselected", "100uwolo")}
	want := []Transfer{
		{"fee-payer", "fee-collector", "2", "uwolo"},
		{"owner", "vault", "5", "uother"},
		{"owner", "vault", "7", "uwolo"},
		{"another", "elsewhere", "9", "uwolo"},
	}
	if got := Extract(logs, fallback); !reflect.DeepEqual(got, want) {
		t.Fatalf("canonical ordinal list: got %#v, want %#v", got, want)
	}
	if err := Validate(logs, fallback); err != nil {
		t.Fatalf("valid complete events: %v", err)
	}
}

func TestExtractPreservesPermissiveLegacyBehavior(t *testing.T) {
	t.Parallel()
	lastAttributeWins := transfer("initial", "vault", "invalid,4uwolo,,5uother,100")
	lastAttributeWins.Attributes = append(lastAttributeWins.Attributes, Attribute{"sender", " final "})
	logs := []LogItem{{Events: []Event{lastAttributeWins, {Type: "transfer", Attributes: []Attribute{{"amount", "8uwolo"}}}}}}
	want := []Transfer{{"final", "vault", "4", "uwolo"}, {"final", "vault", "5", "uother"}}
	if got := Extract(logs, []Event{transfer("fallback", "vault", "9uwolo")}); !reflect.DeepEqual(got, want) {
		t.Fatalf("legacy lookup semantics changed: got %#v, want %#v", got, want)
	}
	if !errors.Is(Validate(logs, nil), ErrMalformedTransfer) {
		t.Fatal("strict consumer accepted legacy-skipped or duplicate data")
	}
	if got := Extract([]LogItem{{Events: []Event{{Type: "transfer"}}}}, []Event{transfer("fallback", "vault", "9uwolo")}); !reflect.DeepEqual(got, []Transfer{{"fallback", "vault", "9", "uwolo"}}) {
		t.Fatalf("empty log extraction no longer falls back: %#v", got)
	}
	if got := Extract(nil, nil); got == nil || len(got) != 0 {
		t.Fatalf("legacy empty nonnil result changed: %#v", got)
	}
}

func TestValidateRejectsMalformedAndHiddenEvents(t *testing.T) {
	t.Parallel()
	cases := map[string]Event{
		"missing all attributes": {Type: "transfer"},
		"missing sender":         {Type: "transfer", Attributes: []Attribute{{"recipient", "vault"}, {"amount", "1uwolo"}}},
		"blank recipient":        transfer("owner", " \t", "1uwolo"),
		"blank amount":           transfer("owner", "vault", " "),
		"duplicate sender":       {Type: "transfer", Attributes: []Attribute{{"sender", "owner"}, {"sender", "owner"}, {"recipient", "vault"}, {"amount", "1uwolo"}}},
		"duplicate recipient":    {Type: "transfer", Attributes: []Attribute{{"sender", "owner"}, {"recipient", "vault"}, {"recipient", "other"}, {"amount", "1uwolo"}}},
		"duplicate amount":       {Type: "transfer", Attributes: []Attribute{{"sender", "owner"}, {"recipient", "vault"}, {"amount", "1uwolo"}, {"amount", "1uwolo"}}},
	}
	for _, invalid := range []string{"uwolo", "1", "1uwolo,", ",1uwolo", "1uwolo,,2uother", "1uwolo,garbage", "-1uwolo", "+1uwolo", "0uwolo", "01uwolo", "1.5uwolo", "1 uwolo", "1u!", "1uwolo,2uwolo", strings.Repeat("9", 79) + "uwolo", strings.Repeat("9", 78) + "uwolo"} {
		cases["coin "+invalid] = transfer("owner", "vault", invalid)
	}
	for name, malformed := range cases {
		t.Run(name, func(t *testing.T) {
			for _, where := range []string{"log", "fallback", "unused fallback", "later log"} {
				t.Run(where, func(t *testing.T) {
					var logs []LogItem
					var fallback []Event
					switch where {
					case "log":
						logs = []LogItem{{Events: []Event{malformed}}}
					case "fallback":
						fallback = []Event{malformed}
					case "unused fallback":
						logs = []LogItem{{Events: []Event{transfer("owner", "vault", "1uwolo")}}}
						fallback = []Event{malformed}
					case "later log":
						logs = []LogItem{{Events: []Event{transfer("owner", "vault", "1uwolo")}}, {Events: []Event{malformed}}}
					}
					if err := Validate(logs, fallback); !errors.Is(err, ErrMalformedTransfer) {
						t.Fatalf("malformed transfer accepted: %v", err)
					}
				})
			}
		})
	}
}

func TestValidateSDKDenominationsAndOriginalCoinOrder(t *testing.T) {
	t.Parallel()
	event := transfer("owner", "vault", "2uother,3ibc/ABC,4factory/wolo1owner/token")
	if err := Validate(nil, []Event{event}); err != nil {
		t.Fatal(err)
	}
	if got := Extract(nil, []Event{event}); !reflect.DeepEqual(got, []Transfer{{"owner", "vault", "2", "uother"}, {"owner", "vault", "3", "ibc/ABC"}, {"owner", "vault", "4", "factory/wolo1owner/token"}}) {
		t.Fatalf("coin order was sorted or denomination was filtered: %#v", got)
	}
	if err := Validate([]LogItem{{Events: []Event{{Type: "message", Attributes: []Attribute{{"sender", ""}}}}}}, nil); err != nil {
		t.Fatalf("non-transfer event must not be parsed as transfer: %v", err)
	}
	if err := Validate(nil, []Event{transfer("owner", "vault", "115792089237316195423570985008687907853269984665640564039457584007913129639935uwolo")}); err != nil {
		t.Fatalf("maximum SDK unsigned 256-bit amount must parse without truncation: %v", err)
	}
}

func TestSharedJSONContract(t *testing.T) {
	t.Parallel()
	var payload struct {
		Logs   []LogItem `json:"logs"`
		Events []Event   `json:"events"`
	}
	if err := json.Unmarshal([]byte(`{"logs":[{"events":[{"type":"transfer","attributes":[{"key":"sender","value":"owner"},{"key":"recipient","value":"vault"},{"key":"amount","value":"3uwolo"}]}]}],"events":[]}`), &payload); err != nil {
		t.Fatal(err)
	}
	got, err := json.Marshal(Extract(payload.Logs, payload.Events))
	if err != nil || string(got) != `[{"sender":"owner","recipient":"vault","amount":"3","denom":"uwolo"}]` {
		t.Fatalf("shared settlement JSON contract changed: %s, %v", got, err)
	}
}
