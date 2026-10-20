from fastapi import HTTPException

from app.models import ActivityEvent


def require_approver(actor):
    # Demonstration role selection only. This is NOT authentication.
    if actor.actor_role not in {"owner", "bookkeeper"}:
        raise HTTPException(status_code=403, detail="A viewer cannot approve this action")


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
