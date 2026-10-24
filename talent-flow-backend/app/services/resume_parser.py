"""
简历解析服务

输入：简历本地路径、职位要求项及判定标准的列表
输出：结构化 JSON（基本信息 + 职位匹配建议）

采用 LangChain LCEL 编排：
    preprocess（读取简历文本） → classify（LLM 抽取与匹配） → validate（输出校验）

依赖安装：
    pip install langchain langchain-openai python-dotenv pydantic pypdf

需要在 .env 中配置：
    LLM_MODEL=qwen-max
    OPENAI_API_KEY=sk-xxx
    OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from html import unescape
from typing import List, Literal

import dotenv
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dotenv.load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

# 简历文本截断上限，避免超出 LLM 上下文
MAX_RESUME_CHARS = 8000


# ---------- 输出 Schema（输出校验依据） ----------
class BasicInfo(BaseModel):
    """候选人基本信息"""

    name: str | None = Field(None, description="姓名；未识别到则为 null")
    phone: str | None = Field(None, description="联系电话；未识别到则为 null")
    email: str | None = Field(None, description="邮箱地址；未识别到则为 null")
    experience: str | None = Field(None, description="工作年限，如「5-10年」；未识别到则为 null")


class MatchSuggestion(BaseModel):
    """单条职位匹配建议"""

    name: str = Field(description="要求项名称，与输入要求项保持一致")
    suggestion: Literal["满足", "不满足", "证据不足"] = Field(description="匹配建议：满足/不满足/证据不足")
    evidence: str = Field("", description="匹配依据，引用简历原文关键内容；无依据则为空字符串")


class ResumeParseResult(BaseModel):
    """简历解析结果"""

    basic: BasicInfo = Field(description="候选人基本信息")
    suggestions: List[MatchSuggestion] = Field(description="职位匹配建议列表")


# ---------- 简历文本提取 ----------
def _extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError("解析 PDF 需要安装 pypdf：pip install pypdf") from e
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(path: str) -> str:
    # DOCX 是 zip 包，正文在 word/document.xml，标准库即可提取
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)  # 段落换行
    return unescape(re.sub(r"<[^>]+>", "", xml))


def extract_text(path: str) -> str:
    """按扩展名提取简历文本，支持 pdf/docx/txt/md"""
    if not os.path.isfile(path):
        raise ValueError(f"简历文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text = _extract_pdf_text(path)
    elif ext == ".docx":
        text = _extract_docx_text(path)
    elif ext in (".txt", ".md"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    elif ext == ".doc":
        raise ValueError("暂不支持旧版 .doc 格式，请另存为 .docx 或 .pdf 后重试")
    else:
        raise ValueError(f"不支持的简历格式：{ext}")
    return text.strip()


# ---------- 步骤 1：预处理 ----------
def preprocess(payload: dict) -> dict:
    """读取简历文本 + 格式化要求项列表"""
    text = extract_text(payload["resume_path"])
    if not text:
        raise ValueError("未能从简历中提取到文本内容")

    req_lines = []
    for i, r in enumerate(payload["requirements"], 1):
        name = r.get("name") if isinstance(r, dict) else getattr(r, "name", "")
        standard = (
            r.get("standard") if isinstance(r, dict) else getattr(r, "standard", None)
        ) or "（无判定标准）"
        req_lines.append(f"{i}. {name}：{standard}")

    return {
        "resume_text": text[:MAX_RESUME_CHARS],
        "requirements_text": "\n".join(req_lines) or "（无要求项）",
    }


# ---------- 步骤 2：信息抽取与匹配（LLM 提示词 + 输出 Parser） ----------
parser = PydanticOutputParser(pydantic_object=ResumeParseResult)

system_prompt = """你是一名资深简历解析专家。基于用户提供的简历文本，完成两项任务：
一、提取候选人基本信息：姓名、联系电话、邮箱地址、工作年限
二、按给定的职位要求项列表（含判定标准），逐项判断候选人匹配情况

要求：
1. 基本信息必须来自简历原文，未识别到的字段填 null，严禁编造
2. 匹配建议只能是：满足/不满足/证据不足
3. 匹配依据需引用简历原文中的关键内容作为佐证；确实没有依据时给空字符串，严禁编造
4. 逐项输出所有要求项，name 与输入保持完全一致，不要遗漏、不要新增
5. 严格按指定 JSON 格式输出，不要附加任何额外说明
6. 工作年限格式为x年，不要多余文字

{format_instructions}
"""

classify_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        (
            "user",
            "简历文本：\n{resume_text}\n\n职位要求项列表（含判定标准）：\n{requirements_text}",
        ),
    ]
).partial(format_instructions=parser.get_format_instructions())


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-v4-pro"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=0.2,
        timeout=120,  # 超时防止 API 挂起导致解析状态永远停在 processing
        max_retries=2,
    )


# ---------- 步骤 3：输出校验 ----------
def _validate(result: ResumeParseResult, requirement_names: List[str]) -> str:
    """业务层额外校验：建议项与输入要求项一一对齐（缺失补齐，多余剔除）"""
    by_name = {s.name: s for s in result.suggestions}
    aligned: List[MatchSuggestion] = []
    for name in requirement_names:
        if name in by_name:
            s = by_name[name]
            aligned.append(
                MatchSuggestion(
                    name=name,
                    suggestion=s.suggestion,
                    evidence=s.evidence or "",
                )
            )
        else:
            # LLM 遗漏的要求项，按“证据不足 + 空依据”补齐
            aligned.append(MatchSuggestion(name=name, suggestion="证据不足", evidence=""))
    result.suggestions = aligned
    return json.dumps(result.model_dump(), ensure_ascii=False)


# ---------- 编排 chain ----------
def build_chain(requirement_names: List[str]):
    """构建 LCEL chain：preprocess → classify_prompt → llm → parser → validate"""
    llm = build_llm()
    return (
        RunnableLambda(preprocess)
        | classify_prompt
        | llm
        | parser
        | RunnableLambda(lambda r: _validate(r, requirement_names))
    )


def parse_resume(resume_path: str, requirements: list) -> str:
    """
    对外接口

    :param resume_path: 简历本地路径（支持 pdf/docx/txt/md）
    :param requirements: 职位要求项列表，元素为 dict（含 name、standard）或对象（含 .name/.standard 属性）
    :return: 结构化 JSON 字符串，含 basic（基本信息）与 suggestions（职位匹配建议列表）
    """
    requirement_names = [
        (r.get("name") if isinstance(r, dict) else getattr(r, "name", "")) or ""
        for r in requirements
    ]
    return build_chain(requirement_names).invoke(
        {"resume_path": resume_path, "requirements": requirements}
    )


# if __name__ == "__main__":
#     sample_reqs = [
#         {"name": "Python 开发经验", "standard": "简历中体现 3 年以上 Python 项目经验"},
#         {"name": "网络协议", "standard": "熟悉网络协议，网络运维相关经验"},
#     ]
#     print(parse_resume(r"C:\Users\86134\Downloads\lyr.pdf", sample_reqs))
