from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # DeepSeek LLM
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Embedding（主通道 Ollama，备用 SiliconFlow）
    EMBEDDING_URL: str = "http://192.168.1.200:11434/api/embeddings"  # Ollama embedding API
    EMBEDDING_MODEL: str = "bge-large"
    EMBEDDING_DIM: int = 1024
    # 向量检索时拼在 query 前（如 BGE 系列常用检索指令）；留空则不改写 query
    EMBEDDING_QUERY_PREFIX: str = ""

    # SiliconFlow 备用 Embedding（主通道失败时使用）
    SILICONFLOW_API_KEY: str = "sk-xtpojqrgbqomvlyvtlvpmwbjfpwynbbrqsekxvotxkoxqerw"
    SILICONFLOW_EMBEDDING_URL: str = "https://api.siliconflow.cn/v1/embeddings"
    SILICONFLOW_EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"  # 1024 维，与主通道兼容

    # Milvus（Docker standalone，见 docker/milvus-standalone-compose.yml）
    MILVUS_HOST: str = "127.0.0.1"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "military_chunks"

    # Elasticsearch
    ES_URL: str = "http://localhost:9200"
    ES_INDEX: str = "military_manual"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123456"

    # Data directory
    DATA_DIR: str = "./data"

    # Search parameters（单路调试接口仍用 VECTOR_TOP_K / BM25_TOP_K）
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    # 混合检索每路先取更多候选再 RRF，提高召回与融合效果
    HYBRID_PER_CHANNEL_TOP_K: int = 24
    RRF_K: int = 60
    # 各路对 RRF 贡献权重（图谱全文相对更噪，默认略低于向量）
    RRF_WEIGHT_VECTOR: float = 1.15
    RRF_WEIGHT_BM25: float = 1.0
    RRF_WEIGHT_GRAPH: float = 0.9
    FINAL_TOP_K: int = 5

    # 重排（SiliconFlow /v1/rerank，或其它兼容接口）；未配置密钥时自动跳过
    RERANK_ENABLED: bool = True
    RERANK_API_URL: str = "https://api.siliconflow.cn/v1/rerank"
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_API_KEY: str = ""  # 为空则使用 SILICONFLOW_API_KEY
    RERANK_CANDIDATE_POOL: int = 24  # RRF 后取前 N 条送入重排模型
    RERANK_MAX_DOC_CHARS: int = 800
    RERANK_TIMEOUT: float = 45.0

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
