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
import os
import re
from typing import List, Literal

import dotenv
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dotenv.load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


# ---------- 输出 Schema（输出校验依据） ----------
class RequirementItemSpec(BaseModel):
    """单条岗位要求项"""

    name: str = Field(description="要求项名称，简洁短语，如「Python」")
    type: Literal["必须", "加分"] = Field(description="类型：必须/加分")
    importance: Literal["高", "中", "低"] = Field(description="重要程度：高/中/低")
    standard: str = Field(description="判定标准，描述如何衡量候选人是否符合该要求")


class RequirementList(BaseModel):
    """岗位要求列表"""

    items: List[RequirementItemSpec] = Field(description="岗位要求项集合")


# ---------- 步骤 1：预处理 ----------
def preprocess(jd_text: str) -> dict:
    """清理 JD 原文：去 HTML 标签、合并多余空白"""
    if not jd_text or not jd_text.strip():
        raise ValueError("JD 文本不能为空")
    text = re.sub(r"<[^>]+>", " ", jd_text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"jd": text}


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

{format_instructions}
"""

classify_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("user", "{jd}"),
    ]
).partial(format_instructions=parser.get_format_instructions())


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-v4-pro"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=0.2,
        timeout=120,  # 超时防止 API 挂起导致前端长时间等待
        max_retries=2,  # 偶发 503/超时自动重试
    )


# ---------- 步骤 3：输出校验 ----------
def validate(result: RequirementList) -> str:
    """业务层额外校验：非空、数量上限、名称去重"""
    if not result.items:
        raise ValueError("未提取到任何要求项")
    if len(result.items) > 20:
        result.items = result.items[:20]
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
def build_chain():
    """构建 LCEL chain：preprocess → classify_prompt → llm → parser → validate"""
    llm = build_llm()
    return (
        RunnableLambda(preprocess)
        | classify_prompt
        | llm
        | parser
        | RunnableLambda(validate)
    )


def parse_jd(jd_text: str) -> str:
    """对外接口：输入 JD 文本，返回岗位要求 JSON 格式化字符串"""
    return build_chain().invoke(jd_text)


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
