package main

import (
	"fmt"
	"os"

	"github.com/cosmos/cosmos-sdk/server"
	svrcmd "github.com/cosmos/cosmos-sdk/server/cmd"

	"github.com/emaren/wolochain/app"
	"github.com/emaren/wolochain/cmd/wolochaind/cmd"
)

func main() {
	// Print registered modules
	fmt.Println("🔍 Registered Modules:")
	for _, m := range app.GetModuleNames() {
		fmt.Println(" -", m)
	}

	rootCmd, _ := cmd.NewRootCmd()
	if err := svrcmd.Execute(rootCmd, "", app.DefaultNodeHome); err != nil {
		switch e := err.(type) {
		case server.ErrorCode:
			os.Exit(e.Code)
		default:
			os.Exit(1)
		}
	}
}
