"""Reciprocal Rank Fusion (RRF) 算法实现"""
from typing import Dict, List, Optional


def rrf_fuse(
    result_lists: List[List[Dict]],
    k: int = 60,
    id_key: str = "chunk_id",
    weights: Optional[List[float]] = None,
) -> List[Dict]:
    """
    RRF 融合多路检索结果。

    Args:
        result_lists: 多路检索结果列表，每路为 [{"chunk_id": ..., "score": ...}, ...]
        k: RRF 参数（默认 60）
        id_key: 结果中文档 ID 的字段名
        weights: 与 result_lists 等长的通道权重；None 表示全为 1.0

    Returns:
        融合后的结果列表，按 rrf_score 降序排列
    """
    rrf_scores: Dict[str, float] = {}
    doc_data: Dict[str, Dict] = {}

    n = len(result_lists)
    w = weights if weights is not None and len(weights) == n else None

    for i, result_list in enumerate(result_lists):
        weight = w[i] if w is not None else 1.0
        for rank, doc in enumerate(result_list, start=1):
            doc_id = doc[id_key]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + weight / (k + rank)
            if doc_id not in doc_data:
                doc_data[doc_id] = doc.copy()

    # 按 rrf_score 降序排列
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for doc_id in sorted_ids:
        item = doc_data[doc_id].copy()
        item["rrf_score"] = rrf_scores[doc_id]
        results.append(item)

    return results
