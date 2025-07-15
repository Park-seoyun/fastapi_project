import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException

app = FastAPI(title="API Gateway")

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")
BLOG_SERVICE_URL = os.getenv("BLOG_SERVICE_URL")  # ✅ 블로그 서비스 URL 추가

@app.on_event("startup")
async def startup_event():
    app.state.client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.client.aclose()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def reverse_proxy(request: Request):
    path = request.url.path
    client: httpx.AsyncClient = request.app.state.client

    if path.startswith("/api/users") or path.startswith("/api/auth"):
        base_url = USER_SERVICE_URL
    elif path.startswith("/api/blogs"):  # ✅ blog_service 경로 처리 추가
        base_url = BLOG_SERVICE_URL
    else:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    url = f"{base_url}{path}?{request.url.query}"

    try:
        rp_resp = await client.request(
        method=request.method,
        url=url,
        headers={**request.headers},
        cookies=request.cookies,  # ✅ 쿠키 직접 전달
        content=await request.body()
    )
        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=rp_resp.headers
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
