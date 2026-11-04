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

    FRONTEND_ORIGIN: str = "http://localhost:3001"

    # LLM（OpenAI 兼容）配置，供 app/llm 统一封装读取
    LLM_MODEL: str = "deepseek-v4-pro"
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE: str | None = None
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT: int = 120  # 单次请求硬超时（秒）：防止 API 挂起导致前端长时间等待 / 解析状态停在 processing
    LLM_MAX_TOKENS: int = 4000  # 单次输出 token 上限：配合输入截断，避免 prompt+输出超出模型上下文窗口
    # 429 限流/超时/连接中断/5xx：指数退避重试，默认 1s/2s/4s（共 3 次重试）
    LLM_MAX_RETRIES: int = 3  # 最大重试次数，总尝试次数 = 1 + 该值；退避序列 1s/2s/4s
    LLM_RETRY_INITIAL_WAIT: float = 1.0  # 首次重试前等待秒数
    LLM_RETRY_MAX_WAIT: float = 10.0  # 单次重试最长等待秒数
    LLM_RETRY_JITTER: float = 0.0  # 退避随机抖动秒数；0 = 严格 1s/2s/4s，可调大避免并发惊群

    # OCR 兜底：pypdf 抽不到足够文本（扫描件）时触发
    OCR_ENABLED: bool = True
    OCR_MIN_CHARS: int = 50

    # ---------- RAG / 岗位标准知识库 ----------
    RAG_ENABLED: bool = True  # 关闭后所有检索直接返回空，走纯 LLM 降级链路
    RAG_TOP_K: int = 3  # 每次检索返回的标准条数
    RAG_MIN_SCORE: float = 0.60  # 相似度阈值，低于该值的召回结果丢弃
    EMBEDDING_MODEL: str = "text-embedding-v4"  # DashScope 向量模型
    EMBEDDING_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_API_KEY: str | None = None  # 未配置时 RAG 自动降级，不影响主流程
    VECTOR_STORE_BACKEND: str = "chroma"  # chroma / null
    VECTOR_STORE_PATH: str = "data/vector_store"  # 本地向量持久化目录
    RAG_REBUILD_BATCH: int = 32  # 重建索引时每批向量化的条数

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
