"""requirements API Golden Case：batch 覆盖写、404 校验。"""

from app.models import Job


def _create_job(db) -> int:
    job = Job(name="AI算法工程师", status="open")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def test_batch_replace_overwrites(client, db):
    job_id = _create_job(db)

    # 先批量写 3 项
    r = client.post(
        f"/requirements/{job_id}/items/batch",
        json={"items": [
            {"name": "Python", "type": "必须", "importance": "高", "standard": "3年以上"},
            {"name": "SQL", "type": "必须", "importance": "中", "standard": "熟练"},
            {"name": "英语", "type": "加分", "importance": "低", "standard": "六级"},
        ]},
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3

    # 再批量写 2 项，旧项应被整体覆盖
    r = client.post(
        f"/requirements/{job_id}/items/batch",
        json={"items": [
            {"name": "Go", "type": "必须", "importance": "高", "standard": "5年以上"},
            {"name": "K8s", "type": "加分", "importance": "中", "standard": "生产经验"},
        ]},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 2
    assert {i["name"] for i in data} == {"Go", "K8s"}

    # 列表接口确认落库结果
    r = client.get(f"/requirements/{job_id}/items")
    assert [i["name"] for i in r.json()["data"]] == ["Go", "K8s"]


def test_batch_replace_job_not_found(client):
    r = client.post(
        "/requirements/9999/items/batch",
        json={"items": [{"name": "Python", "type": "必须", "importance": "高", "standard": "3年以上"}]},
    )
    assert r.status_code == 404


def test_generate_jd_not_found(client):
    r = client.post("/requirements/9999/generate")
    assert r.status_code == 404


def test_generate_jd_empty(client, db):
    job_id = _create_job(db)  # 无 description
    r = client.post(f"/requirements/{job_id}/generate")
    assert r.status_code == 400
