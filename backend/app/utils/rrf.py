"""Reciprocal Rank Fusion (RRF) 算法实现"""
from typing import List, Dict


def rrf_fuse(
    result_lists: List[List[Dict]],
    k: int = 60,
    id_key: str = "chunk_id",
) -> List[Dict]:
    """
    RRF 融合多路检索结果。

    Args:
        result_lists: 多路检索结果列表，每路为 [{"chunk_id": ..., "score": ...}, ...]
        k: RRF 参数（默认 60）
        id_key: 结果中文档 ID 的字段名

    Returns:
        融合后的结果列表，按 rrf_score 降序排列
    """
    rrf_scores: Dict[str, float] = {}
    doc_data: Dict[str, Dict] = {}

    for result_list in result_lists:
        for rank, doc in enumerate(result_list, start=1):
            doc_id = doc[id_key]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
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
