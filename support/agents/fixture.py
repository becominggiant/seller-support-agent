"""Rule-based agent: keyword + regex heuristics. No API key, deterministic."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

KEYWORDS = {
    "refund": ["refund", "money back", "chargeback", "return", "damaged", "broken", "cancel", "wrong item", "never arrived"],
    "shipping": ["where is", "shipped", "shipping", "tracking", "track", "deliver", "arrive", "status of my order", "when will"],
    "product_question": ["in stock", "available", "do you have", "size", "fit", "compatible", "how many", "restock", "material"],
    "spam": ["crypto", "seo services", "click here", "winner", "free followers", "guaranteed income", "promote your", "bitcoin"],
}
ORDER_RE = re.compile(r"\bord-\d{3,}\b", re.I)
SKU_RE = re.compile(r"\bsku-\d{4}\b", re.I)
UNANSWERABLE = ["compatible", "fit", "size", "material", "dimensions", "waterproof"]
NAME_TO_SKU = {"phone case": "sku-1001", "cable organizer": "sku-1002", "travel bottle": "sku-1003"}


def classify(message: str) -> Tuple[str, float, Dict[str, int]]:
    t = message.lower()
    hits = {cat: sum(1 for k in kws if k in t) for cat, kws in KEYWORDS.items()}
    if ORDER_RE.search(t):
        hits["shipping"] += 1 if hits["refund"] == 0 else 0
    if SKU_RE.search(t) or any(n in t for n in NAME_TO_SKU):
        hits["product_question"] += 1 if hits["refund"] == 0 and hits["shipping"] == 0 else 0
    # money words dominate: any refund signal wins (routes to human)
    if hits["refund"]:
        best = "refund"
    else:
        best = max(hits, key=hits.get)
    total = sum(hits.values())
    if total == 0:
        return "other", 0.4, hits
    share = hits[best] / total
    conf = min(0.99, 0.55 + 0.2 * hits[best] + 0.2 * share - 0.2)
    # Attributes our ops data cannot answer (fit/compatibility/material) -> cap confidence
    # so the gate escalates instead of auto-sending a guess. Added after eval case prod-03.
    if best == "product_question" and any(k in t for k in UNANSWERABLE):
        conf = min(conf, 0.6)
    return best, round(conf, 2), hits


def plan_tools(message: str, category: str) -> List[Dict[str, Any]]:
    t = message.lower()
    calls: List[Dict[str, Any]] = []
    for oid in dict.fromkeys(m.lower() for m in ORDER_RE.findall(t)):
        calls.append({"name": "lookup_order", "args": {"order_id": oid}})
    skus = [m.lower() for m in SKU_RE.findall(t)] + [s for n, s in NAME_TO_SKU.items() if n in t]
    for sku in dict.fromkeys(skus):
        calls.append({"name": "check_inventory", "args": {"product_id": sku}})
    if category == "product_question" and not skus:
        calls.append({"name": "list_inventory", "args": {}})
    return calls


def draft(category: str, message: str, results: List[Dict[str, Any]]) -> str:
    lines = ["Hi there, thanks for reaching out!"]
    for r in results:
        out = r["result"]
        if not out.get("ok"):
            lines.append(f"I couldn't find that ({out.get('error')}); a team member will follow up.")
        elif r["name"] == "lookup_order":
            lines.append(f"Order {out['id']} ({out['quantity']}x {out['product_name']}) is currently "
                         f"'{out['status']}' with shipping status '{out['shipping_status'].replace('_', ' ')}'.")
        elif r["name"] == "check_inventory":
            stock = f"in stock ({out['quantity_on_hand']} available)" if out["in_stock"] else "out of stock"
            lines.append(f"{out['name']} ({out['product_id']}) is {stock} at ${out['price']:.2f}.")
        elif r["name"] == "list_inventory":
            items = ", ".join(f"{i['name']} ({i['quantity_on_hand']})" for i in out["items"])
            lines.append(f"Here's what we currently have in stock: {items}.")
    if category == "refund":
        lines.append("I've passed your request to the shop owner, who reviews all refunds and returns personally.")
    elif category in ("other", "spam") or len(lines) == 1:
        lines.append("A team member will get back to you shortly.")
    lines.append("— Becoming Giant Support")
    return "\n".join(lines)
