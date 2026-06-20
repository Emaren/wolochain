package types

import (
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/msgservice"
)

// RegisterInterfaces registers wartrophy messages.
func RegisterInterfaces(registrar codectypes.InterfaceRegistry) {
	registrar.RegisterImplementations(
		(*sdk.Msg)(nil),
		&MsgRegisterTrophy{},
		&MsgMintTrophy{},
		&MsgAssignTrophy{},
		&MsgReassignTrophy{},
		&MsgRetireTrophy{},
		&MsgUpdateTrophyMetadata{},
		&MsgSetTrophyAuthority{},
	)
	msgservice.RegisterMsgServiceDesc(registrar, &_Msg_serviceDesc)
}
