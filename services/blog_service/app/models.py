from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from sqlmodel import Field, SQLModel

class ArticleImage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    image_filename: str
    article_id: Optional[int] = Field(default=None, index=True)

class BlogArticle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: str
    create_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Seoul")))
    owner_id: int
    tags: Optional[str] = Field(default=None)

# ✅ Pydantic 모델들
class BlogArticleCreate(SQLModel):
    title: str
    content: str
    tags: Optional[str] = None

class BlogArticleUpdate(SQLModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None

class BlogArticlePublic(SQLModel):
    id: int
    title: str
    content: str
    create_at: datetime
    owner_id: int
    tags: Optional[str] = None
    image_url: Optional[str] = None
    author_username: Optional[str] = None  # ✅ 작성자 이름 추가
