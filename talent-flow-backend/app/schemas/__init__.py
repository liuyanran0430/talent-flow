from .candidate import CandidateCreate, CandidateOut, CandidateUpdate
from .common import ApiResponse, PageParams, PageResponse
from .job import JobCreate, JobOut, JobUpdate, JobWithStats
from .jobfit import JobFitCreate, JobFitOut, JobFitUpdate
from .requirement import (
    RequirementItemCreate,
    RequirementItemOut,
    RequirementItemUpdate,
)
from .template import (
    ApplyTemplateRequest,
    RequirementTemplateCreate,
    RequirementTemplateOut,
    RequirementTemplateUpdate,
    TemplateItemCreate,
    TemplateItemOut,
    TemplateItemUpdate,
)

__all__ = [
    "ApiResponse",
    "PageParams",
    "PageResponse",
    "JobCreate",
    "JobOut",
    "JobUpdate",
    "JobWithStats",
    "CandidateCreate",
    "CandidateOut",
    "CandidateUpdate",
    "RequirementItemCreate",
    "RequirementItemOut",
    "RequirementItemUpdate",
    "RequirementTemplateCreate",
    "RequirementTemplateOut",
    "RequirementTemplateUpdate",
    "TemplateItemCreate",
    "TemplateItemOut",
    "TemplateItemUpdate",
    "JobFitCreate",
    "JobFitOut",
    "JobFitUpdate",
    "ApplyTemplateRequest",
    "ParseRequest",
    "ParseResult",
]
