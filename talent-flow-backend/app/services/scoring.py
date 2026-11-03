"""匹配分计算：纯函数，与前端 matchScore.js 的 ALGO_SETTINGS 公式保持一致。"""

from ..models import JobFit, RequirementItem
from ..schemas.requirement import RecalculatePayload


def _item_score(suggestion: str) -> float:
    """单项得分：满足=1，证据不足=0.5，不满足=0"""
    if suggestion == "满足":
        return 1.0
    if suggestion == "证据不足":
        return 0.5
    return 0.0


def calc_match_score(items: list[RequirementItem], fits: list[JobFit], params: RecalculatePayload) -> dict:
    """按前端 ALGO_SETTINGS 相同公式计算匹配得分与各建议项个数"""
    if not items or not fits:
        return {"score": 0, "must_satisfied": 0, "must_unsatisfied": 0, "must_insufficient": 0, "bonus_satisfied": 0}
    fit_map = {f.requirement_item_id: f.suggestion for f in fits}
    weights = params.weights

    must_weight_sum = 0.0
    must_earn = 0.0
    must_satisfied = must_unsatisfied = must_insufficient = bonus_satisfied = 0
    for it in items:
        suggestion = fit_map.get(it.id, "不满足")
        s = _item_score(suggestion)
        if it.type == "加分":
            if s == 1:
                bonus_satisfied += 1
        else:
            weight = weights.get(it.importance, 35)
            must_weight_sum += weight
            must_earn += weight * s
            if suggestion == "满足":
                must_satisfied += 1
            elif suggestion == "证据不足":
                must_insufficient += 1
            else:
                must_unsatisfied += 1

    if must_weight_sum == 0:
        return {"score": 0, "must_satisfied": must_satisfied, "must_unsatisfied": must_unsatisfied,
                "must_insufficient": must_insufficient, "bonus_satisfied": bonus_satisfied}

    must_total = must_satisfied + must_unsatisfied + must_insufficient
    base = (100 * must_earn) / must_weight_sum
    gate_pass = must_total == 0 or (must_satisfied / must_total) * 100 >= params.must_gate
    final = base if gate_pass else min(base, params.recommend_threshold - 1)
    final += min(6, 2 * bonus_satisfied)
    return {
        "score": max(0, min(100, round(final))),
        "must_satisfied": must_satisfied,
        "must_unsatisfied": must_unsatisfied,
        "must_insufficient": must_insufficient,
        "bonus_satisfied": bonus_satisfied,
    }
