from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/inventory.db"
    business_timezone: str = "Asia/Kuala_Lumpur"
    app_name: str = "FreshStock API"
    forecast_package_root: str | None = None
    forecast_engine: str = "baseline"
    forecast_ml_config: str | None = None
    forecast_model_path: str | None = None
    forecast_history_days: int = 120
    store_id: str = "demo-store"
    import_max_rows: int = 20000
    ab_test_seed: str = "freshstock-demo"
    orbyte_base_url: str | None = None
    orbyte_api_token: str | None = None
    pos_webhook_secret: str | None = None
    pos_webhook_max_age_seconds: int = 300
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def business_today(self):
        return datetime.now(ZoneInfo(self.business_timezone)).date()
