import os
import httpx
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.datastructures import MutableHeaders

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        public_paths = ["/api/auth/login", "/api/auth/register"]

        # GET, OPTIONS 메서드이거나 public path면 인증 없이 통과
        if request.method in ("GET", "OPTIONS") or request.url.path in public_paths:
            return await call_next(request)

        # 세션 쿠키 확인
        session_id = request.cookies.get("session_id")
        if not session_id:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                auth_url = f"{USER_SERVICE_URL}/api/auth/me"
                auth_resp = await client.get(auth_url, cookies={"session_id": session_id})

                if auth_resp.status_code != 200:
                    return JSONResponse(
                        status_code=auth_resp.status_code,
                        content=auth_resp.json()
                    )

                try:
                    user_data = auth_resp.json()
                except ValueError:
                    return JSONResponse(
                        status_code=502,
                        content={"detail": "Invalid auth response"}
                    )

                user_id = str(user_data.get("id"))
                new_headers = request.headers.mutablecopy()
                new_headers["X-User-Id"] = user_id
                request.scope["headers"] = new_headers.raw

        except httpx.RequestError as e:
            # 예: 로그 찍기 -> logger.error(f"Auth service failed: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": "User service is unavailable"}
            )

        # 요청 처리 계속
        response = await call_next(request)
        return response
