from sqlalchemy.orm import Session
from typing import List, Dict, Any


def get_on_order_quantity(db: Session, product_id: int) -> float:
    """
    Calculates the total quantity of a product currently on order but not yet received.
    Used by the recommendation engine's fresh cap formula.
    """
    # M1 TODO: Connect this to your actual PurchaseOrder SQLAlchemy models once finalized.
    # Example logic: query PurchaseOrder where status is 'pending' and sum the line items for this product.

    # Placeholder return until the database model is fully wired:
    return 0.0


def create_purchase_order(
    db: Session, supplier_id: int, expected_date: str, items: List[Dict[str, Any]]
):
    """
    Creates a new purchase order record in the database.
    """
    # M1 TODO: Insert into the purchase_orders table.
    # Plan requires: Supplier, status, expected date, lines.
    pass
