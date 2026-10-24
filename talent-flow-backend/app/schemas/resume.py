from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    file_path: str = Field(..., description="简历文件路径")


class UploadResult(BaseModel):
    success: bool = True
    candidate_id: int


class ParseResult(BaseModel):
    name: str
    phone: str
    email: str
    position: str
    experience: str
