from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/inventory.db"
    business_timezone: str = "Asia/Kuala_Lumpur"
    app_name: str = "Perishable Food Inventory - M1 Backend"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def business_today(self):
        return datetime.now(ZoneInfo(self.business_timezone)).date()
