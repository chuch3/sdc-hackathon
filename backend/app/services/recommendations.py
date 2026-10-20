from app.schemas import Recommendation


def recommend(db, product_id: int, as_of) -> Recommendation:
    """M3 replaces this body. M1 owns the HTTP endpoint, M3 owns the calculation.

    Read Product/Batch/StockMovement/PurchaseOrder through the SAME SQLAlchemy session.
    Return an app.schemas.Recommendation. Do not commit stock changes here.
    """
    raise NotImplementedError("M3 forecast/reorder service has not been connected yet")
