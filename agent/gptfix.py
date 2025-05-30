#!/usr/bin/env python3
import os, json, sys
from openai import OpenAI

print("🔥 GPTFIX STARTED", flush=True)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_PATH = os.path.join(ROOT, "build", "latest.log")
CONTEXT_PATH = os.path.join(ROOT, "agent", "gptcontext.json")

client = OpenAI()

def read_context():
    try:
        with open(CONTEXT_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def read_log_tail():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r") as f:
            content = f.read().strip()
            return content[-2000:] if len(content) > 2000 else content
    return ""

def build_prompt(context, log_tail, user_message):
    return [
        {
            "role": "system",
            "content": f"""You are a dev agent for a Cosmos SDK chain named Wolochain.

Context:
{json.dumps(context, indent=2)}

Recent build log:
{log_tail}

Respond with the root cause and suggested fix. No fluff. Just help."""
        },
        {
            "role": "user",
            "content": user_message or "Analyze the build log and return the fix."
        }
    ]

def run_gpt(messages):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[OpenAI Error] {str(e)}"

def main():
    context = read_context()
    log_tail = read_log_tail()

    if not log_tail:
        print("⚠️  Build log is empty. Nothing to analyze.")
        return

    user_message = " ".join(sys.argv[1:]).strip()
    messages = build_prompt(context, log_tail, user_message)

    print("🧠 GPT is analyzing the build error...\n")
    print(run_gpt(messages))

if __name__ == "__main__":
    main()
