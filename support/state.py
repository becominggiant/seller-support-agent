from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SupportState(TypedDict, total=False):
    message: str
    category: str
    confidence: float
    injection_flags: List[str]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    draft: str
    decision: str  # auto_send | escalate
    reason: str
    traces: List[Dict[str, Any]]
    agent: str
    error: Optional[str]


CATEGORIES = ["shipping", "refund", "product_question", "spam", "other"]
AUTO_SEND_CATEGORIES = {"shipping", "product_question"}
CONFIDENCE_THRESHOLD = 0.85
