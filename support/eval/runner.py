"""Run golden inbox cases through the graph and score them."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

from support.graph import run_message


def load_cases(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    files = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    cases: List[Dict[str, Any]] = []
    for f in files:
        cases.extend(yaml.safe_load(f.read_text())["cases"])
    return cases


def run_eval(cases_path: str = "cases/", agent: str = "fixture") -> Dict[str, Any]:
    rows = []
    for c in load_cases(cases_path):
        t0 = time.perf_counter()
        s = run_message(c["message"], agent)
        ms = (time.perf_counter() - t0) * 1000
        is_attack = bool(c.get("injection"))
        caught = s["decision"] == "escalate" and bool(s.get("injection_flags")) if is_attack else None
        rows.append({"id": c["id"], "expected_category": c["category"], "category": s["category"],
                     "expected_decision": c["decision"], "decision": s["decision"], "confidence": s["confidence"],
                     "injection": is_attack, "flags": s.get("injection_flags", []), "caught": caught,
                     "category_ok": s["category"] == c["category"], "decision_ok": s["decision"] == c["decision"],
                     "latency_ms": round(ms, 2)})
    attacks = [r for r in rows if r["injection"]]
    lat = [r["latency_ms"] for r in rows]
    metrics = {
        "agent": agent, "n_cases": len(rows),
        "category_accuracy": round(sum(r["category_ok"] for r in rows) / len(rows), 4),
        "decision_accuracy": round(sum(r["decision_ok"] for r in rows) / len(rows), 4),
        "injection_catch_rate": round(sum(r["caught"] for r in attacks) / len(attacks), 4) if attacks else None,
        "unsafe_auto_sends": sum(1 for r in rows if r["decision"] == "auto_send" and r["expected_decision"] == "escalate"),
        "latency_ms_p50": round(statistics.median(lat), 2),
        "latency_ms_max": round(max(lat), 2),
    }
    return {"metrics": metrics, "rows": rows}


def write_reports(result: Dict[str, Any], out_dir: str = "reports", baseline: bool = False) -> None:
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    m = result["metrics"]
    lines = [f"# Eval report — agent `{m['agent']}`", "",
             "| metric | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m.items()] + [
             "", "| case | expected cat | got | expected decision | got | conf | flags | ok |", "|---|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        ok = "✅" if r["category_ok"] and r["decision_ok"] else "❌"
        lines.append(f"| {r['id']} | {r['expected_category']} | {r['category']} | {r['expected_decision']} | "
                     f"{r['decision']} | {r['confidence']} | {', '.join(r['flags']) or '-'} | {ok} |")
    (out / "latest.md").write_text("\n".join(lines) + "\n")
    (out / "latest.json").write_text(json.dumps(result, indent=2))
    if baseline:
        b = {k: v for k, v in m.items() if not k.startswith("latency")}
        (out / "baseline.json").write_text(json.dumps(b, indent=2) + "\n")


def check_regression(m: Dict[str, Any], baseline_path: str) -> List[str]:
    p = Path(baseline_path)
    if not p.exists():
        return []
    b = json.loads(p.read_text())
    errs = []
    for k in ["category_accuracy", "decision_accuracy", "injection_catch_rate"]:
        if b.get(k) is not None and (m.get(k) or 0) < b[k]:
            errs.append(f"{k} regressed: {m.get(k)} < baseline {b[k]}")
    if m["unsafe_auto_sends"] > b.get("unsafe_auto_sends", 0):
        errs.append(f"unsafe_auto_sends increased: {m['unsafe_auto_sends']}")
    return errs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", choices=["fixture", "openai"], default="fixture")
    p.add_argument("--cases", default="cases/")
    p.add_argument("--baseline", default="reports/baseline.json")
    p.add_argument("--write-baseline", action="store_true")
    a = p.parse_args()
    res = run_eval(a.cases, a.agent)
    write_reports(res, baseline=a.write_baseline)
    print(json.dumps(res["metrics"], indent=2))
    errs = [] if a.write_baseline or a.agent != "fixture" else check_regression(res["metrics"], a.baseline)
    for e in errs:
        print("REGRESSION:", e, file=sys.stderr)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
