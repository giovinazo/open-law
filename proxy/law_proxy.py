"""법제처 OPEN API HTTP 중계 프록시.

NAS에서 항상 실행 → 외부 클라이언트는 NAS 도메인 경유로 법제처 호출.
법제처는 NAS의 외부 IP만 화이트리스트에 등록하면 됨.

실행:
    PROXY_TOKEN=xxxx uvicorn law_proxy:app --host 0.0.0.0 --port 8765

클라이언트 호출:
    curl 'https://<NAS도메인>:8765/lawSearch.do?target=law&type=JSON&query=개인정보보호법' \
        -H 'X-Proxy-Token: xxxx'
"""

import os
import logging
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response

LAW_BASE = "https://www.law.go.kr/DRF"
LAW_OC = os.environ.get("LAW_OC", "giovinazo")
PROXY_TOKEN = os.environ.get("PROXY_TOKEN")
TIMEOUT = 30

ALLOWED_PATHS = {"lawSearch.do", "lawService.do"}

app = FastAPI(title="law.go.kr proxy")
logger = logging.getLogger("law_proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.get("/health")
def health():
    return {"status": "ok", "oc": LAW_OC, "auth_required": bool(PROXY_TOKEN)}


@app.get("/{path:path}")
async def proxy(path: str, request: Request):
    if PROXY_TOKEN and request.headers.get("X-Proxy-Token") != PROXY_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    if path not in ALLOWED_PATHS:
        raise HTTPException(status_code=404, detail=f"path not allowed: {path}")

    params = dict(request.query_params)
    params["OC"] = LAW_OC

    upstream_url = f"{LAW_BASE}/{path}"
    try:
        r = requests.get(upstream_url, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"upstream error: {e}")
        raise HTTPException(status_code=502, detail=f"upstream: {e}") from e

    client_ip = request.client.host if request.client else "?"
    logger.info(f"{client_ip} {path} target={params.get('target')} → {r.status_code} {len(r.content)}B")

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
