from fastapi import APIRouter

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/{product_id}")
def get_recommendation(product_id: int):
    return {"message": f"Recommendation for product {product_id} will go here (M3 TODO)"}
