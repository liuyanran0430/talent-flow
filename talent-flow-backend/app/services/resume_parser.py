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


class AnalysisPoint(BaseModel):
    """优势/风险条目：point 是结论，evidence 必须引用简历原文关键内容。
    业务层强制约束：evidence 为空或太短的优势条目会被过滤掉，不写入最终结果。"""

    point: str = Field(..., max_length=100, description="结论要点，如 '5 年 Python 后端经验'")
    evidence: str = Field(..., min_length=1, max_length=200, description="证据，直接引用简历原文；必须有具体内容才能保留该条目")


class ResumeParseResult(BaseModel):
    """简历解析结果"""

    basic: BasicInfo = Field(description="候选人基本信息")
    suggestions: List[MatchSuggestion] = Field(description="职位匹配建议列表")
    advantages: List[AnalysisPoint] = Field(default_factory=list, description="候选人优势（带证据），无证据的优势不出现")
    risks: List[AnalysisPoint] = Field(default_factory=list, description="需要关注的风险/短板（带证据）")


# ---------- OCR 兜底阈值 ----------
# pypdf 从扫描版 PDF 抽不到文字时，通常返回空串或极少垃圾字符；
# 低于该阈值即判定为扫描件，触发 OCR。可在 .env 中通过 OCR_MIN_CHARS 覆盖。
OCR_MIN_CHARS = int(os.getenv("OCR_MIN_CHARS", "50"))
# 是否对所有 PDF 都尝试 OCR 兜底（默认 True）
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes")


def _extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError("解析 PDF 需要安装 pypdf：pip install pypdf") from e
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # 扫描件兜底：pypdf 抽不到足够文本时，尝试 OCR
    if OCR_ENABLED and len(text.strip()) < OCR_MIN_CHARS:
        try:
            from . import ocr as _ocr
        except ImportError:
            _ocr = None
        if _ocr and _ocr.ocr_available():
            ocr_text = _ocr.ocr_pdf(path)
            if ocr_text and len(ocr_text) > len(text):
                text = ocr_text
    return text


def _extract_docx_text(path: str) -> str:
    # DOCX 是 zip 包，正文在 word/document.xml，标准库即可提取
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)  # 段落换行
    return unescape(re.sub(r"<[^>]+>", "", xml))


def _extract_image_text(path: str) -> str:
    """对 jpg/png/jpeg 等图片简历直接走 OCR"""
    try:
        from . import ocr as _ocr
    except ImportError:
        _ocr = None
    if not _ocr or not _ocr.ocr_available():
        raise ValueError(
            "图片简历需要 OCR 依赖，请先安装：pip install rapidocr-onnxruntime pillow"
        )
    with open(path, "rb") as f:
        return _ocr.ocr_image_bytes(f.read())


# 图片简历支持的扩展名
_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def extract_text(path: str) -> str:
    """按扩展名提取简历文本，支持 pdf/docx/txt/md/jpg/png（图片走 OCR）"""
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
    elif ext in _IMAGE_EXTS:
        text = _extract_image_text(path)
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

system_prompt = """你是一名资深简历解析专家。基于用户提供的简历文本，完成四项任务：
一、提取候选人基本信息：姓名、联系电话、邮箱地址、工作年限
二、按给定的职位要求项列表（含判定标准），逐项判断候选人匹配情况
三、列出候选人优势（advantages）：从简历中提炼与岗位要求匹配最突出的 1-5 点。每点必须附 evidence，直接引用简历原文的关键内容，不得编造。如果简历中找不到足够证据支撑某一优势，宁可少写也不要硬凑
四、列出需关注的风险（risks）：候选人经验不足、技能缺失或明显短板 0-5 点。每点也必须附 evidence；若简历中无明显风险则返回空数组

硬性规则：
1. 基本信息必须来自简历原文，未识别到的字段填 null，严禁编造
2. 匹配建议只能是：满足/不满足/证据不足
3. 匹配依据、优势/风险的 evidence 必须直接引用简历原文；没有依据时填空字符串或直接省略该条目
4. 优势（advantages）没有证据的条目不得出现，evidence 为空或太短（少于 6 字）的优势必须直接省略，不能返回
5. 风险（risks）可以在 evidence 较弱时保留，但仍需尽力引用原文
6. 逐项输出所有要求项，name 与输入保持完全一致，不要遗漏、不要新增
7. 严格按指定 JSON 格式输出，不要附加任何额外说明

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
# 优势 evidence 最小长度：短于此值视为"没有证据"，该优势必须被过滤掉
# 风险 evidence 放宽（可能简历未明确提及某风险，但仍保留条目提醒 HR 核实）
_ADVANTAGE_MIN_EVIDENCE_CHARS = 6


def _validate(result: ResumeParseResult, requirement_names: List[str]) -> str:
    """业务层额外校验：
    1. 建议项与输入要求项一一对齐（缺失补齐，多余剔除）
    2. 优势强制证据过滤：evidence 为空或太短的优势必须移除，返回空数组而非保留无证据条目
    3. 风险 evidence 为空的条目保留（提醒 HR 核实），但空数组可接受
    """
    # ---- 建议项对齐 ----
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
            aligned.append(MatchSuggestion(name=name, suggestion="证据不足", evidence=""))
    result.suggestions = aligned

    # ---- 优势强制证据过滤 ----
    # 规则：evidence 必须非空且不少于 _ADVANTAGE_MIN_EVIDENCE_CHARS 字符
    result.advantages = [
        a for a in (result.advantages or [])
        if a.evidence and len(a.evidence.strip()) >= _ADVANTAGE_MIN_EVIDENCE_CHARS and a.point.strip()
    ]

    # ---- 风险：evidence 为空的条目保留但 point 必须非空 ----
    result.risks = [r for r in (result.risks or []) if r.point.strip()]

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
