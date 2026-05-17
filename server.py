"""법제처 OPEN API MCP 서버 (NAS 프록시 경유).

환경변수:
    LAW_PROXY_URL   NAS 프록시 base URL (기본 http://giovinazo.synology.me:8765)
    LAW_PROXY_TOKEN X-Proxy-Token 값 (필수)

NAS 프록시가 OC=giovinazo를 자동 주입하므로 클라이언트는 토큰만 보내면 됨.
화이트리스트가 NAS 외부 IP로 통합돼 어느 환경에서나 호출 가능.
"""

import os
from typing import Literal

import requests
from mcp.server.fastmcp import FastMCP

PROXY_URL = os.environ.get("LAW_PROXY_URL", "http://giovinazo.synology.me:8765").rstrip("/")
TIMEOUT = 30

# 자주 쓰는 법령 약칭 → 정식 명칭 (search_law include_abbreviation=True 시 적용)
# TODO: 20개 초과 시 별도 JSON으로 분리.
_LAW_ABBR = {
    "산집법": "산업집적활성화 및 공장설립에 관한 법률",
    "산업단지법": "산업입지 및 개발에 관한 법률",
    "개보법": "개인정보 보호법",
    "개인정보법": "개인정보 보호법",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "공정거래법": "독점규제 및 공정거래에 관한 법률",
    "근기법": "근로기준법",
    "산안법": "산업안전보건법",
    "공공기관운영법": "공공기관의 운영에 관한 법률",
    "공운법": "공공기관의 운영에 관한 법률",
    "국정감사법": "국정감사 및 조사에 관한 법률",
    "부정청탁법": "부정청탁 및 금품등 수수의 금지에 관한 법률",
    "청탁금지법": "부정청탁 및 금품등 수수의 금지에 관한 법률",
}

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


def _normalize_date(s: str | None) -> str | None:
    """YYYYMMDD·YYYY-MM-DD·YYYY/MM/DD·YYYY.MM.DD 모두 받아 YYYYMMDD로 정규화."""
    if not s:
        return None
    cleaned = s.replace("-", "").replace("/", "").replace(".", "")
    if len(cleaned) != 8 or not cleaned.isdigit():
        raise ValueError(f"날짜는 YYYYMMDD 또는 YYYY-MM-DD 형식이어야 합니다 (입력값: {s!r})")
    return cleaned


def _normalize_buchik(buchik_block: dict | None) -> list[dict]:
    """법령 응답의 부칙 블록을 평탄화한다.

    원본은 ``{"부칙단위": [{...}, ...]}`` (단건 시 dict)이며 각 단위의
    ``부칙내용``은 ``list[list[str]]`` 이중 리스트라 LLM이 다루기 어렵다.
    이를 ``[{공포일자, 공포번호, 부칙키, 내용(str)}]`` 형태로 평탄화한다.
    """
    if not buchik_block:
        return []
    units = buchik_block.get("부칙단위", [])
    if isinstance(units, dict):
        units = [units]
    out = []
    for unit in units:
        lines: list[str] = []
        for block in unit.get("부칙내용", []):
            if isinstance(block, list):
                lines.extend(str(x) for x in block if x is not None)
            elif block:
                lines.append(str(block))
        out.append({
            "공포일자": unit.get("부칙공포일자"),
            "공포번호": unit.get("부칙공포번호"),
            "부칙키": unit.get("부칙키"),
            "내용": "\n".join(lines),
        })
    return out


@mcp.tool()
def search_law(
    query: str,
    display: int = 20,
    org: str | None = None,
    include_abbreviation: bool = False,
) -> dict:
    """법령명으로 현행 법령을 검색하여 MST(법령일련번호)·법령ID를 얻는다.

    Args:
        query: 법령명 또는 약칭. 기본은 정식 명칭으로 검색
            (예: '개인정보 보호법'). 약칭으로 검색하려면
            include_abbreviation=True (예: '산집법', '청탁금지법').
        display: 최대 결과 개수. 기본 20.
        org: 소관부처명 부분일치 필터 (예: '산업통상자원부',
            '개인정보보호위원회'). 응답 후처리.
        include_abbreviation: True면 query를 내장 약칭 사전으로 매핑.
            기본 False (기존 동작 유지).

    Returns:
        {"LawSearch": {"law": [{법령일련번호, 법령명한글, 소관부처명,
        시행일자, 현행연혁코드, ...}], "totalCnt": "N"}}

    Examples:
        search_law("개인정보 보호법")
        search_law("산집법", include_abbreviation=True)
        search_law("관세법", org="기획재정부")
    """
    q = _LAW_ABBR.get(query, query) if include_abbreviation else query
    res = _call("lawSearch.do", {"target": "law", "query": q, "display": display})
    if org:
        search = res.get("LawSearch")
        if isinstance(search, dict):
            laws = search.get("law", [])
            if isinstance(laws, dict):
                laws = [laws]
            filtered = [x for x in laws if isinstance(x, dict) and org in (x.get("소관부처명") or "")]
            search["law"] = filtered
            search["totalCnt"] = str(len(filtered))
    return res


