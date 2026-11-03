"""jobfits API Golden Case：列表、创建校验、只改建议、删除。"""

from app.models import Candidate, Job, JobFit, RequirementItem, ResumeInfo


def _create_candidate(db, name: str = "张三") -> int:
    c = Candidate(name=name, status="review")
    c.resume = ResumeInfo()
    db.add(c)
    db.commit()
    db.refresh(c)
    return c.id


def _create_requirement(db, name: str = "Python 基础") -> int:
    job = Job(name="AI算法工程师", status="open")
    db.add(job)
    db.commit()
    db.refresh(job)
    item = RequirementItem(job_id=job.id, name=name, type="必须", importance="高")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.id


def test_list_by_candidate_empty(client):
    r = client.get("/jobfits/candidates/1")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_create_and_list_by_candidate(client, db):
    candidate_id = _create_candidate(db)
    req_id = _create_requirement(db)

    r = client.post(
        "/jobfits",
        json={
            "candidate_id": candidate_id,
            "requirement_item_id": req_id,
            "suggestion": "满足",
            "evidence": "5 年 Python 开发经验",
        },
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["suggestion"] == "满足"
    assert data["evidence"] == "5 年 Python 开发经验"

    r = client.get(f"/jobfits/candidates/{candidate_id}")
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == data["id"]


def test_list_orders_by_id(client, db):
    candidate_id = _create_candidate(db)
    first = _create_requirement(db, name="Python 基础")
    second = _create_requirement(db, name="K8s")
    for req_id in (first, second):
        client.post(
            "/jobfits",
            json={"candidate_id": candidate_id, "requirement_item_id": req_id, "suggestion": "证据不足"},
        )

    items = client.get(f"/jobfits/candidates/{candidate_id}").json()["data"]
    assert [i["requirement_item_id"] for i in items] == [first, second]
    assert [i["id"] for i in items] == sorted(i["id"] for i in items)


def test_create_default_suggestion(client, db):
    candidate_id = _create_candidate(db)
    req_id = _create_requirement(db)

    r = client.post("/jobfits", json={"candidate_id": candidate_id, "requirement_item_id": req_id})
    assert r.status_code == 201
    assert r.json()["data"]["suggestion"] == "证据不足"
    assert r.json()["data"]["evidence"] is None


def test_create_candidate_not_found(client, db):
    req_id = _create_requirement(db)
    r = client.post("/jobfits", json={"candidate_id": 9999, "requirement_item_id": req_id})
    assert r.status_code == 404
    assert "candidate 9999 not found" in r.json()["detail"]


def test_create_requirement_not_found(client, db):
    candidate_id = _create_candidate(db)
    r = client.post("/jobfits", json={"candidate_id": candidate_id, "requirement_item_id": 9999})
    assert r.status_code == 404
    assert "requirement item 9999 not found" in r.json()["detail"]


def test_create_validation(client):
    assert client.post("/jobfits", json={}).status_code == 422
    assert client.post("/jobfits", json={"candidate_id": "abc", "requirement_item_id": 1}).status_code == 422


def test_update_suggestion_keeps_evidence(client, db):
    """HR 只改匹配建议，匹配依据（AI 解析原始内容）保持不动。"""
    candidate_id = _create_candidate(db)
    req_id = _create_requirement(db)
    fit_id = client.post(
        "/jobfits",
        json={
            "candidate_id": candidate_id,
            "requirement_item_id": req_id,
            "suggestion": "证据不足",
            "evidence": "简历未提及容器编排",
        },
    ).json()["data"]["id"]

    r = client.put(f"/jobfits/{fit_id}", json={"suggestion": "满足"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["suggestion"] == "满足"
    assert data["evidence"] == "简历未提及容器编排"
    # 关联关系不因更新而变化
    assert data["candidate_id"] == candidate_id
    assert data["requirement_item_id"] == req_id

    db.expire_all()
    assert db.get(JobFit, fit_id).suggestion == "满足"


def test_update_not_found(client):
    r = client.put("/jobfits/9999", json={"suggestion": "满足"})
    assert r.status_code == 404
    assert r.json()["detail"] == "jobfit not found"


def test_delete_then_list_empty(client, db):
    candidate_id = _create_candidate(db)
    req_id = _create_requirement(db)
    fit_id = client.post(
        "/jobfits",
        json={"candidate_id": candidate_id, "requirement_item_id": req_id, "suggestion": "满足"},
    ).json()["data"]["id"]

    r = client.delete(f"/jobfits/{fit_id}")
    assert r.status_code == 200
    assert r.json()["message"] == "deleted"
    assert client.get(f"/jobfits/candidates/{candidate_id}").json()["data"] == []

    db.expire_all()
    assert db.get(JobFit, fit_id) is None

    r = client.delete(f"/jobfits/{fit_id}")
    assert r.status_code == 404
