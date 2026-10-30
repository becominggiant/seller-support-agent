from support.tools.ops_client import check_inventory, list_inventory, lookup_order


def test_lookup_order():
    o = lookup_order("ord-001")
    assert o["ok"] and o["customer_email"] == "alice@example.com" and o["product_name"] == "Minimal Phone Case"
    assert not lookup_order("ord-404")["ok"]


def test_inventory():
    assert check_inventory("sku-1001")["quantity_on_hand"] == 14
    assert len(list_inventory()["items"]) == 3
