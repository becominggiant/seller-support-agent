"""Ops tools for the support agent.

Default mode is in-process sample data that mirrors the sample store in
whatnot-automation-agent (app/data/store.py). If WHATNOT_OPS_URL is set,
list_inventory() / check_inventory() read GET {WHATNOT_OPS_URL}/inventory
from that FastAPI service instead. Orders are always served from the
in-process sample (the upstream API has no GET-by-id order route).
"""
from __future__ import annotations

import copy
import os
from typing import Any, Callable, Dict

PRODUCTS: Dict[str, Dict[str, Any]] = {
    "sku-1001": {"id": "sku-1001", "name": "Minimal Phone Case", "category": "phone accessories", "price": 14.99},
    "sku-1002": {"id": "sku-1002", "name": "Cable Organizer", "category": "desk accessories", "price": 9.99},
    "sku-1003": {"id": "sku-1003", "name": "Travel Bottle Set", "category": "wellness", "price": 18.99},
}
INVENTORY: Dict[str, Dict[str, Any]] = {
    "sku-1001": {"product_id": "sku-1001", "quantity_on_hand": 14, "reorder_level": 10, "lead_time_days": 4},
    "sku-1002": {"product_id": "sku-1002", "quantity_on_hand": 8, "reorder_level": 12, "lead_time_days": 5},
    "sku-1003": {"product_id": "sku-1003", "quantity_on_hand": 22, "reorder_level": 10, "lead_time_days": 6},
}
ORDERS: Dict[str, Dict[str, Any]] = {
    "ord-001": {"id": "ord-001", "product_id": "sku-1001", "quantity": 2, "selling_price": 14.99, "status": "pending",
                "payment_status": "paid", "shipping_status": "not_started", "customer_email": "alice@example.com"},
    "ord-002": {"id": "ord-002", "product_id": "sku-1002", "quantity": 1, "selling_price": 9.99, "status": "shipped",
                "payment_status": "paid", "shipping_status": "in_transit", "customer_email": "bob@example.com"},
}


def _remote_inventory() -> Dict[str, Dict[str, Any]] | None:
    url = os.getenv("WHATNOT_OPS_URL")
    if not url:
        return None
    import httpx

    resp = httpx.get(url.rstrip("/") + "/inventory", timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "inventory" in data:
        data = data["inventory"]
    if isinstance(data, list):
        data = {row["product_id"]: row for row in data}
    return data


def list_inventory() -> Dict[str, Any]:
    inv = _remote_inventory() or INVENTORY
    return {"ok": True, "items": [
        {**copy.deepcopy(row), "name": PRODUCTS.get(pid, {}).get("name", pid)} for pid, row in inv.items()]}


def check_inventory(product_id: str) -> Dict[str, Any]:
    inv = _remote_inventory() or INVENTORY
    row = inv.get(product_id)
    if row is None:
        return {"ok": False, "error": f"unknown product {product_id}"}
    prod = PRODUCTS.get(product_id, {})
    return {"ok": True, "product_id": product_id, "name": prod.get("name"), "price": prod.get("price"),
            "quantity_on_hand": row["quantity_on_hand"], "in_stock": row["quantity_on_hand"] > 0}


def lookup_order(order_id: str) -> Dict[str, Any]:
    order = ORDERS.get(order_id)
    if order is None:
        return {"ok": False, "error": f"unknown order {order_id}"}
    out = copy.deepcopy(order)
    out["product_name"] = PRODUCTS[order["product_id"]]["name"]
    return {"ok": True, **out}


# MCP-style registry: name -> (callable, JSON schema). Not an MCP server.
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "lookup_order": {"fn": lookup_order, "description": "Look up an order by id (e.g. ord-001).",
                     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}},
    "check_inventory": {"fn": check_inventory, "description": "Check stock for a product id (e.g. sku-1001).",
                        "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    "list_inventory": {"fn": list_inventory, "description": "List all inventory with product names.",
                       "parameters": {"type": "object", "properties": {}}},
}


def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    fn: Callable[..., Dict[str, Any]] = TOOL_REGISTRY[name]["fn"]
    return fn(**args)
