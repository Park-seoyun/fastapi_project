import os
from typing import Annotated
from fastapi import FastAPI, status, Response, Depends, HTTPException, Cookie, UploadFile, File
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

# 모델과 유틸리티
from models import User, UserCreate, UserPublic, UserLogin, UserUpdate, UserChangePassword
from database import init_db, get_session
from redis_client import get_redis
from auth import (
    get_password_hash,
    verify_password,
    create_session,
    delete_session
)

app = FastAPI(title="User Service")

# Static 디렉토리 설정
STATIC_DIR = "/app/static"
PROFILE_IMAGE_DIR = f"{STATIC_DIR}/profiles"
os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 유저 공개 데이터 생성 함수
def create_user_public(user: User) -> UserPublic:
    image_url = f"/static/profiles/{user.profile_image_filename}" if user.profile_image_filename \
        else "https://www.w3schools.com/w3images/avatar_g.jpg"
    user_dict = user.model_dump()
    user_dict["profile_image_url"] = image_url
    return UserPublic.model_validate(user_dict)

# DB 초기화
@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/")
def health_check():
    return {"status": "User service running"}

# ✅ 회원가입
@app.post("/api/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    response: Response,
    user_data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)]
):
    statement = select(User).where(User.email == user_data.email)
    exist_user_result = await session.exec(statement)
    if exist_user_result.one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용중인 이메일 입니다.")
    
    hashed_password = get_password_hash(user_data.password)
    new_user = User.model_validate(user_data, update={"hashed_password": hashed_password})
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    # 회원가입 후 자동 로그인 처리
    session_id = await create_session(redis, new_user.id)
    response.set_cookie(
        key="session_id", value=session_id,
        httponly=True, samesite="lax", max_age=3600, path="/"
    )

    return create_user_public(new_user)

# ✅ 로그인
@app.post("/api/auth/login", response_model=UserPublic)
async def login_user(
    response: Response,
    user_data: UserLogin,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)]
):
    statement = select(User).where(User.email == user_data.email)
    result = await session.exec(statement)
    user = result.one_or_none()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    
    session_id = await create_session(redis, user.id)
    response.set_cookie(
        key="session_id", value=session_id,
        httponly=True, samesite="lax", max_age=3600, path="/"
    )
    return create_user_public(user)

# ✅ 현재 로그인한 유저 정보
@app.get("/api/auth/me", response_model=UserPublic)
async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    response: Response,
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    user_id = await redis.get(f"session:{session_id}")
    if not user_id:
        response.delete_cookie("session_id", path="/")
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    statement = select(User).where(User.id == int(user_id))
    result = await session.exec(statement)
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return create_user_public(user)

# ✅ 로그아웃
@app.post("/api/auth/logout")
async def logout(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    response: Response,
    session_id: Annotated[str | None, Cookie()] = None
):
    if session_id:
        await delete_session(redis, session_id)
    response.delete_cookie("session_id", path="/")
    return {"message": "Logout 성공"}

# ✅ 회원정보 수정
@app.put("/api/users/me", response_model=UserPublic)
async def update_current_user(
    user_data: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")
    
    user_id = await redis.get(f"session:{session_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")
    
    statement = select(User).where(User.id == int(user_id))
    result = await session.exec(statement)
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user.username = user_data.username or user.username
    user.bio = user_data.bio or user.bio

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return create_user_public(user)

# ✅ 비밀번호 변경
@app.put("/api/users/me/change-password")
async def change_password(
    password_data: UserChangePassword,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    user_id = await redis.get(f"session:{session_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    statement = select(User).where(User.id == int(user_id))
    result = await session.exec(statement)
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")

    user.hashed_password = get_password_hash(password_data.new_password)
    session.add(user)
    await session.commit()

    return {"message": "비밀번호 변경 완료"}

@app.post("/api/users/me/upload-image")
async def upload_profile_image(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[str | None, Cookie()] = None
):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인 되어있지 않습니다.")

    user_id = await redis.get(f"session:{session_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    # 사용자 조회
    statement = select(User).where(User.id == int(user_id))
    result = await session.exec(statement)
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 파일 저장
    filename = f"user_{user.id}_{file.filename}"
    file_location = os.path.join(PROFILE_IMAGE_DIR, filename)
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())

    user.profile_image_filename = filename
    session.add(user)
    await session.commit()

    return {"message": "프로필 이미지 업로드 완료", "profile_image_url": f"/static/profiles/{filename}"}
