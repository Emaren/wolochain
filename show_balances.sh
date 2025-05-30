#!/bin/bash

set -e

# Colors and box drawing
GREEN="\033[1;32m"
RESET="\033[0m"
TOP_LEFT="┌"
TOP_RIGHT="┐"
BOTTOM_LEFT="└"
BOTTOM_RIGHT="┘"
HORIZONTAL="─"
VERTICAL="│"

# Get block height
HEIGHT=$(wolochaind status 2>/dev/null | jq -r '.SyncInfo.latest_block_height')
# Get total supply
TOTAL_SUPPLY=$(wolochaind query bank total -o json | jq -r '.supply[] | select(.denom=="uwolo") | .amount')
# Get account balances
ACCOUNTS=$(wolochaind keys list --keyring-backend test -o json)

# Prep rows
ROWS=()
ROWS+=("📦 Block Height: $HEIGHT")
ROWS+=("💰 Total Supply: $TOTAL_SUPPLY uwolo")
ROWS+=("")

echo "$ACCOUNTS" | jq -r '.[] | "\(.name)\t\(.address)"' | while IFS=$'\t' read -r name address; do
  balance=$(wolochaind query bank balances "$address" -o json | jq -r '.balances[]? | "\(.amount) \(.denom)"')
  ROWS+=("🧑 $name: $balance")
done

# Calculate max width
MAX_WIDTH=0
for row in "${ROWS[@]}"; do
  [ ${#row} -gt $MAX_WIDTH ] && MAX_WIDTH=${#row}
done
((MAX_WIDTH+=4)) # Padding

# Draw top border
printf "${GREEN}${TOP_LEFT}"
for ((i=0; i<MAX_WIDTH; i++)); do printf "${HORIZONTAL}"; done
printf "${TOP_RIGHT}\n"

# Draw content
for row in "${ROWS[@]}"; do
  printf "${VERTICAL} ${row}"
  spaces=$((MAX_WIDTH - ${#row} - 1))
  for ((i=0; i<spaces; i++)); do printf " "; done
  printf "${VERTICAL}\n"
done

# Draw bottom border
printf "${BOTTOM_LEFT}"
for ((i=0; i<MAX_WIDTH; i++)); do printf "${HORIZONTAL}"; done
printf "${BOTTOM_RIGHT}${RESET}\n"
