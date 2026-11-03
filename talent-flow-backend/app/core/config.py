from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "TalentFlow Backend"
    APP_ENV: str = "dev"
    APP_DEBUG: bool = True

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "talent_flow"

    # 可选：直接覆盖拼装的 MySQL URL。
    # 生产留空走下面的 MySQL 拼装；本地验证可设为 sqlite:///./local.db
    DATABASE_URL: str | None = None

    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # LLM（OpenAI 兼容）配置，供 app/llm 统一封装读取
    LLM_MODEL: str = "deepseek-v4-pro"
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE: str | None = None
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT: int = 120  # 超时防止 API 挂起导致前端长时间等待 / 解析状态停在 processing
    LLM_MAX_RETRIES: int = 2  # 可重试错误（超时/连接中断/429/5xx）的最大重试次数，总尝试次数 = 1 + 该值
    LLM_RETRY_INITIAL_WAIT: float = 1.0  # 首次重试前等待秒数
    LLM_RETRY_MAX_WAIT: float = 10.0  # 单次重试最长等待秒数

    # OCR 兜底：pypdf 抽不到足够文本（扫描件）时触发
    OCR_ENABLED: bool = True
    OCR_MIN_CHARS: int = 50

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
