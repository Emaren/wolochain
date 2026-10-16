package cmd

import (
    "math"
    "strconv"
    "strings"
    "testing"
)

// Regression: a signed int64 whole-WOLO amount must not wrap when converted
// to the Cosmos 6-decimal base denomination.
func TestSettlementNormalizeWholeWOLOOverflow(t *testing.T) {
    ceiling := int64(math.MaxInt64 / 1_000_000)
    for _, tc := range []struct {
        name string
        wolo int64
        want string
        valid bool
    }{
        {"one", 1, "1000000", true},
        {"representable_max", ceiling, strconv.FormatInt(ceiling*1_000_000, 10), true},
        {"overflow_by_one", ceiling + 1, "", false},
        {"max_int64", math.MaxInt64, "", false},
        {"zero", 0, "", false},
        {"negative", -1, "", false},
    } {
        t.Run(tc.name, func(t *testing.T) {
            got, err := normalizeAmountUWolo("", tc.wolo)
            if tc.valid && (err != nil || got != tc.want) {
                t.Fatalf("expected exact payout units %q, got %q: %v", tc.want, got, err)
            }
            if !tc.valid && (err == nil || got != "") {
                t.Fatalf("unsafe whole-WOLO amount %d accepted as %q", tc.wolo, got)
            }
        })
    }
}

func TestSettlementNormalizeMicroWOLOCanonicalAndSignedBounded(t *testing.T) {
    for _, valid := range []string{"1", "1000000", strconv.FormatInt(math.MaxInt64, 10)} {
        got, err := normalizeAmountUWolo(valid, 0)
        if err != nil || got != valid { t.Fatalf("valid %q rejected as %q: %v", valid, got, err) }
    }
    bad := []string{
        "0", "00", "0001", "01", "+1", "-1", " 001 ", "1.0",
        "000000", "1e6", "0x10", "1_000_000",
        "9223372036854775808", "18446744073709551615", "18446744073709551616",
        strings.Repeat("9", 100),
    }
    for _, invalid := range bad {
        if got, err := normalizeAmountUWolo(invalid, 0); err == nil || got != "" {
            t.Errorf("noncanonical/unsafe micro amount %q accepted as %q", invalid, got)
        }
    }
}

func TestSettlementRejectMixedAmountRepresentations(t *testing.T) {
    for _, whole := range []int64{-5, -1, 1, 5} {
        if got, err := normalizeAmountUWolo("1000000", whole); err == nil || got != "" {
            t.Errorf("mixed micro=%q, whole=%d accepted as %q", "1000000", whole, got)
        }
    }
}
