"""岗位能力标准分支：岗位识别、工具查询与证据化。

岗位唯一性：`部门 + 岗位名` 唯一确定一个 job_id；仅给岗位名时按全库唯一性判断。
证据范围硬约束：只允许使用该岗位 requirement_items 自身字段，禁止引用 kb_standards。
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from ..core.logging_config import get_logger
from ..llm.client import ModelClient
from ..repositories import JobRepository, RequirementRepository

logger = get_logger("qa")

UNASSIGNED_DEPARTMENT = "未分配部门"

_PRONOUNS = ("这个岗位", "该岗位", "该职位", "本岗位", "这个职位", "这个职位的要求")
# 明确在问「某个岗位的要求项」但未点名的信号词：用于发起岗位澄清，而不是当作通用能力检索
_JOB_TARGET_HINTS = _PRONOUNS + ("要求项", "岗位要求", "任职要求", "职位要求")

_EXTRACT_SYSTEM = """从用户问题中抽取部门名称与岗位名称，只输出一个 JSON 对象：
{"department_name": "部门名称或空字符串", "job_name": "岗位名称或空字符串"}
无法确定时对应字段输出空字符串。不要输出 JSON 之外的解释。"""


def department_name(job) -> str:
    return job.department.name if getattr(job, "department", None) else UNASSIGNED_DEPARTMENT


def list_jobs(db: Session, keyword: str | None = None) -> list[dict]:
    """列出全部岗位（含部门），keyword 命中部门名或岗位名时过滤。"""
    jobs = JobRepository(db).list()
    items = [
        {"job_id": job.id, "department_name": department_name(job), "job_name": job.name}
        for job in jobs
    ]
    if keyword:
        items = [
            item
            for item in items
            if keyword in item["department_name"] or keyword in item["job_name"]
        ]
    return items


def _specific(item: dict) -> dict:
    return {"status": "specific", "job": item, "candidates": []}


def _ambiguous(candidates: list[dict]) -> dict:
    return {"status": "ambiguous", "job": None, "candidates": candidates}


def has_job_target_hint(question: str) -> bool:
    """问题是否明显在问某个岗位的要求，但未点明具体岗位名。"""
    return any(keyword in (question or "") for keyword in _JOB_TARGET_HINTS)


def resolve_job_target(
    db: Session,
    question: str,
    pending_intent: dict | None = None,
) -> dict:
    """确定性岗位识别：返回 specific / ambiguous / department_only / none。"""
    all_jobs = list_jobs(db)
    question = question or ""

    # 追问后用户选择候选：优先按「部门 + 岗位」组合匹配，再退到岗位名、部门名
    # 注意部门名可能被多个候选共享，不能仅凭部门命中就回退为多选
    if pending_intent and pending_intent.get("type") == "job_clarify":
        candidates = pending_intent.get("candidates") or []
        combo_hits = [
            c
            for c in candidates
            if c.get("job_name") and c["job_name"] in question
            and c.get("department_name") and c["department_name"] in question
        ]
        if len(combo_hits) == 1:
            return _specific(combo_hits[0])
        name_hits = [c for c in candidates if c.get("job_name") and c["job_name"] in question]
        if len(name_hits) == 1:
            return _specific(name_hits[0])
        if len(name_hits) > 1:
            dept_hits = [
                c
                for c in name_hits
                if c.get("department_name") and c["department_name"] in question
            ]
            if len(dept_hits) == 1:
                return _specific(dept_hits[0])
            return _ambiguous(dept_hits or name_hits)
        dept_hits = [
            c for c in candidates if c.get("department_name") and c["department_name"] in question
        ]
        if len(dept_hits) == 1:
            return _specific(dept_hits[0])
        if len(dept_hits) > 1:
            return _ambiguous(dept_hits)

    # 部门 + 岗位名同时命中：组合唯一即确定
    combo_hits = [
        item
        for item in all_jobs
        if item["department_name"] in question and item["job_name"] in question
    ]
    if len(combo_hits) == 1:
        return _specific(combo_hits[0])
    if len(combo_hits) > 1:
        return _ambiguous(combo_hits)

    # 仅命中岗位名：全库唯一视为具体岗位，跨部门重复则追问
    name_hits = [item for item in all_jobs if item["job_name"] and item["job_name"] in question]
    if len(name_hits) == 1:
        return _specific(name_hits[0])
    if len(name_hits) > 1:
        return _ambiguous(name_hits)

    # 仅命中部门名：追问该部门下的岗位
    dept_hits = [item for item in all_jobs if item["department_name"] in question]
    if dept_hits:
        return {"status": "department_only", "job": None, "candidates": dept_hits}

    # 只给指代词 / 问「岗位要求项」但未点名：追问具体岗位，并列出候选
    if has_job_target_hint(question):
        return _ambiguous(list_jobs(db))
    return {"status": "none", "job": None, "candidates": []}


def extract_job_terms(question: str) -> dict | None:
    """规则未命中时用 LLM 抽取部门名/岗位名，失败静默返回 None。"""
    try:
        client = ModelClient(temperature=0.0, max_tokens=60)
        content = str(
            client.chat_model.invoke(
                [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=question)]
            ).content
            or ""
        )
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("岗位名称抽取失败：%s", e)
        return None


def match_extracted_terms(db: Session, terms: dict | None) -> dict:
    """用 LLM 抽取结果再匹配一次岗位。"""
    if not terms:
        return {"status": "none", "job": None, "candidates": []}
    dept = str(terms.get("department_name") or "").strip()
    name = str(terms.get("job_name") or "").strip()
    if not dept and not name:
        return {"status": "none", "job": None, "candidates": []}
    hits = [
        item
        for item in list_jobs(db)
        if (not name or name in item["job_name"])
        and (not dept or dept in item["department_name"])
    ]
    if len(hits) == 1:
        return _specific(hits[0])
    if len(hits) > 1:
        return _ambiguous(hits)
    return {"status": "none", "job": None, "candidates": []}


def job_profile(db: Session, job: dict) -> dict:
    """查询岗位基本信息与全部要求项（get_job_profile 工具）。"""
    requirements = RequirementRepository(db).list_by_job(job["job_id"])
    return {
        "job_id": job["job_id"],
        "department_name": job["department_name"],
        "job_name": job["job_name"],
        "requirements": [
            {
                "requirement_item_id": item.id,
                "name": item.name,
                "type": item.type,
                "importance": item.importance,
                "standard": item.standard,
            }
            for item in requirements
        ],
    }


def job_evidence(profile: dict) -> list[dict]:
    """要求项转证据：内容只取 requirement_items 字段，不注入 kb_standards。"""
    document_name = f"职位要求（{profile['department_name']} / {profile['job_name']}）"
    document_id = f"JOB-{profile['job_id']}"
    evidence: list[dict] = []
    for item in profile["requirements"]:
        parts = [item["name"], f"类型：{item['type']}", f"重要度：{item['importance']}"]
        if item.get("standard"):
            parts.append(f"判定标准：{item['standard']}")
        else:
            parts.append("判定标准：未配置")
        evidence.append(
            {
                "document_name": document_name,
                "document_id": document_id,
                "segment_id": f"REQ-{item['requirement_item_id']}",
                "score": 1.0,
                "content": "｜".join(parts),
                "missing_standard": not bool(item.get("standard")),
            }
        )
    return evidence
