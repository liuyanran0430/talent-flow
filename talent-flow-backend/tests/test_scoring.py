"""calc_match_score 纯函数单测：权重加权、must_gate 封顶、加分项加成。"""

from app.models import JobFit, RequirementItem
from app.schemas.requirement import RecalculatePayload
from app.services.scoring import calc_match_score


def _item(i, type_="必须", importance="高"):
    return RequirementItem(id=i, job_id=1, name=f"项{i}", type=type_, importance=importance)


def _fit(item_id, suggestion):
    return JobFit(id=item_id, candidate_id=1, requirement_item_id=item_id, suggestion=suggestion)


def test_weighted_score_all_satisfied():
    items = [_item(1, importance="高"), _item(2, importance="低")]
    fits = [_fit(1, "满足"), _fit(2, "满足")]
    params = RecalculatePayload()
    result = calc_match_score(items, fits, params)
    assert result["score"] == 100
    assert result["must_satisfied"] == 2


def test_weighted_score_partial():
    # 高权重满足(45) + 中权重不满足(35) → base = 45/80*100 ≈ 56
    items = [_item(1, importance="高"), _item(2, importance="中")]
    fits = [_fit(1, "满足"), _fit(2, "不满足")]
    result = calc_match_score(items, fits, RecalculatePayload())
    assert result["score"] == 56
    assert result["must_unsatisfied"] == 1


def test_must_gate_caps_score():
    # 满足率 1/2 = 50% < 80% 门槛 → 分数封顶到 threshold-1 = 74
    items = [_item(1, importance="高"), _item(2, importance="高")]
    fits = [_fit(1, "满足"), _fit(2, "证据不足")]
    params = RecalculatePayload(must_gate=80, recommend_threshold=75)
    result = calc_match_score(items, fits, params)
    # base = (45*1 + 45*0.5)/90*100 = 75，门槛不过 → min(75, 74) = 74
    assert result["score"] == 74
    assert result["must_insufficient"] == 1


def test_bonus_adds_points_capped_at_6():
    # 基本项：1 满足 + 1 不满足 → base = 50（不会被 100 上限吃掉加成幅度）
    items = [
        _item(1),
        _item(2),
        _item(3, type_="加分"),
        _item(4, type_="加分"),
        _item(5, type_="加分"),
        _item(6, type_="加分"),
    ]
    fits = [
        _fit(1, "满足"),
        _fit(2, "不满足"),
        _fit(3, "满足"),
        _fit(4, "满足"),
        _fit(5, "满足"),
        _fit(6, "满足"),
    ]
    result = calc_match_score(items, fits, RecalculatePayload())
    assert result["bonus_satisfied"] == 4
    # base 50（基本项满足率 50% 未过 80% 门槛 → 封顶 74，最终取 50）+ min(6, 2*4)
    assert result["score"] == 56


def test_bonus_points_capped_even_when_base_low():
    """加分项最多 +6：4 个满足 → +6 而不是 +8；1 个满足 → +2。"""
    items = [_item(1), _item(2, type_="加分"), _item(3, type_="加分"), _item(4, type_="加分"), _item(5, type_="加分")]
    fits = [_fit(1, "满足"), _fit(2, "满足"), _fit(3, "满足"), _fit(4, "满足"), _fit(5, "满足")]
    assert calc_match_score(items, fits, RecalculatePayload())["score"] == 100  # 100 + 6 仍封顶 100

    items = [_item(1), _item(2, type_="加分")]
    fits = [_fit(1, "满足"), _fit(2, "满足")]
    assert calc_match_score(items, fits, RecalculatePayload())["score"] == 100  # base 100 +2 → 封顶

    items = [_item(1), _item(2), _item(3, type_="加分")]
    fits = [_fit(1, "满足"), _fit(2, "不满足"), _fit(3, "满足")]
    assert calc_match_score(items, fits, RecalculatePayload())["score"] == 52  # 50 + 2


def test_missing_fit_treated_as_unsatisfied():
    """要求项没有对应建议时按「不满足」计入，不能漏算进分母。"""
    items = [_item(1), _item(2)]
    fits = [_fit(1, "满足")]
    result = calc_match_score(items, fits, RecalculatePayload())
    assert result["must_satisfied"] == 1
    assert result["must_unsatisfied"] == 1
    assert result["must_insufficient"] == 0
    assert result["score"] == 50  # base 50，门槛 50% 未过 → min(50, 74)


def test_unknown_importance_falls_back_to_weight_35():
    """importance 不在 高/中/低 时权重回退 35。"""
    items = [_item(1, importance="紧急"), _item(2, importance="紧急")]
    fits = [_fit(1, "满足"), _fit(2, "不满足")]
    result = calc_match_score(items, fits, RecalculatePayload())
    # (35*1 + 35*0)/70 * 100 = 50
    assert result["score"] == 50
    assert result["must_satisfied"] == 1


def test_only_bonus_items_scores_zero():
    """全是加分项时 must_weight_sum=0，避免除零，得分为 0 但加分统计正确。"""
    items = [_item(1, type_="加分"), _item(2, type_="加分")]
    fits = [_fit(1, "满足"), _fit(2, "不满足")]
    result = calc_match_score(items, fits, RecalculatePayload())
    assert result["score"] == 0
    assert result["bonus_satisfied"] == 1
    assert result["must_satisfied"] == 0


def test_must_gate_exactly_at_threshold_passes():
    """满足率正好等于门槛（80%）时放行，不做封顶。"""
    items = [_item(i) for i in range(1, 6)]
    fits = [_fit(i, "满足") for i in range(1, 5)] + [_fit(5, "不满足")]
    result = calc_match_score(items, fits, RecalculatePayload(must_gate=80, recommend_threshold=75))
    assert result["score"] == 80  # 4/5 = 80% 通过，base 80 不封顶


def test_just_below_gate_gets_capped():
    """满足率低于门槛时封顶到 threshold-1。"""
    items = [_item(i) for i in range(1, 9)]
    fits = [_fit(i, "满足") for i in range(1, 7)] + [_fit(7, "不满足"), _fit(8, "不满足")]
    result = calc_match_score(items, fits, RecalculatePayload(must_gate=80, recommend_threshold=75))
    assert result["score"] == 74  # 6/8 = 75% 未过，base 75 → min(75, 74)


def test_empty_inputs():
    assert calc_match_score([], [], RecalculatePayload())["score"] == 0
    # 有要求项但完全没有匹配建议 → 直接返回 0
    assert calc_match_score([_item(1)], [], RecalculatePayload())["score"] == 0
