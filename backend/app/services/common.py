from fastapi import HTTPException

from app.models import ActivityEvent

APPROVER_ROLES = {"owner", "manager", "bookkeeper"}
STOCK_ROLES = APPROVER_ROLES | {"staff"}


def require_approver(actor):
    # Demonstration role selection only. This is NOT authentication.
    if actor.actor_role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="This role cannot approve this action")


def require_stock_actor(actor, movement_type: str):
    allowed = STOCK_ROLES if movement_type == "SALE" else APPROVER_ROLES
    if actor.actor_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Role {actor.actor_role} cannot record a {movement_type} action",
        )


def add_event(db, event_type, entity_type, entity_id, actor, payload=None):
    db.add(
        ActivityEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_name=actor.actor_name,
            reason=actor.reason,
            payload=payload or {},
        )
    )
