"""Deterministic prompt-injection / exfiltration detector (runs before any LLM)."""
from __future__ import annotations

import re
from typing import List

PATTERNS = {
    "override_instructions": r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all|your)\b.{0,20}\b(instructions|rules|prompt)",
    "system_prompt_leak": r"\b(reveal|show|print|repeat|output)\b.{0,40}\b(system prompt|instructions|hidden prompt|developer message)",
    "role_hijack": r"\b(you are now|act as|pretend to be|new role)\b",
    "exfil_external_email": r"\b(send|email|forward|transfer|wire)\b.{0,60}@(?!example\.com)[a-z0-9.-]+\.[a-z]{2,}",
    "tool_abuse": r"\b(list|dump|export)\b.{0,30}\b(all (orders|customers|emails)|customer (list|emails|data))",
    "fake_authority": r"\b(i am|this is)\b.{0,20}\b(the (admin|owner|seller|developer)|support staff)\b",
}


def detect_injection(text: str) -> List[str]:
    t = text.lower()
    return [name for name, pat in PATTERNS.items() if re.search(pat, t)]