@mcp.tool()
def get_law_text(
    mst: str,
    jo: str | None = None,
    mode: Literal["summary", "articles_only", "full"] = "full",
) -> dict:
    """법령 본문 또는 특정 조문을 조회한다.

    주의: 큰 법령(민법·형법·산집법 등)은 전체 응답이 수백 KB~1 MB에
    달해 LLM 컨텍스트 로드 실패가 잦다. mode='summary'로 구조 먼저
    확인 후 필요한 조문만 jo로 재호출하는 패턴을 권장한다.

    Args:
        mst: search_law 결과의 법령일련번호(MST). 예: '270351'.
        jo: 조문 지정. '제3조' 또는 6자리 코드 '000300'. 생략 시 전체.
        mode: 응답 크기 제어 (jo 미지정일 때만 적용):
            - 'summary': 기본정보 + 조문 목록(번호·제목·여부)만 (수 KB)
            - 'articles_only': 기본정보 + 조문(부칙·개정문 제외)
            - 'full': 전체 (기본값, 호환성 유지)

    Returns:
        mode='full': {"법령": {"기본정보", "조문", "부칙", "개정문",
            "제개정이유"}}
        mode='summary': {"기본정보": {...}, "조문수": N,
            "조문목록": [{"조문번호", "조문제목", "조문여부"}, ...]}
        mode='articles_only': {"기본정보": {...}, "조문": {...}}

    Examples:
        get_law_text(mst="270351", jo="000300")          # 제3조
        get_law_text(mst="283929", mode="summary")        # 산집법 구조만
        get_law_text(mst="283929", mode="articles_only")  # 산집법 조문만
    """
    params = {"target": "law", "MST": mst}
    if jo:
        params["JO"] = jo
    raw = _call("lawService.do", params)

    if jo or mode == "full":
        body = raw.get("법령")
        if isinstance(body, dict) and body.get("부칙"):
            body["부칙_flat"] = _normalize_buchik(body["부칙"])
        return raw

    body = raw.get("법령", {})
    units = body.get("조문", {}).get("조문단위", [])
    if isinstance(units, dict):
        units = [units]

    if mode == "summary":
        return {
            "기본정보": body.get("기본정보"),
            "조문수": len(units),
            "조문목록": [
                {
                    "조문번호": u.get("조문번호"),
                    "조문제목": u.get("조문제목"),
                    "조문여부": u.get("조문여부"),
                }
                for u in units
            ],
        }
    return {
        "기본정보": body.get("기본정보"),
        "조문": body.get("조문"),
    }


@mcp.tool()
def search_decisions(
    query: str,
    display: int = 20,
    court: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """판례를 키워드로 검색한다.

    Args:
        query: 검색어 (예: '손해배상', '개인정보 유출').
        display: 최대 결과 개수. 기본 20.
        court: 법원명 정확매칭 (예: '대법원', '서울고등법원').
        date_from: 선고일 시작. YYYYMMDD 또는 YYYY-MM-DD.
        date_to: 선고일 종료. YYYYMMDD 또는 YYYY-MM-DD.
            from/to 어느 한쪽만 지정하면 반대쪽은 무한대로 처리.
            (법제처 API는 prncYd 범위 'YYYYMMDD~YYYYMMDD'만 지원)

    Returns:
        {"PrecSearch": {"prec": [{판례일련번호, 사건번호, 법원명,
        선고일자, 사건명, ...}], "totalCnt": "N"}}

    Examples:
        search_decisions("개인정보 유출")
        search_decisions("손해배상", court="대법원")
        search_decisions("개인정보", date_from="20200101", date_to="2025-12-31")
    """
    params: dict = {"target": "prec", "query": query, "display": display}
    if court:
        params["curt"] = court
    df = _normalize_date(date_from)
    dt = _normalize_date(date_to)
    if df or dt:
        params["prncYd"] = f"{df or '00010101'}~{dt or '99991231'}"
    return _call("lawSearch.do", params)


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
