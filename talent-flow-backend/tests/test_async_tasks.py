"""异步任务链路用例：LLM 接口立即返回 request_id，后台处理，前端凭 request_id 轮询状态。"""

import json
import threading

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.models import Candidate, Job, ResumeInfo
from app.services import jd_parser
from app.services import resume_tasks

_GEN_ITEMS = {
    "items": [
        {"name": "Python", "type": "必须", "importance": "高", "standard": "3 年以上开发经验"},
    ]
}

_RESUME_RESULT = {
    "basic": {"name": "张三", "phone": None, "email": None, "experience": "5 年"},
    "suggestions": [],
    "advantages": [{"point": "5 年 Python 经验", "evidence": "负责 Python 后端开发"}],
    "risks": [],
}


def _create_job(db, description: str | None = None) -> Job:
    job = Job(name="Python 后端工程师", status="open", description=description)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _create_candidate(db, job_id: int, *, status: str = "review", resume_path: str | None = "uploads/x.pdf") -> Candidate:
    cand = Candidate(name="张三", status=status)
    cand.resume = ResumeInfo(job_id=job_id, resume_path=resume_path)
    db.add(cand)
    db.commit()
    db.refresh(cand)
    return cand


def _fake_llm_client(payload: str, calls: dict | None = None):
    def _llm(_messages):
        if calls is not None:
            calls["n"] += 1
        return AIMessage(content=payload)

    class _FakeClient:
        chat_model = RunnableLambda(_llm)

    return _FakeClient()


def test_get_unknown_task_returns_404(client):
    r = client.get("/tasks/not-exists")
    assert r.status_code == 404


def test_generate_returns_request_id_then_succeeds(client, db, monkeypatch):
    """POST /requirements/{id}/generate 立即返回 request_id，后台完成后可从 /tasks/{id} 取到结果。"""
    job = _create_job(db, description="岗位要求：3 年以上 Python 开发经验，熟悉 SQL。")
    monkeypatch.setattr(
        jd_parser, "get_model_client", lambda: _fake_llm_client(json.dumps(_GEN_ITEMS, ensure_ascii=False))
    )

    r = client.post(f"/requirements/{job.id}/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "generating"
    request_id = body["data"]["request_id"]
    assert len(request_id) == 32

    # TestClient 会同步执行 BackgroundTasks，此时任务应已完成
    t = client.get(f"/tasks/{request_id}").json()["data"]
    assert t["status"] == "success"
    assert t["task_type"] == "requirement_generate"
    assert t["result"][0]["name"] == "Python"


def test_generate_failure_is_recorded_for_polling(client, db, monkeypatch):
    """后台 LLM 失败：任务状态 failed，前端轮询可读取 error，而不是接口直接报错。"""
    job = _create_job(db, description="岗位要求：Python 开发。")
    monkeypatch.setattr(jd_parser, "get_model_client", lambda: _fake_llm_client("这不是 JSON"))

    r = client.post(f"/requirements/{job.id}/generate")
    assert r.status_code == 200  # 入队成功，失败发生在后台
    request_id = r.json()["data"]["request_id"]

    t = client.get(f"/tasks/{request_id}").json()["data"]
    assert t["status"] == "failed"
    assert t["error"]


def test_generate_rejects_empty_jd_without_task(client, db):
    """JD 为空属前置校验，同步返回 400，不创建任务（前端无需轮询）。"""
    job = _create_job(db)
    r = client.post(f"/requirements/{job.id}/generate")
    assert r.status_code == 400
    assert "request_id" not in r.json().get("data", {})


def test_analyze_returns_request_id_and_parses_candidate(client, db, monkeypatch):
    """POST /resumes/{id}/analyze 返回 request_id，后台解析完成后候选人进入 review。"""
    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="review")
    monkeypatch.setattr(
        resume_tasks, "parse_resume", lambda *a, **kw: json.dumps(_RESUME_RESULT, ensure_ascii=False)
    )

    r = client.post(f"/resumes/{cand.id}/analyze")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "processing"
    request_id = data["request_id"]

    t = client.get(f"/tasks/{request_id}").json()["data"]
    assert t["status"] == "success"
    assert t["result"]["candidate_id"] == cand.id

    db.expire_all()
    latest = db.get(Candidate, cand.id)
    assert latest.status == "review"
    assert latest.name == "张三"
    assert latest.resume.analysis


