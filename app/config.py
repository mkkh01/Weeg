from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "LINKUSDT","DOTUSDT","TRXUSDT","LTCUSDT","BCHUSDT","UNIUSDT","ETCUSDT","ATOMUSDT",
    "XLMUSDT","NEARUSDT","FILUSDT","APTUSDT","ARBUSDT","OPUSDT","INJUSDT","SUIUSDT",
    "SEIUSDT","ICPUSDT","VETUSDT","ALGOUSDT","AAVEUSDT","RENDERUSDT",
]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    supabase_url: str | None = None
    supabase_key: str | None = None
    redis_url: str | None = None
    binance_rest_url: str = "https://data-api.binance.vision"
    binance_ws_url: str = "wss://data-stream.binance.vision/stream,wss://stream.binance.us:9443/stream"
    symbols: str = ",".join(DEFAULT_SYMBOLS)
    default_interval: str = "15m"
    cors_origins: str = "*"
    confidence_threshold: int = 65
    minimum_rr: float = 2.0
    risk_per_trade: float = 0.005
    database_path: str = "weeg.db"

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",")]

@lru_cache
def get_settings() -> Settings:
    return Settings()
