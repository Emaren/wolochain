package satchelservice

import (
	"testing"

	base "cosmossdk.io/api/cosmos/base/v1beta1"
	txapi "cosmossdk.io/api/cosmos/tx/v1beta1"
	"google.golang.org/protobuf/proto"
)

func TestOfflineWagerProofBindsActualFeeRatherThanSignedExporterClaim(t *testing.T) {
	f := newBackendFixture(t)
	signed, err := f.b.Sign(t.Context(), f.request)
	if err != nil {
		t.Fatal(err)
	}
	if err := verifyWagerProofFee(signed.Bytes, f.b.cfg.FeesUWolo); err != nil {
		t.Fatal(err)
	}
	if err := verifyWagerProofFee(signed.Bytes, "1"); err == nil {
		t.Fatal("independently approved lower fee accepted actual larger debit")
	}
	for _, mutate := range []func(*txapi.AuthInfo){
		func(a *txapi.AuthInfo) { a.Fee.Payer = f.request.Sender },
		func(a *txapi.AuthInfo) { a.Fee.Granter = f.request.Sender },
		func(a *txapi.AuthInfo) { a.Fee.Amount = append(a.Fee.Amount, &base.Coin{Denom: "stake", Amount: "1"}) },
		func(a *txapi.AuthInfo) { a.Fee.Amount[0].Denom = "stake" },
		func(a *txapi.AuthInfo) { a.Fee = nil },
	} {
		var raw txapi.TxRaw
		var auth txapi.AuthInfo
		if proto.Unmarshal(signed.Bytes, &raw) != nil || proto.Unmarshal(raw.AuthInfoBytes, &auth) != nil {
			t.Fatal("bad native fixture")
		}
		mutate(&auth)
		raw.AuthInfoBytes, _ = proto.Marshal(&auth)
		encoded, _ := proto.Marshal(&raw)
		if verifyWagerProofFee(encoded, f.b.cfg.FeesUWolo) == nil {
			t.Fatal("ambiguous or different fee responsibility accepted")
		}
	}
}
