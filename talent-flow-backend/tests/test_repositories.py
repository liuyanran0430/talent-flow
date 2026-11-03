"""仓储层 smoke：sqlite 建表后 CRUD 往返（开启外键校验，与 MySQL 行为对齐）。"""

from app.models import Candidate, Job, ResumeInfo
from app.repositories import CandidateRepository, RequirementRepository, ResumeRepository


def test_candidate_crud_roundtrip(db):
    repo = CandidateRepository(db)
    c = Candidate(name="张三", status="pending")
    repo.add(c)
    repo.commit()
    repo.refresh(c)
    assert c.id is not None

    got = repo.get(c.id)
    assert got is not None and got.name == "张三"

    items, total = repo.list(search="张三")
    assert total == 1 and items[0].id == c.id

    repo.delete(got)
    repo.commit()
    assert repo.get(c.id) is None


def test_resume_find_by_hash(db):
    repo = ResumeRepository(db)
    c = Candidate(name="李四", status="pending", resume=ResumeInfo(resume_hash="abc123"))
    db.add(c)
    db.commit()

    hit = repo.find_by_hash("abc123")
    assert hit is not None and hit.candidate_id == c.id
    assert repo.find_by_hash("not-exists") is None


def test_requirement_bulk_create(db):
    # 外键已开启：必须先建真实职位，job_id 不能凭空指向 1
    job = Job(name="AI算法工程师", status="open")
    db.add(job)
    db.commit()
    db.refresh(job)

    repo = RequirementRepository(db)
    created = repo.bulk_create(
        job_id=job.id,
        items=[{"name": "Python", "type": "必须", "importance": "高"}],
    )
    repo.commit()
    assert len(created) == 1 and created[0].id is not None

    assert len(repo.list_by_job(job.id)) == 1
    repo.delete_by_job(job.id)
    repo.commit()
    assert repo.list_by_job(job.id) == []
