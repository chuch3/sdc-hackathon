def apply_stock_action(db, action, as_of):
    """M2 replaces this body: FEFO allocation + ledger + idempotency in one transaction.

    Return a JSON-ready dict with request_id, product_id, allocations and outcome.
    Recheck expiry and status before deduction; never allow negative stock.
    A repeated request_id with identical input must not deduct stock twice.
    """
    raise NotImplementedError("M2 FEFO/stock-action service has not been connected yet")
