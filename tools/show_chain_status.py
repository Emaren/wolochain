#!/Users/tonyblum/miniconda3/bin/python
import subprocess
import json
import time
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

NODE = "tcp://localhost:26657"
console = Console()

# Known addresses for clear display
KNOWN_LABELS = {
    "wolo1g36x89pcac2xfxd5mn8sxslr9dtu2yczzj5f4a": "👑 Emperor Wallet",
    "wolo1pfpcep0c5vch278kxkh50caeqz252lquuss58s": "🚰 Faucet Wallet",
    "wolo1vrpwkywwa9q8zl3ycmafq2napja58vr2c4j3w4": "🛡️ Validator Wallet",
    "wolo1fl48vsnmsdzcv85q5d2q4z5ajdha8yu3aqv4s2": "🔒 Bonded Token Pool",
    "wolo1tygms3xhhs3yv487phx3dw4a95jn7t7lfqsyx7": "🌀 Not Bonded Pool",
    "wolo10d07y265gmmuvt4z0w9aw880jnsr700jjekllw": "🏛️ Gov Module",
    "wolo1jv65s3grqf6v6jl3dp4t6c9t9rk99cd80ypxqz": "🎁 Distribution Module",
    "wolo1m3h30wlvsf8llruxtpukdvsy0km2kum8q2zzwa": "🧱 Mint Module",
    "wolo17xpfvakm2amg962yls6f84z3kell8c5lczx6zq": "💸 Fee Collector",
}

def run_cmd(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except:
        return None

def get_block_height():
    res = run_cmd(["curl", "-s", "localhost:26657/status"])
    return res["result"]["sync_info"]["latest_block_height"] if res else "?"

def get_accounts():
    res = run_cmd(["wolochaind", "q", "auth", "accounts", "--output", "json", "--node", NODE])
    return res["accounts"] if res else []

def get_balance(address):
    res = run_cmd(["wolochaind", "q", "bank", "balances", address, "--output", "json", "--node", NODE])
    coins = res["balances"] if res else []
    total = sum(int(c["amount"]) for c in coins if c["denom"] == "uwolo")
    wolo_amount = total / 1_000_000
    display = f"{wolo_amount:,.6f} wolo" if total else "0 wolo"
    return total, display

def get_supply_and_staked():
    pool_data = run_cmd(["wolochaind", "q", "staking", "pool", "--output", "json", "--node", NODE])
    accounts = get_accounts()

    if not accounts or not pool_data:
        return 0, 0, 0, 0

    total = 0
    for acc in accounts:
        addr = acc.get("base_account", {}).get("address", acc.get("address", "???"))
        balance_data = run_cmd(["wolochaind", "q", "bank", "balances", addr, "--output", "json", "--node", NODE])
        coins = balance_data["balances"] if balance_data else []
        total += sum(int(c["amount"]) for c in coins if c["denom"] == "uwolo")

    staked = int(pool_data.get("bonded_tokens", 0))
    unbonded = total - staked
    percent = (staked / total * 100) if total > 0 else 0
    return total / 1_000_000, staked / 1_000_000, unbonded / 1_000_000, percent

def build_table(height, accounts):
    total, staked, unbonded, percent = get_supply_and_staked()

    table = Table(
        title=f"Wolochain – Chain Status @ Block {height}",
        show_lines=True,
        pad_edge=False
    )
    table.add_column("Name or Type", style="cyan")  # Let it wrap
    table.add_column("Address", style="white")      # Full length address
    table.add_column("Balance", style="green", justify="right", no_wrap=True)

    balances = []
    for acc in accounts:
        addr = acc.get("base_account", {}).get("address", acc.get("address", "???"))
        raw_name = acc.get("name", "")
        is_module = "@type" in acc and "ModuleAccount" in acc["@type"]
        label = KNOWN_LABELS.get(addr)

        if label:
            name = label.ljust(26)[:26]
        elif is_module:
            name = f"🧩 {raw_name or 'Module Account'}".ljust(26)[:26]
        else:
            name = "👤 EOA Wallet".ljust(26)

        amount, display = get_balance(addr)
        balances.append((name, addr, display, amount))

    balances.sort(key=lambda x: x[3], reverse=True)

    for name, addr, display, _ in balances:
        table.add_row(name, addr, display)

    summary = (
        f"💰 [bold]Total Supply:[/bold] {total:,.6f} wolo\n"
        f"🔒 [bold]Staked:[/bold] {staked:,.6f} wolo ({percent:.2f}%)\n"
        f"🌀 [bold]Unbonded:[/bold] {unbonded:,.6f} wolo"
    )

    table.caption = summary
    return Panel(table, border_style="green", expand=True)

if __name__ == "__main__":
    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            height = get_block_height()
            accounts = get_accounts()
            panel = build_table(height, accounts)
            live.update(panel)
            time.sleep(5)

