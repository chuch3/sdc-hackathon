from abc import ABC, abstractmethod
from typing import Any, Dict


class DemandPolicy(ABC):
    """Blueprint for weekday, daypart, and seasonal adjustments."""

    @abstractmethod
    def calculate_adjusted_demand(self, base_demand: float, date: Any, **kwargs) -> float:
        # Every domain must define how it calculates its specific demand
        pass


class PlanningPolicy(ABC):
    """Blueprint for purchase versus production logic."""

    @abstractmethod
    def generate_plan(self, forecast: float, current_stock: float, **kwargs) -> Dict[str, Any]:
        # Every domain must define whether to buy more or bake more
        pass


class AdvicePolicy(ABC):
    """Blueprint for markdown, donation, and seasonal recommendations."""

    @abstractmethod
    def get_recommendation(self, product_id: str, stock_data: Any, **kwargs) -> Dict[str, Any]:
        # Every domain must define when to discount or donate items
        pass
