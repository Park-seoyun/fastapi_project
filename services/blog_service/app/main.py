import os
from typing import Annotated, Optional
from fastapi import FastAPI, status, Depends, HTTPException, Cookie, UploadFile, File
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis
import httpx  # ✅ user_service 호출용
from fastapi.responses import JSONResponse

from models import (
    BlogArticle, BlogArticleCreate, BlogArticleUpdate, BlogArticlePublic, ArticleImage
)
from database import init_db, get_session
from redis_client import get_redis

app = FastAPI(title="Blog Service")

# ✅ Static 디렉토리 설정
STATIC_DIR = "/app/static"
ARTICLE_IMAGE_DIR = f"{STATIC_DIR}/articles"
os.makedirs(ARTICLE_IMAGE_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ✅ user_service URL (api_gateway 경유로 고정)
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api_gateway:8000")
USER_SERVICE_URL = f"{API_GATEWAY_URL}/api/users"


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/")
def health_check():
    return {"status": "Blog service running"}


# ✅ 게시글 + 이미지 URL + 작성자 이름 + 소유자 여부 생성 함수
async def create_blog_public(
    blog: BlogArticle,
    session: AsyncSession,
    image: Optional[ArticleImage],
    current_user_id: Optional[int] = None,
) -> BlogArticlePublic:
    image_url = (
        f"/static/articles/{image.image_filename}"
        if image else None
    )

    # ✅ 작성자 이름 user_service API 호출
    author_username = f"사용자_{blog.owner_id}"
    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(f"{USER_SERVICE_URL}/{blog.owner_id}")
            if user_resp.status_code == 200:
                user_data = user_resp.json()
                author_username = user_data.get("username", author_username)
    except Exception as e:
        print(f"작성자 이름 가져오기 실패: {e}")

    is_owner = blog.owner_id == current_user_id

    return BlogArticlePublic.model_validate(
        blog,
        update={
            "image_url": image_url,
            "author_username": author_username,
            "is_owner": is_owner,
        }
    )


# ✅ 게시글 작성
@app.post("/api/blogs/", response_model=BlogArticlePublic, status_code=status.HTTP_201_CREATED)
async def create_blog(
    blog_data: BlogArticleCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    owner_id = await redis.get(f"session:{session_id}")
    if not owner_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    blog = BlogArticle.model_validate(blog_data, update={"owner_id": int(owner_id)})
    session.add(blog)
    await session.commit()
    await session.refresh(blog)

    stmt = select(ArticleImage).where(ArticleImage.article_id == blog.id)
    img_result = await session.exec(stmt)
    image = img_result.first()

    return await create_blog_public(blog, session, image, current_user_id=int(owner_id))


# ✅ 게시글 목록 조회

@app.get("/api/blogs/")
async def list_blogs(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    current_user_id = None
    if session_id:
        owner_id = await redis.get(f"session:{session_id}")
        if owner_id:
            current_user_id = int(owner_id)

    statement = select(BlogArticle).order_by(BlogArticle.create_at.desc())
    result = await session.exec(statement)
    blogs = result.all()

    blog_public_list = []
    for blog in blogs:
        img_stmt = select(ArticleImage).where(ArticleImage.article_id == blog.id)
        img_result = await session.exec(img_stmt)
        image = img_result.first()
        blog_public_list.append(await create_blog_public(blog, session, image, current_user_id=current_user_id))

    # ✅ 항상 items와 total 포함해서 반환
    return {"items": blog_public_list, "total": len(blog_public_list)}


# ✅ 게시글 단일 조회
@app.get("/api/blogs/{blog_id}", response_model=BlogArticlePublic)
async def get_blog(
    blog_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    current_user_id = None
    if session_id:
        owner_id = await redis.get(f"session:{session_id}")
        if owner_id:
            current_user_id = int(owner_id)

    blog = await session.get(BlogArticle, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    stmt = select(ArticleImage).where(ArticleImage.article_id == blog.id)
    img_result = await session.exec(stmt)
    image = img_result.first()

    return await create_blog_public(blog, session, image, current_user_id=current_user_id)


# ✅ 게시글 수정
@app.put("/api/blogs/{blog_id}", response_model=BlogArticlePublic)
async def update_blog(
    blog_id: int,
    blog_data: BlogArticleUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    owner_id = await redis.get(f"session:{session_id}")
    if not owner_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    blog = await session.get(BlogArticle, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if blog.owner_id != int(owner_id):
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다.")

    blog.title = blog_data.title or blog.title
    blog.content = blog_data.content or blog.content
    blog.tags = blog_data.tags or blog.tags

    session.add(blog)
    await session.commit()
    await session.refresh(blog)

    stmt = select(ArticleImage).where(ArticleImage.article_id == blog.id)
    img_result = await session.exec(stmt)
    image = img_result.first()

    return await create_blog_public(blog, session, image, current_user_id=int(owner_id))


# ✅ 게시글 삭제
@app.delete("/api/blogs/{blog_id}")
async def delete_blog(
    blog_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    owner_id = await redis.get(f"session:{session_id}")
    if not owner_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    blog = await session.get(BlogArticle, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if blog.owner_id != int(owner_id):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    await session.delete(blog)
    await session.commit()
    return {"message": "게시글이 삭제되었습니다."}


# ✅ 게시글 이미지 업로드
@app.post("/api/blogs/{blog_id}/upload-image")
async def upload_article_image(
    blog_id: int,
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    owner_id = await redis.get(f"session:{session_id}")
    if not owner_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    blog = await session.get(BlogArticle, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if blog.owner_id != int(owner_id):
        raise HTTPException(status_code=403, detail="이미지 업로드 권한이 없습니다.")

    filename = f"article_{blog.id}_{file.filename}"
    file_location = os.path.join(ARTICLE_IMAGE_DIR, filename)
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())

    article_image = ArticleImage(image_filename=filename, article_id=blog.id)
    session.add(article_image)
    await session.commit()

    return {"message": "이미지 업로드 완료", "image_url": f"/static/articles/{filename}"}

