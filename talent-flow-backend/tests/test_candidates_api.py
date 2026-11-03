"""candidates API Golden Case：列表筛选/分页、详情、创建、更新路由、删除级联。"""

import json

from app.models import Candidate, Job, JobFit, RequirementItem, ResumeInfo


def _create_job(db, name: str = "AI算法工程师") -> int:
    job = Job(name=name, status="open")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def _create_requirement(db, job_id: int, name: str = "Python") -> int:
    item = RequirementItem(job_id=job_id, name=name, type="必须", importance="高")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.id


def _create_candidate(db, *, name="张三", status="review", job_id=None, analysis=None) -> Candidate:
    c = Candidate(name=name, status=status)
    c.resume = ResumeInfo(job_id=job_id, analysis=analysis)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_list_empty(client):
    r = client.get("/candidates")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"] == {"total": 0, "page": 1, "page_size": 20, "items": []}


def test_list_filters_status_and_search(client, db):
    job_id = _create_job(db)
    _create_candidate(db, name="张三", status="review", job_id=job_id)
    _create_candidate(db, name="李四", status="finish", job_id=job_id)
    _create_candidate(db, name="王五", status="finish")

    r = client.get("/candidates")
    assert r.json()["data"]["total"] == 3

    r = client.get("/candidates", params={"status": "finish"})
    assert {i["name"] for i in r.json()["data"]["items"]} == {"李四", "王五"}

    # status=all 视为不筛选
    r = client.get("/candidates", params={"status": "all"})
    assert r.json()["data"]["total"] == 3

    r = client.get("/candidates", params={"search": "张"})
    assert [i["name"] for i in r.json()["data"]["items"]] == ["张三"]


def test_list_job_id_filter_and_pagination(client, db):
    job_id = _create_job(db)
    other_job_id = _create_job(db, name="后端工程师")
    for idx in range(4):
        _create_candidate(db, name=f"候选{idx}", job_id=job_id)
    _create_candidate(db, name="外职位", job_id=other_job_id)

    r = client.get("/candidates", params={"job_id": job_id})
    assert r.json()["data"]["total"] == 4
    assert {i["job_id"] for i in r.json()["data"]["items"]} == {job_id}

    # 分页：同一秒内创建的记录 created_at 相同，只断言条数不断言顺序
    r = client.get("/candidates", params={"page": 1, "page_size": 2})
    data = r.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    r = client.get("/candidates", params={"page": 3, "page_size": 2})
    assert len(r.json()["data"]["items"]) == 1


def test_list_query_validation(client):
    assert client.get("/candidates", params={"page": 0}).status_code == 422
    assert client.get("/candidates", params={"page_size": 0}).status_code == 422
    assert client.get("/candidates", params={"page_size": 1001}).status_code == 422


def test_get_detail_not_found(client):
    r = client.get("/candidates/9999")
    assert r.status_code == 404
    assert r.json()["detail"] == "candidate not found"


def test_detail_computed_analysis(client, db):
    valid = json.dumps({
        "advantages": [{"point": "熟悉分布式", "evidence": "主导过 3 个服务拆分"}],
        "risks": [{"point": "管理经验不足", "evidence": "未带过团队"}],
    })
    a = _create_candidate(db, name="有分析", analysis=valid)
    b = _create_candidate(db, name="脏数据", analysis="not-a-json")

    data = client.get(f"/candidates/{a.id}").json()["data"]
    assert data["advantages"] == [{"point": "熟悉分布式", "evidence": "主导过 3 个服务拆分"}]
    assert data["risks"] == [{"point": "管理经验不足", "evidence": "未带过团队"}]

    data = client.get(f"/candidates/{b.id}").json()["data"]
    assert data["advantages"] == []
    assert data["risks"] == []


