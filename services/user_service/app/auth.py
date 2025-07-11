import secrets
from typing import Optional
from passlib.context import CryptContext
from redis.asyncio import Redis

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_TTL_SECONDS = 3600

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

async def delete_session(redis: Redis, session_id:str):
    await redis.delete(f"session:{session_id}")

async def create_session(redis: Redis, user_id: int) -> str:
    session_id = secrets.token_hex(16)
    await redis.setex(f"session:{session_id}", SESSION_TTL_SECONDS, user_id)
    return session_id

