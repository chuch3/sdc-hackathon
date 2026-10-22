from __future__ import annotations

import os
from typing import Any

import requests


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self.session.request(
                method, self._url(path), timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise ApiError(0, f"API unavailable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if isinstance(detail, list):
                detail = "; ".join(str(item) for item in detail)
            raise ApiError(response.status_code, str(detail))
        if response.status_code == 204:
            return None
        return response.json()

    def get(self, path: str, params: dict | None = None):
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict | None = None, params: dict | None = None):
        return self._request("POST", path, json=payload or {}, params=params)

    def put(self, path: str, payload: dict | None = None):
        return self._request("PUT", path, json=payload or {})

    def patch(self, path: str, payload: dict | None = None):
        return self._request("PATCH", path, json=payload or {})

    def health(self):
        root = self.base_url.rsplit("/api/", 1)[0]
        try:
            response = self.session.get(f"{root}/health", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise ApiError(0, f"API unavailable at {root}: {exc}") from exc

    def products(self):
        return self.get("products", {"limit": 200})

    def suppliers(self):
        return self.get("suppliers")

    def positions(self):
        return self.get("inventory/positions")

    def batches(self, product_id: int | None = None):
        params = {"limit": 500}
        if product_id:
            params["product_id"] = product_id
        return self.get("batches", params)

    def movements(self, product_id: int | None = None):
        params = {"limit": 100}
        if product_id:
            params["product_id"] = product_id
        return self.get("movements", params)

    def expiry_buckets(self):
        return self.get("expiry/buckets")

    def expiry_alerts(self, horizon_days: int = 3):
        return self.get("expiry/alerts", {"horizon_days": horizon_days})

    def recommendations(self, domain: str | None = None):
        params = {}
        if domain:
            params["domain"] = domain
        return self.get("recommendations", params)

    def planner_week(self, start: str | None = None):
        params = {}
        if start:
            params["start"] = start
        return self.get("planner/week", params)

    def activity_calendar(self, days: int = 120):
        return self.get("analytics/activity-calendar", {"days": days})

    def recommend(self, product_id: int):
        return self.get(f"recommendations/{product_id}")

    def decide(self, product_id: int, actor: dict):
        return self.post(f"recommendations/{product_id}/decision", actor)

    def stock_action(self, payload: dict):
        return self.post("stock-actions", payload)

    def adjustment(self, payload: dict):
        return self.post("stock-adjustments", payload)

    def receive_batch(self, payload: dict):
        return self.post("batches", payload)

    def purchase_orders(self):
        return self.get("purchase-orders")

    def create_purchase_order(self, payload: dict):
        return self.post("purchase-orders", payload)

    def approve_purchase_order(self, order_id: int, actor: dict):
        return self.post(f"purchase-orders/{order_id}/approve", actor)

    def receive_purchase_order(self, order_id: int, payload: dict):
        return self.post(f"purchase-orders/{order_id}/receive", payload)

    def on_order(self, product_id: int):
        return self.get(f"products/{product_id}/on-order")

    def bakery_profiles(self):
        return self.get("bakery/profiles")

    def bake_plan(self, plan_date: str):
        return self.get("bakery/bake-plan", {"plan_date": plan_date})

    def create_bake_plan(self, plan_date: str, product_id: int, actor: dict):
        return self.post(
            "bakery/bake-plan",
            {"plan_date": plan_date, "product_id": product_id, **actor},
        )

    def approve_bake_plan(self, product_id: int, plan_date: str, actor: dict):
        return self.post(
            f"bakery/bake-plan/{product_id}/approve",
            actor,
            params={"plan_date": plan_date},
        )

    def seasonal_advice(self):
        return self.get("bakery/seasonal-advice")

    def holidays(self):
        return self.get("holidays")

    def activity(self):
        return self.get("activity", {"limit": 40})

    def orbyte_status(self):
        return self.get("integrations/orbyte")