def test_analyze_failure_keeps_review_status(client, db, monkeypatch):
    """解析失败：任务 failed，候选人仍为 review（可人工补全），前端轮询可提示失败原因。"""
    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="review")

    def _boom(*args, **kwargs):
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr(resume_tasks, "parse_resume", _boom)

    r = client.post(f"/resumes/{cand.id}/analyze")
    request_id = r.json()["data"]["request_id"]
    t = client.get(f"/tasks/{request_id}").json()["data"]
    assert t["status"] == "failed"
    assert t["error"]

    db.expire_all()
    latest = db.get(Candidate, cand.id)
    assert latest.status == "review"


def test_recalculate_returns_request_id_when_candidates_exist(client, db, monkeypatch):
    """要求重算：有可重算候选人时返回 request_id，后台完成后任务为 success。"""
    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="finish")
    monkeypatch.setattr(
        resume_tasks, "parse_resume", lambda *a, **kw: json.dumps(_RESUME_RESULT, ensure_ascii=False)
    )

    r = client.post(f"/requirements/{job.id}/recalculate", json={})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["count"] == 1
    request_id = data["request_id"]

    t = client.get(f"/tasks/{request_id}").json()["data"]
    assert t["status"] == "success"
    assert t["result"]["count"] == 1

    db.expire_all()
    assert db.get(Candidate, cand.id).status == "finish"  # 已确认候选人重算后保持 finish


def test_run_parse_dedupes_concurrent_calls_for_same_candidate(db, monkeypatch):
    """同一候选人并发触发解析：第二个调用被单飞去重跳过，LLM 只调用一次。"""
    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="review")

    entered = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def _slow_parse(*_args, **_kwargs):
        calls["n"] += 1
        entered.set()
        assert release.wait(5), "等待首个解析释放超时"
        return json.dumps(_RESUME_RESULT, ensure_ascii=False)

    monkeypatch.setattr(resume_tasks, "parse_resume", _slow_parse)

    result: dict = {}

    def _run_first() -> None:
        try:
            result["first"] = resume_tasks.run_parse(cand.id, request_id="first")
        except Exception as e:  # noqa: BLE001  记录异常供断言
            result["first"] = e

    thread = threading.Thread(target=_run_first)
    thread.start()
    assert entered.wait(5), "首个解析未进入 LLM 调用"

    with pytest.raises(resume_tasks.ParseAlreadyRunningError):
        resume_tasks.run_parse(cand.id, request_id="second")

    release.set()
    thread.join(10)
    assert result["first"] is True
    assert calls["n"] == 1


def test_analyze_skips_when_candidate_already_processing(client, db):
    """候选人已在解析中（未超时）：重复触发直接返回 already parsing，不创建任务。"""
    from datetime import datetime

    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="processing")
    # sqlite 的 CURRENT_TIMESTAMP 是 UTC，与本地 datetime.now() 存在时差，这里显式写入本地时间
    cand.updated_at = datetime.now()
    db.commit()

    r = client.post(f"/resumes/{cand.id}/analyze")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "processing"
    assert "request_id" not in data


def test_mark_parsing_reclaims_stale_processing_candidate(db):
    """processing 超过 3 分钟视为僵死，允许重新抢占（自愈）。"""
    from datetime import datetime, timedelta

    from app.services.candidate_service import CandidateService

    job = _create_job(db, description="Python 后端")
    cand = _create_candidate(db, job.id, status="processing")
    cand.updated_at = datetime.now() - timedelta(minutes=5)
    db.commit()

    _, proceed = CandidateService(db).mark_parsing(cand.id)
    assert proceed is True

    db.expire_all()
    assert db.get(Candidate, cand.id).status == "processing"
