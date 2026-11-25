// Package chainevents preserves the settlement service's canonical bank-event
// ordering. Extract retains the existing permissive lookup behavior; consumers
// requiring complete financial evidence must call Validate before Extract.
package chainevents

import (
	"errors"
	"strings"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"
)

type Transfer struct {
	Sender    string `json:"sender"`
	Recipient string `json:"recipient"`
	Amount    string `json:"amount"`
	Denom     string `json:"denom"`
}

type LogItem struct {
	Events []Event `json:"events"`
}

type Event struct {
	Type       string      `json:"type"`
	Attributes []Attribute `json:"attributes"`
}

type Attribute struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type CoinAmount struct {
	Amount string
	Denom  string
}

// Extract uses logs in their original order, splitting each amount in its
// original comma order. Top-level events are used only if the logs yielded no
// transfers. Every denomination and recipient remains in the ordinal list.
// This deliberately preserves settlement lookup's historical permissiveness.
func Extract(logItems []LogItem, fallbackEvents []Event) []Transfer {
	transfers := make([]Transfer, 0)

	appendFromEvents := func(events []Event) {
		for _, event := range events {
			if event.Type != "transfer" {
				continue
			}

			sender := ""
			recipient := ""
			amount := ""
			for _, attr := range event.Attributes {
				switch attr.Key {
				case "sender":
					sender = strings.TrimSpace(attr.Value)
				case "recipient":
					recipient = strings.TrimSpace(attr.Value)
				case "amount":
					amount = strings.TrimSpace(attr.Value)
				}
			}

			if sender == "" || recipient == "" || amount == "" {
				continue
			}

			for _, coin := range SplitCoins(amount) {
				transfers = append(transfers, Transfer{
					Sender:    sender,
					Recipient: recipient,
					Amount:    coin.Amount,
					Denom:     coin.Denom,
				})
			}
		}
	}

	for _, logItem := range logItems {
		appendFromEvents(logItem.Events)
	}

	if len(transfers) == 0 {
		appendFromEvents(fallbackEvents)
	}

	return transfers
}

// SplitCoins preserves the historical settlement parsing contract, including
// skipping malformed items. Validate refuses these items for strict consumers.
func SplitCoins(raw string) []CoinAmount {
	parts := strings.Split(raw, ",")
	out := make([]CoinAmount, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		splitAt := 0
		for splitAt < len(part) && part[splitAt] >= '0' && part[splitAt] <= '9' {
			splitAt++
		}
		if splitAt == 0 || splitAt >= len(part) {
			continue
		}

		out = append(out, CoinAmount{
			Amount: part[:splitAt],
			Denom:  part[splitAt:],
		})
	}
	return out
}

var ErrMalformedTransfer = errors.New("malformed_transfer_event")

// Validate rejects transfer events that permissive lookup could silently skip
// or reinterpret. It checks both representations, including unused fallback
// events. It does not authenticate events, prove execution or grant credit.
func Validate(logItems []LogItem, fallbackEvents []Event) error {
	for _, item := range logItems {
		if err := validateEvents(item.Events); err != nil {
			return err
		}
	}
	return validateEvents(fallbackEvents)
}

func validateEvents(events []Event) error {
	for _, event := range events {
		if event.Type != "transfer" {
			continue
		}
		values := make(map[string]string, 3)
		for _, attr := range event.Attributes {
			switch attr.Key {
			case "sender", "recipient", "amount":
				if _, exists := values[attr.Key]; exists {
					return ErrMalformedTransfer
				}
				values[attr.Key] = strings.TrimSpace(attr.Value)
			}
		}
		if values["sender"] == "" || values["recipient"] == "" || values["amount"] == "" {
			return ErrMalformedTransfer
		}
		parts := strings.Split(values["amount"], ",")
		coins := SplitCoins(values["amount"])
		if len(parts) != len(coins) {
			return ErrMalformedTransfer
		}
		seen := make(map[string]bool, len(coins))
		for _, coin := range coins {
			// Canonical bank base units are positive integers. Use the SDK's
			// denomination validation and bounded integer implementation.
			if len(coin.Amount) > 78 || coin.Amount[0] == '0' || sdk.ValidateDenom(coin.Denom) != nil || seen[coin.Denom] {
				return ErrMalformedTransfer
			}
			integer, ok := sdkmath.NewIntFromString(coin.Amount)
			if !ok || !integer.IsPositive() {
				return ErrMalformedTransfer
			}
			seen[coin.Denom] = true
		}
	}
	return nil
}
