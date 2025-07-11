import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi import FastAPI, Request
import httpx

app = FastAPI(title="API Gateway")

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")

@app.on_event("startup")
async def startup_event():
    app.state.client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.client.aclose()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def reverse_proxy(request : Request):
    path = request.url.path
    client: httpx.AsyncClient = request.app.state.client
    
    if path.startswith("/api/users") or path.startswith("/api/auth"):
        base_url = USER_SERVICE_URL
    else:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    
    url = f"{base_url}{path}?{request.url.query}"
    
    try:
        rp_resp = await client.request(
            method=request.method,
            url=url,
            headers=request.headers,
            content=await request.body()
        )
        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=rp_resp.headers
        )
    except httpx.ConnectError:
        raise HTTPException(Status_code=503, detail="Service unavailable")