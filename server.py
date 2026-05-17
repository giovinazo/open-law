"""법제처 OPEN API MCP 서버 (NAS 프록시 경유).

환경변수:
    LAW_PROXY_URL   NAS 프록시 base URL (기본 http://giovinazo.synology.me:8765)
    LAW_PROXY_TOKEN X-Proxy-Token 값 (필수)

NAS 프록시가 OC=giovinazo를 자동 주입하므로 클라이언트는 토큰만 보내면 됨.
화이트리스트가 NAS 외부 IP로 통합돼 어느 환경에서나 호출 가능.
"""

import os
import requests
from mcp.server.fastmcp import FastMCP

PROXY_URL = os.environ.get("LAW_PROXY_URL", "http://giovinazo.synology.me:8765").rstrip("/")
TIMEOUT = 30

mcp = FastMCP("open-law")


def _call(path: str, params: dict) -> dict:
    token = os.environ.get("LAW_PROXY_TOKEN")
    if not token:
        raise RuntimeError("환경변수 LAW_PROXY_TOKEN 미설정. MCP 설정에 주입 필요.")
    full = {"type": "JSON", **params}
    headers = {"X-Proxy-Token": token}
    r = requests.get(f"{PROXY_URL}/{path}", params=full, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def search_law(query: str, display: int = 20) -> dict:
    """법령명으로 현행 법령을 검색해 MST·법령ID를 얻는다.

    Args:
        query: 검색할 법령명 (예: '개인정보보호법', '관세법')
        display: 최대 결과 개수 (기본 20)
    """
    return _call("lawSearch.do", {"target": "law", "query": query, "display": display})


@mcp.tool()
def get_law_text(mst: str, jo: str | None = None) -> dict:
    """법령 본문 또는 특정 조문을 가져온다.

    Args:
        mst: search_law 결과의 법령일련번호(MST)
        jo: 조문 지정 (예: '제3조' 또는 6자리 코드 '000300'). 생략 시 전체.
    """
    params = {"target": "law", "MST": mst}
    if jo:
        params["JO"] = jo
    return _call("lawService.do", params)


@mcp.tool()
def search_decisions(query: str, display: int = 20) -> dict:
    """판례를 키워드로 검색한다.

    Args:
        query: 검색어 (예: '손해배상', '개인정보 유출')
        display: 최대 결과 개수 (기본 20)
    """
    return _call("lawSearch.do", {"target": "prec", "query": query, "display": display})


@mcp.tool()
def get_decision_text(decision_id: str) -> dict:
    """판례 전문을 ID로 조회한다.

    Args:
        decision_id: search_decisions 결과의 판례일련번호
    """
    return _call("lawService.do", {"target": "prec", "ID": decision_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
