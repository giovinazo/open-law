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
    """법령명으로 현행 법령을 검색하여 MST(법령일련번호)·법령ID를 얻는다.

    Args:
        query: 법령명. 정식 명칭 권장 (예: '개인정보 보호법', '관세법').
            약칭(예: '산집법')은 미매칭일 수 있다.
        display: 최대 결과 개수. 기본 20.

    Returns:
        {"LawSearch": {"law": [{법령일련번호, 법령명한글, 소관부처명,
        시행일자, 현행연혁코드, ...}], "totalCnt": "N"}}

    Examples:
        search_law("개인정보 보호법")
        search_law("관세법", display=5)
    """
    return _call("lawSearch.do", {"target": "law", "query": query, "display": display})


@mcp.tool()
def get_law_text(mst: str, jo: str | None = None) -> dict:
    """법령 본문 또는 특정 조문을 조회한다.

    주의: 큰 법령(민법·형법·산집법 등)은 전체 응답이 수백 KB~1 MB에
    달해 LLM 컨텍스트 로드 실패가 잦다. 다음 순서를 권장한다.
      1단계: jo 생략 호출로 기본정보·조문 구조 먼저 확인
      2단계: 필요한 조문만 jo='제13조' 형태로 재호출

    Args:
        mst: search_law 결과의 법령일련번호(MST). 예: '270351'.
        jo: 조문 지정. '제3조' 또는 6자리 코드 '000300'. 생략 시 전체.

    Returns:
        {"법령": {"기본정보": {...}, "조문": {"조문단위": [...]},
        "부칙": {"부칙단위": [...]}, "개정문": {...}, "제개정이유": {...}}}

    Examples:
        get_law_text(mst="270351", jo="000300")  # 개인정보보호법 제3조
        get_law_text(mst="270351")                # 전체(큰 법령은 주의)
    """
    params = {"target": "law", "MST": mst}
    if jo:
        params["JO"] = jo
    return _call("lawService.do", params)


@mcp.tool()
def search_decisions(query: str, display: int = 20) -> dict:
    """판례를 키워드로 검색한다.

    Args:
        query: 검색어 (예: '손해배상', '개인정보 유출', '공동불법행위').
        display: 최대 결과 개수. 기본 20.

    Returns:
        {"PrecSearch": {"prec": [{판례일련번호, 사건번호, 법원명,
        선고일자, 사건명, ...}], "totalCnt": "N"}}

    Examples:
        search_decisions("개인정보 유출")
        search_decisions("손해배상", display=10)
    """
    return _call("lawSearch.do", {"target": "prec", "query": query, "display": display})


@mcp.tool()
def get_decision_text(decision_id: str) -> dict:
    """판례 전문(판시사항·판결요지·참조조문·판례내용)을 ID로 조회한다.

    Args:
        decision_id: search_decisions 응답의 판례일련번호. 예: '193332'.

    Returns:
        {"PrecService": {판시사항, 판결요지, 참조조문, 참조판례,
        판례내용, 사건번호, 법원명, 선고일자, ...}}

    Examples:
        get_decision_text(decision_id="193332")  # 2015다24904 네이트 사건
    """
    return _call("lawService.do", {"target": "prec", "ID": decision_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
