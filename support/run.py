import argparse
import json

from support.graph import run_message


def main() -> None:
    p = argparse.ArgumentParser(description="Triage one inbound buyer message.")
    p.add_argument("--message", required=True)
    p.add_argument("--agent", choices=["fixture", "openai"], default="fixture")
    a = p.parse_args()
    s = run_message(a.message, a.agent)
    print(json.dumps({k: s.get(k) for k in ["category", "confidence", "injection_flags", "tool_results",
                                            "decision", "reason", "draft", "traces"]}, indent=2))


if __name__ == "__main__":
    main()
