from .base import BaseRepository
from .candidate_repository import CandidateRepository
from .department_repository import DepartmentRepository
from .job_repository import JobRepository
from .jobfit_repository import JobFitRepository
from .match_repository import MatchRepository
from .requirement_repository import RequirementRepository
from .resume_repository import ResumeRepository
from .template_repository import TemplateRepository

__all__ = [
    "BaseRepository",
    "CandidateRepository",
    "DepartmentRepository",
    "JobRepository",
    "JobFitRepository",
    "MatchRepository",
    "RequirementRepository",
    "ResumeRepository",
    "TemplateRepository",
]
