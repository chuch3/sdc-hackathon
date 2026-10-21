import math
from datetime import date
from typing import Any, Dict
from app.domains.base import DemandPolicy, PlanningPolicy, AdvicePolicy


class GenericPerishablePolicy(DemandPolicy, PlanningPolicy, AdvicePolicy):
    """Generic domain implementation for standard inventory (dairy, meat, produce)."""

    # 1. Demand Adjustment Logic
    def calculate_adjusted_demand(self, base_demand: float, target_date: date, **kwargs) -> float:
        """Standard perishables use a simpler forecast based on promotional multipliers."""
        # Generic items don't typically use daypart splitting or massive weekend spikes
        promotional_factor = kwargs.get("promotional_factor", 1.0)
        return round(base_demand * promotional_factor, 2)

    # 2. Purchase Planning Logic (Instead of Baking)
    def generate_plan(self, forecast: float, current_stock: float, **kwargs) -> Dict[str, Any]:
        """Calculates how much to buy based on the plan's 'fresh cap' formula."""
        lead_time = kwargs.get("lead_time", 1)
        review_period = kwargs.get("review_period", 1)
        safety_stock = kwargs.get("safety_stock", 0.0)
        on_order = kwargs.get("on_order", 0.0)
        remaining_shelf_life = kwargs.get("remaining_shelf_life", 7)
        moq = kwargs.get("moq", 1)  # Minimum Order Quantity

        # Reorder Point calculation
        horizon_days = lead_time + review_period
        rop = (forecast * horizon_days) + safety_stock

        # Raw order needed
        raw_order = rop - current_stock - on_order

        # Fresh cap: Don't order more than we can sell before it expires
        fresh_cap_days = min(remaining_shelf_life, horizon_days)
        fresh_cap = (forecast * fresh_cap_days) - current_stock

        # Recommended order quantity
        recommended_qty = max(0, min(raw_order, fresh_cap))

        # Round up to match supplier Minimum Order Quantity case sizes
        if recommended_qty > 0:
            recommended_qty = math.ceil(recommended_qty / moq) * moq

        action = "BUY" if recommended_qty > 0 else "HOLD"

        return {
            "recommended_order_quantity": recommended_qty,
            "rop": rop,
            "capped_by_freshness": fresh_cap < raw_order,
            "action": action,
        }

    # 3. Expiry Risk & Markdown Advice
    def get_recommendation(self, product_id: str, stock_data: Any, **kwargs) -> Dict[str, Any]:
        """Provides advice based on the Expiry Risk buckets."""
        days_to_expiry = kwargs.get("days_to_expiry", 99)
        category_threshold = kwargs.get("category_threshold", 2)  # e.g., 2 days for produce

        if days_to_expiry < 0:
            action = "WRITE OFF"
            advice = "Product is expired. Do not sell. Remove from shelves immediately."
        elif days_to_expiry <= category_threshold:
            action = "MARKDOWN / DONATE"
            advice = "Critical risk. Markdown if expected sales are lower than stock, otherwise route to donation."
        elif days_to_expiry <= 2 * category_threshold:
            action = "WARNING"
            advice = "Approaching critical expiry threshold. Monitor sales."
        else:
            action = "HOLD"
            advice = "Stock is healthy."

        return {
            "product_id": product_id,
            "days_to_expiry": days_to_expiry,
            "action": action,
            "advice": advice,
        }
