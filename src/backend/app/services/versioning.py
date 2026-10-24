from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models

VERSION_MODELS = (
    models.ActivityEvent,
    models.StockMovement,
    models.StockoutEvent,
    models.StockActionRequest,
    models.PurchaseOrder,
    models.Batch,
)


def data_version(db: Session) -> int:
    """Monotonic token that changes whenever inventory or decision data changes."""
    values = [
        db.scalar(select(func.max(model.id)))
        for model in VERSION_MODELS
    ]
    return max((int(value or 0) for value in values), default=0)
