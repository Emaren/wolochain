import os
import json
import re
import subprocess
import time
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.progress import track

start = time.time()
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(PROJECT_DIR, 'gptcontext.json')
console = Console()

# 🧠 Banner
def print_banner():
    console.print(Panel.fit(
        "[bold cyan]🧠  Wolochain Agent Context Builder[/bold cyan]\n[blue]🔍 Scanning project structure and environment...[/blue]",
        title="",
        border_style="green",
        padding=(1, 4),
        box=box.SQUARE
    ))

# 🧠 Data Extraction Functions
def get_git_branch():
    try:
        branch = subprocess.check_output([
            "git", "rev-parse", "--abbrev-ref", "HEAD"
        ], cwd=PROJECT_DIR).decode().strip()
        console.print(f"[green]🌿 Git branch:[/green] {branch}")
        return branch
    except:
        console.print("[yellow]⚠️  Not a git repo[/yellow]")
        return None

def get_go_version():
    try:
        output = subprocess.check_output(["go", "version"]).decode()
        match = re.search(r"go version go([\d.]+)", output)
        version = match.group(1) if match else "unknown"
        console.print(f"[green]🔧 Go version:[/green] {version}")
        return version
    except:
        console.print("[red]💀 Could not detect Go version[/red]")
        return "unknown"

def get_sdk_version():
    try:
        with open("go.mod") as f:
            content = f.read()
            match = re.search(r"github.com/cosmos/cosmos-sdk v([\d.]+)", content)
            version = match.group(1) if match else "unknown"
            console.print(f"[green]🧬 Cosmos SDK:[/green] {version}")
            return version
    except:
        console.print("[red]💀 Could not read go.mod[/red]")
        return "unknown"

def get_modules():
    try:
        with open("app/app.go") as f:
            content = f.read()
            modules = sorted(set(re.findall(r'\"github.com/.+/x/(\w+)\"', content)))
            console.print(f"[green]📆 Modules:[/green] {len(modules)} found")
            return modules
    except:
        console.print("[red]💀 Could not parse app/app.go[/red]")
        return []

def get_custom_modules():
    x_path = os.path.join(PROJECT_DIR, "x")
    if not os.path.exists(x_path):
        console.print("[yellow]⚠️  No x/ directory found[/yellow]")
        return []
    modules = [m for m in os.listdir(x_path) if os.path.isdir(os.path.join(x_path, m))]
    console.print(f"[green]🧹 Custom Modules:[/green] {len(modules)} found")
    return sorted(modules)

def detect_build_tool():
    if os.path.exists("Makefile"):
        tool = "make build"
    elif os.path.exists("build.sh"):
        tool = "./build.sh"
    else:
        tool = "go build"
    console.print(f"[green]🛠️  Build Tool:[/green] {tool}")
    return tool

def detect_tokens_from_genesis():
    path = os.path.join(PROJECT_DIR, "genesis.custom.json")
    try:
        with open(path) as f:
            data = json.load(f)
            balances = data["app_state"]["bank"]["balances"]
            denoms = {coin["denom"] for acct in balances for coin in acct.get("coins", [])}
            console.print(f"[green]💰 Genesis Tokens:[/green] {sorted(denoms)}")
            return sorted(denoms)
    except:
        console.print("[yellow]⚠️  No valid genesis.custom.json or tokens missing[/yellow]")
        return []

def get_proto_packages():
    packages = set()
    proto_dir = os.path.join(PROJECT_DIR, "proto")
    if not os.path.exists(proto_dir):
        console.print("[yellow]⚠️  No proto/ directory found[/yellow]")
        return []

    proto_files = []
    for root, _, files in os.walk(proto_dir):
        for file in files:
            if file.endswith(".proto"):
                proto_files.append(os.path.join(root, file))

    if not proto_files:
        console.print("[yellow]⚠️  No .proto files found[/yellow]")
        return []

    console.print(f"[green]📆 Scanning {len(proto_files)} proto files...[/green]")

    for file_path in track(proto_files, description="🔍 Reading proto packages"):
        with open(file_path) as f:
            for line in f:
                match = re.search(r'^\s*package\s+([^\s;]+);', line)
                if match:
                    packages.add(match.group(1))

    result = sorted(packages)
    console.print(f"[green]📆 Proto Packages:[/green] {len(result)} found")
    return result

def build_context():
    modules = get_modules()
    return {
        "chain_id": "wolochain",
        "git_branch": get_git_branch(),
        "cosmos_sdk": get_sdk_version(),
        "go_version": get_go_version(),
        "wasm_enabled": "wasm" in modules,
        "modules": modules,
        "custom_modules": get_custom_modules(),
        "proto_packages": get_proto_packages(),
        "build_tool": detect_build_tool(),
        "custom_genesis": "genesis.custom.json" if os.path.exists("genesis.custom.json") else None,
        "genesis_tokens": detect_tokens_from_genesis(),
        "chat_model": "gpt-4",
        "notes": "Auto-generated by gptcontext.autogen.py"
    }

def write_context_file(context):
    with open(CONTEXT_FILE, "w") as f:
        json.dump(context, f, indent=2)

    table = Table(title="🗞 Context Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Key", style="green")
    table.add_column("Value / Count", style="green")

    for key, val in context.items():
        display = f"{len(val)} items" if isinstance(val, list) else str(val)
        table.add_row(f"✅ {key}", display if val else "[dim](empty)[/dim]")

    console.print(table)
    console.print(Panel.fit(f"[green]✅ gptcontext.json written[/green] to [bold]{CONTEXT_FILE}[/bold]\n[blue]⏱️ Scan time:[/blue] {round(time.time() - start, 2)}s", title="📂 Output"))

def main():
    parser = argparse.ArgumentParser(description="Build gptcontext.json")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of saving")
    parser.add_argument("--print", action="store_true", help="Print formatted summary only")
    args = parser.parse_args()

    print_banner()
    context = build_context()

    if args.json:
        console.print(json.dumps(context, indent=2))
    elif args.print:
        write_context_file(context)
    else:
        write_context_file(context)

if __name__ == "__main__":
    main()
