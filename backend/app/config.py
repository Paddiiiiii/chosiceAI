from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # DeepSeek LLM
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Embedding（Ollama 或 SiliconFlow）
    EMBEDDING_URL: str = "http://192.168.1.200:11434/api/embeddings"  # Ollama embedding API
    EMBEDDING_MODEL: str = "bge-large"
    EMBEDDING_DIM: int = 1024

    # Milvus（支持 Lite 模式和 Standalone 模式）
    MILVUS_URI: str = "./data/milvus.db"  # Lite模式：本地文件；Standalone模式：http://localhost:19530
    MILVUS_COLLECTION: str = "military_chunks"

    # Elasticsearch
    ES_URL: str = "http://localhost:9200"
    ES_INDEX: str = "military_manual"

    # Data directory
    DATA_DIR: str = "./data"

    # Search parameters
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    RRF_K: int = 60
    FINAL_TOP_K: int = 5

    # OCR correction
    OCR_CHUNK_SIZE: int = 1000

    # 部署模式
    DEPLOY_MODE: str = "local"  # local（直接部署）或 docker

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def data_path(self) -> Path:
        p = Path(self.DATA_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def docs_path(self) -> Path:
        p = self.data_path / "docs"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
