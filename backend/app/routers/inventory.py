from fastapi import APIRouter

router = APIRouter(prefix="/inventory", tags=["Inventory & Batches"])


@router.get("/batches")
def get_batches():
    return {"message": "List of inventory batches will go here (M1/M2 TODO)"}
