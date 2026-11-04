"""结构化输出（JSON）解析失败的重试与降级策略。

对照 LLM 错误码处理表「JSON 解析失败：模型输出不合规 → 重试一次后降级转人工」：
- 第一次解析失败（输出不是合法 JSON / 不符合 Schema）→ 原样重试一次（重新走一遍 LLM）
- 第二次仍失败 → 抛出原异常，由调用方降级转人工：
  - 简历解析：services/resume_tasks.run_parse 捕获后置候选人 status=review，
    resume.info 提示「简历解析失败，请手动补全信息」，进入 HR 复核
  - JD 要求项生成：接口返回 500 错误提示，HR 手动逐条填写要求项
"""

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import Runnable
from pydantic import ValidationError

# 视为「模型输出不合规」的异常：JSON 文本非法（OutputParserException）或字段不满足 Schema（ValidationError）
PARSE_ERROR_TYPES = (OutputParserException, ValidationError)


def invoke_with_parse_retry(chain: Runnable, inputs, *, logger, tag: str):
    """执行 LCEL chain；解析失败自动重试一次，再失败抛出原异常交由调用方降级转人工。

    :param chain: 含 LLM 与 Pydantic 输出解析的完整 chain
    :param inputs: chain.invoke 的入参
    :param logger: 记录重试日志的 logger（带 request_id 上下文）
    :param tag: 业务标签，用于日志定位，如 "简历解析" / "JD 要求项生成"
    """
    try:
        return chain.invoke(inputs)
    except PARSE_ERROR_TYPES as e:
        logger.warning("%s 模型输出 JSON 不合规，重试一次：%s", tag, e)
        return chain.invoke(inputs)