def test_create_candidate_flattens_resume_fields(client, db):
    job_id = _create_job(db)
    r = client.post(
        "/candidates",
        json={
            "name": "赵六",
            "job_id": job_id,
            "resume_path": "/tmp/resume.pdf",
            "experience": "3-5年",
            "review_note": "待安排面试",
        },
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["job_id"] == job_id
    assert data["resume_path"] == "/tmp/resume.pdf"
    assert data["experience"] == "3-5年"
    assert data["review_note"] == "待安排面试"
    assert data["status"] == "review"
    assert data["advantages"] == [] and data["risks"] == []

    # 简历侧字段落在 resume_infos，一行对一行
    resumes = db.query(ResumeInfo).filter(ResumeInfo.candidate_id == data["id"]).all()
    assert len(resumes) == 1
    assert resumes[0].job_id == job_id


def test_create_candidate_without_resume_row(client, db):
    r = client.post("/candidates", json={"name": "孙七"})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["job_id"] is None
    # 未带任何简历侧字段时不建简历行
    assert db.query(ResumeInfo).filter(ResumeInfo.candidate_id == data["id"]).count() == 0


def test_create_candidate_validation(client):
    r = client.post("/candidates", json={"name": "x" * 65})
    assert r.status_code == 422
    r = client.post("/candidates", json={"phone": "1" * 33})
    assert r.status_code == 422


def test_update_routes_resume_fields(client, db):
    job_id = _create_job(db)
    new_job_id = _create_job(db, name="后端工程师")
    c = _create_candidate(db, name="张三", job_id=job_id)

    r = client.put(
        f"/candidates/{c.id}",
        json={"name": "张三改", "phone": "13800000000", "job_id": new_job_id, "review_note": "建议再面一轮"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["name"] == "张三改"
    assert data["phone"] == "13800000000"
    assert data["job_id"] == new_job_id
    assert data["review_note"] == "建议再面一轮"
    # 未提交的字段保持原值
    assert data["status"] == "review"

    db.expire_all()
    resume = db.query(ResumeInfo).filter(ResumeInfo.candidate_id == c.id).one()
    assert resume.job_id == new_job_id
    assert resume.review_note == "建议再面一轮"


def test_update_status_and_review_note_single_call(client, db):
    """HR 点「采纳」时状态与复核意见必须一次 PUT 全部落库。"""
    c = _create_candidate(db, name="周予安", status="review")

    r = client.put(f"/candidates/{c.id}", json={"status": "finish", "review_note": "同意录用"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "finish"
    assert data["review_note"] == "同意录用"

    db.expire_all()
    assert db.get(Candidate, c.id).status == "finish"
    resume = db.query(ResumeInfo).filter(ResumeInfo.candidate_id == c.id).one()
    assert resume.review_note == "同意录用"


def test_update_creates_resume_row_when_missing(client, db):
    c = _create_candidate(db, name="无简历行")
    c.resume = None
    db.delete(db.query(ResumeInfo).filter(ResumeInfo.candidate_id == c.id).one())
    db.commit()

    job_id = _create_job(db)
    r = client.put(f"/candidates/{c.id}", json={"job_id": job_id})
    assert r.status_code == 200
    assert r.json()["data"]["job_id"] == job_id
    assert db.query(ResumeInfo).filter(ResumeInfo.candidate_id == c.id).count() == 1


def test_update_not_found(client):
    r = client.put("/candidates/9999", json={"name": "不存在"})
    assert r.status_code == 404
    assert r.json()["detail"] == "candidate not found"


def test_delete_cascades_jobfits_and_resume_file(client, db, tmp_path):
    job_id = _create_job(db)
    req_id = _create_requirement(db, job_id)
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("简历内容", encoding="utf-8")

    c = Candidate(name="待删除", status="finish")
    c.resume = ResumeInfo(job_id=job_id, resume_path=str(resume_file))
    db.add(c)
    db.commit()
    db.refresh(c)
    db.add(JobFit(candidate_id=c.id, requirement_item_id=req_id, suggestion="满足", evidence="3 年经验"))
    db.commit()

    r = client.delete(f"/candidates/{c.id}")
    assert r.status_code == 200
    assert r.json()["message"] == "deleted"

    db.expire_all()
    assert db.get(Candidate, c.id) is None
    assert db.query(ResumeInfo).filter(ResumeInfo.candidate_id == c.id).count() == 0
    assert db.query(JobFit).filter(JobFit.candidate_id == c.id).count() == 0
    assert not resume_file.exists()


def test_delete_not_found(client):
    r = client.delete("/candidates/9999")
    assert r.status_code == 404
    assert r.json()["detail"] == "candidate not found"
