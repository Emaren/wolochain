// wolo-c01-admission admits and proves one zero-funds key-possession check.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/emaren/wolochain/internal/satchelservice"
	"golang.org/x/sys/unix"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if len(os.Args) == 3 {
		switch os.Args[1] {
		case "prepare":
			request, err := satchelservice.PrepareC01KeyPossessionRequest(ctx, os.Args[2])
			if err == nil {
				// The owner signer requires exactly these bytes, with no newline.
				if _, err = os.Stdout.Write(request); err == nil {
					return
				}
			}
		case "admit":
			if unix.Setrlimit(unix.RLIMIT_CORE, &unix.Rlimit{}) != nil {
				break
			}
			receipt, err := satchelservice.CheckC01AdmittedKey(ctx, os.Args[2])
			if err == nil && json.NewEncoder(os.Stdout).Encode(receipt) == nil {
				return
			}
		}
	}
	fmt.Fprintln(os.Stderr, "C01_ZERO_FUNDS_ADMISSION_REFUSED")
	os.Exit(3)
}
