"""
岗位 JD 解析服务

输入：岗位 JD 文本
输出：岗位要求的 JSON 格式化字符串（含若干要求项）

采用 LangChain LCEL 编排：
    preprocess（预处理） → classify（标签分类） → validate（输出校验）

依赖安装：
    pip install langchain langchain-openai python-dotenv pydantic

需要在 .env 中配置：
    LLM_MODEL=qwen-max
    OPENAI_API_KEY=sk-xxx
    OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
"""
from __future__ import annotations

import json
import re
from typing import List, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from ..core.logging_config import (
    get_logger,
    reset_prompt_version,
    reset_retrieval_ids,
    set_prompt_version,
    set_retrieval_ids,
)
from ..llm import get_model_client
from ..llm.parse_retry import invoke_with_parse_retry

logger = get_logger("jd-parser")

# JD 原文截断上限：超长 JD（含 HTML 噪声清洗后）不至于把 prompt 顶出模型上下文窗口
MAX_JD_CHARS = 6000
# 岗位标准参考注入上限：避免多条标准把 prompt 撑爆
MAX_STANDARD_REFS_CHARS = 2000


# ---------- 输出 Schema（输出校验依据） ----------
class RequirementItemSpec(BaseModel):
    """单条岗位要求项"""

    name: str = Field(description="要求项名称，简洁短语，如「Python」")
    type: Literal["必须", "加分"] = Field(description="类型：必须/加分")
    importance: Literal["高", "中", "低"] = Field(description="重要程度：高/中/低")
    standard: str = Field(description="判定标准，描述如何衡量候选人是否符合该要求")
    standard_id: int | None = Field(
        None, description="命中的岗位标准条目 id；没有匹配到参考标准时填 null"
    )


class RequirementList(BaseModel):
    """岗位要求列表"""

    items: List[RequirementItemSpec] = Field(description="岗位要求项集合")


# ---------- 步骤 1：预处理 ----------
def format_standard_refs(standards: list[dict]) -> str:
    """把检索到的岗位标准格式化为 Prompt 中的参考清单。"""
    if not standards:
        return "（无可用标准参考，按 JD 原文提取）"
    lines = []
    for s in standards:
        line = f"- standard_id={s['id']} ｜ {s['name']}"
        if s.get("standard"):
            line += f" ｜ 判定标准：{s['standard']}"
        if s.get("required_evidence"):
            line += f" ｜ 证据要求：{s['required_evidence']}"
        lines.append(line)
    return "\n".join(lines)[:MAX_STANDARD_REFS_CHARS]


def preprocess(jd_text: str, standards: list[dict] | None = None) -> dict:
    """清理 JD 原文：去 HTML 标签、合并多余空白，并按上限截断（上下文超限防御）"""
    if not jd_text or not jd_text.strip():
        raise ValueError("JD 文本不能为空")
    text = re.sub(r"<[^>]+>", " ", jd_text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"jd": text[:MAX_JD_CHARS], "standard_refs": format_standard_refs(standards or [])}


# ---------- 步骤 2：标签分类（LLM 提示词 + 输出 Parser） ----------
parser = PydanticOutputParser(pydantic_object=RequirementList)

system_prompt = """你是一名岗位要求提取专家。基于用户提供的岗位 JD 文本，提取结构化的岗位要求项。

要求：
1. 每个要求项需包含：名称、类型（必须/加分）、重要程度（高/中/低）、判定标准（描述如何判定候选人符合此项）
2. 名称简洁（如「Python」「3 年以上经验」「沟通能力」）
3. 判定标准要可衡量、可验证
4. 一般提取 5-10 项核心要求，避免滥发
5. 严格按指定 JSON 格式输出，不要附加任何额外说明
6. 如果重要程度和类型无法判断，设为「低」和「必须」
7. 若提供了「岗位标准参考」，优先复用参考中的标准名称与判定标准；仅当要求项与该标准语义一致时回填对应 standard_id，没有匹配填 null，严禁编造 id

{format_instructions}
"""

classify_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("user", "{jd}\n\n岗位标准参考（优先复用，命中时回填 standard_id）：\n{standard_refs}"),
    ]
).partial(format_instructions=parser.get_format_instructions())


# ---------- 步骤 3：输出校验 ----------
def validate(result: RequirementList, allowed_ids: set[int] | None = None) -> str:
    """业务层额外校验：非空、数量上限、名称去重、引用校验"""
    if not result.items:
        raise ValueError("未提取到任何要求项")
    if len(result.items) > 20:
        result.items = result.items[:20]
    # 引用校验：standard_id 不在本次注入范围内的一律剔除，避免模型编造来源
    allowed = allowed_ids or set()
    for it in result.items:
        if it.standard_id is not None and it.standard_id not in allowed:
            it.standard_id = None
    seen: set[str] = set()
    deduped: List[RequirementItemSpec] = []
    for it in result.items:
        if it.name in seen:
            continue
        seen.add(it.name)
        deduped.append(it)
    result.items = deduped
    return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)


# ---------- 编排 chain ----------
def build_chain(standards: list[dict] | None = None):
    """构建 LCEL chain：preprocess → classify_prompt → llm → parser → validate"""
    standards = standards or []
    allowed_ids = {int(s["id"]) for s in standards}
    llm = get_model_client().chat_model
    return (
        RunnableLambda(lambda jd_text: preprocess(jd_text, standards))
        | classify_prompt
        | llm
        | parser
        | RunnableLambda(lambda result: validate(result, allowed_ids))
    )


def parse_jd(jd_text: str, standards: list[dict] | None = None) -> str:
    """对外接口：输入 JD 文本（可选岗位标准参考），返回岗位要求 JSON 格式化字符串。

    JSON 解析失败（模型输出不合规）时自动重试一次；再失败抛出原异常，
    由调用方降级转人工：requirements 接口返回错误提示，HR 手动填写要求项。
    """
    # 空文本直接拒绝：不必构建 chain（也就不会触碰 LLM 客户端）
    if not jd_text or not jd_text.strip():
        raise ValueError("JD 文本不能为空")
    standards = standards or []
    # 标记本次使用的提示词版本与检索命中 id，写入 LLM 结构化日志
    prompt_token = set_prompt_version("jd_generate/v1")
    retrieval_token = set_retrieval_ids([s["id"] for s in standards])
    try:
        return invoke_with_parse_retry(
            build_chain(standards), jd_text, logger=logger, tag="JD 要求项生成"
        )
    finally:
        reset_prompt_version(prompt_token)
        reset_retrieval_ids(retrieval_token)


# if __name__ == "__main__":
    # sample_jd = """
    # 岗位：大模型应用工程师
    # 职责：负责 RAG、Agent 系统设计与开发。
    # 要求：
    # - Python 开发经验
    # - 熟悉 LangChain、LlamaIndex 等框架
    # - 熟悉 Transformer、RAG 原理
    # - 加分：有 Agent 项目经验
    # - 良好的沟通与团队协作能力
    # """
    # print(parse_jd(sample_jd))
