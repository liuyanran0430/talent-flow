"""问题分类器：把用户问题归入六类之一。

只输出一个类别名；输出非法时重试一次，仍非法归为 ambiguous，不抛出异常。
"""

import re

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.config import settings
from ..core.logging_config import get_logger
from ..llm.client import ModelClient

logger = get_logger("qa")

JOB_ABILITY = "job_ability"
INTERVIEW_EVAL = "interview_eval"
PROCESS_RULE = "process_rule"
BUSINESS_FAQ = "business_faq"
OUT_OF_SCOPE = "out_of_scope"
AMBIGUOUS = "ambiguous"

CATEGORIES = (JOB_ABILITY, INTERVIEW_EVAL, PROCESS_RULE, BUSINESS_FAQ, OUT_OF_SCOPE, AMBIGUOUS)

# 同义词映射：模型可能输出中文名或简写，统一到合法标识
_ALIASES: dict[str, tuple[str, ...]] = {
    JOB_ABILITY: ("job_ability", "岗位能力标准", "岗位能力", "岗位标准"),
    INTERVIEW_EVAL: ("interview_eval", "面试评价规范", "面试评价", "面试标准"),
    PROCESS_RULE: ("process_rule", "招聘阶段规则", "招聘阶段", "流程规则"),
    BUSINESS_FAQ: ("business_faq", "招聘业务FAQ", "招聘业务faq", "业务FAQ", "FAQ", "常见问题"),
    OUT_OF_SCOPE: ("out_of_scope", "无关问题", "无关", "超出范围"),
    AMBIGUOUS: ("ambiguous", "模糊问题", "模糊", "信息不足"),
}

_SYSTEM_PROMPT = """你是招聘知识问答的问题分类器，只输出一个类别名，不输出解释、JSON、标点或任何其他内容。

判定优先级（严格按序，命中即停止）：
第一步 — 是否属于招聘领域：与招聘、岗位、面试、录用、入职、候选人管理、招聘系统使用完全无关的，输出 out_of_scope。
（天气、股票、薪酬核算、考勤年假、报销流程、公司组织架构调整均为 out_of_scope；「招聘系统报错怎么排查」属于招聘系统使用，归 business_faq）
第二步 — 是否信息不足：属于招聘领域，但缺少关键对象、指代不明、无法确定具体规则或标准的，输出 ambiguous。
（问题简短但对象明确，如「pending 是什么意思？」，不属于模糊问题，归 business_faq）
（问题已明确指向岗位/职位/要求项，只是未给出具体岗位名，如「这个岗位要求项有哪些？」，归 job_ability，由岗位分支追问具体岗位，不要归 ambiguous）
（问题给出明确的标准对象，如「RAG 判定标准」「某项能力的证据要求」，即使没有点名岗位，也归 job_ability，走通用能力标准检索，不要归 ambiguous）
第三步 — 按问题核心对象分类：
- 岗位需要什么能力/经验/学历/技能/素质 → job_ability
- 面试官如何评价、如何打分、评价表怎么填、如何写结论、如何避免偏见 → interview_eval
- 招聘流程在某个阶段怎么流转、状态怎么变更、时间节点、权限、门禁、审批规则 → process_rule
- 通用流程、政策、操作说明、候选人常见问题、系统使用、材料要求等相对稳定的业务问答 → business_faq
第四步 — 多类别冲突：按问题核心诉求归类，不按提到的关键词归类。
- 「面试时怎么判断候选人是否符合 RAG 原理这条标准？」核心诉求是如何评价 → interview_eval
- 「RAG 原理这条标准要求达到什么程度？」核心诉求是标准本身 → job_ability
- 无法判断核心诉求 → ambiguous

合法输出值（只能输出以下之一）：
job_ability / interview_eval / process_rule / business_faq / out_of_scope / ambiguous"""


def _build_user_content(
    question: str,
    pending_intent: dict | None,
    history: list[dict] | None,
) -> str:
    content = f"问题：{question}"
    if pending_intent and pending_intent.get("type") == "job_clarify":
        candidates = pending_intent.get("candidates") or []
        names = [" / ".join(filter(None, [c.get("department_name"), c.get("job_name")])) for c in candidates]
        content += f"\n上一轮岗位澄清候选：{'；'.join(names) or '无'}"
        content += f"\n上一轮原问题：{pending_intent.get('question') or ''}"
    else:
        turns = (history or [])[-settings.QA_MAX_HISTORY_TURNS :]
        if turns:
            lines = [f"Q：{t.get('question', '')}\nA：{t.get('answer', '')}" for t in turns]
            content += "\n最近对话：\n" + "\n".join(lines)
    return content


def _invoke(prompt: str) -> str:
    client = ModelClient(
        temperature=settings.QA_CLASSIFIER_TEMPERATURE,
        max_tokens=settings.QA_CLASSIFIER_MAX_TOKENS,
    )
    response = client.chat_model.invoke(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return str(response.content or "")


def normalize_category(raw: str) -> str | None:
    """规范化分类输出：去空白与引号，按出现位置取第一个合法类别。"""
    if not raw:
        return None
    text = raw.strip().strip("`\"'“”‘’。 \n\t")
    if not text:
        return None
    best: tuple[int, str] | None = None
    for category in CATEGORIES:
        for alias in _ALIASES[category]:
            index = text.find(alias)
            if index >= 0 and (best is None or index < best[0]):
                best = (index, category)
    return best[1] if best else None


def classify_question(
    question: str,
    *,
    pending_intent: dict | None = None,
    history: list[dict] | None = None,
) -> str:
    """返回六类之一；LLM 失败或输出非法时降级为 ambiguous。"""
    if not settings.QA_ENABLED:
        return AMBIGUOUS
    prompt = _build_user_content(question, pending_intent, history)
    for attempt in range(2):
        try:
            raw = _invoke(prompt)
        except Exception as e:
            logger.warning("问题分类失败，降级为 ambiguous：%s", e)
            return AMBIGUOUS
        category = normalize_category(raw)
        if category:
            return category
        logger.warning("问题分类输出非法 attempt=%s raw=%r", attempt + 1, raw[:50])
    return AMBIGUOUS
