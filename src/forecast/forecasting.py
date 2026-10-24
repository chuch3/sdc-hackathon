from __future__ import annotations

from typing import Protocol

from .contracts import ForecastContext, ForecastRequest, ForecastResult
from .policies import DemandPolicy


class Forecaster(Protocol):
    def forecast(
        self,
        request: ForecastRequest,
        context: ForecastContext,
        policy: DemandPolicy | None = None,
    ) -> ForecastResult: ...
