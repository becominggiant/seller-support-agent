"""LangGraph pipeline: classify -> tools -> draft -> gate."""
from __future__ import annotations

import time
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from support.injection import detect_injection
from support.state import AUTO_SEND_CATEGORIES, CONFIDENCE_THRESHOLD, SupportState
from support.tools.ops_client import TOOL_REGISTRY, call_tool


def _backend(name: str):
    if name == "openai":
        from support.agents import openai_agent as b
    else:
        from support.agents import fixture as b
    return b


def _trace(state: SupportState, node: str, t0: float, **info: Any) -> list:
    return state.get("traces", []) + [{"node": node, "ms": round((time.perf_counter() - t0) * 1000, 3), **info}]


def classify_node(state: SupportState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    flags = detect_injection(state["message"])
    category, conf, _ = _backend(state.get("agent", "fixture")).classify(state["message"])
    return {"category": category, "confidence": conf, "injection_flags": flags,
            "traces": _trace(state, "classify", t0, category=category, confidence=conf, flags=flags)}


def tools_node(state: SupportState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    calls = _backend(state.get("agent", "fixture")).plan_tools(state["message"], state["category"])
    results = []
    for c in calls:
        if c["name"] not in TOOL_REGISTRY:  # allow-list
            continue
        results.append({"name": c["name"], "args": c["args"], "result": call_tool(c["name"], c["args"])})
    return {"tool_calls": calls, "tool_results": results,
            "traces": _trace(state, "tools", t0, calls=[c["name"] for c in calls])}


def draft_node(state: SupportState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    text = _backend(state.get("agent", "fixture")).draft(state["category"], state["message"], state.get("tool_results", []))
    return {"draft": text, "traces": _trace(state, "draft", t0)}


def gate_node(state: SupportState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    reasons = []
    if state["category"] not in AUTO_SEND_CATEGORIES:
        reasons.append(f"category '{state['category']}' requires human review")
    if state["confidence"] < CONFIDENCE_THRESHOLD:
        reasons.append(f"confidence {state['confidence']:.2f} < {CONFIDENCE_THRESHOLD}")
    if state.get("injection_flags"):
        reasons.append("injection flags: " + ", ".join(state["injection_flags"]))
    if any(not r["result"].get("ok") for r in state.get("tool_results", [])):
        reasons.append("tool lookup failed")
    decision = "escalate" if reasons else "auto_send"
    reason = "; ".join(reasons) or "low-risk category, high confidence, clean input"
    return {"decision": decision, "reason": reason, "traces": _trace(state, "gate", t0, decision=decision)}


def route_after_classify(state: SupportState) -> str:
    # Injected or spam messages skip tool calls entirely (no data access for attackers).
    if state.get("injection_flags") or state["category"] == "spam":
        return "draft"
    return "tools"


def build_graph():
    g = StateGraph(SupportState)
    g.add_node("classify", classify_node)
    g.add_node("tools", tools_node)
    g.add_node("draft", draft_node)
    g.add_node("gate", gate_node)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route_after_classify, {"tools": "tools", "draft": "draft"})
    g.add_edge("tools", "draft")
    g.add_edge("draft", "gate")
    g.add_edge("gate", END)
    return g.compile()


_GRAPH = None


def run_message(message: str, agent: str = "fixture") -> SupportState:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH.invoke({"message": message, "agent": agent, "traces": [], "tool_results": []})
