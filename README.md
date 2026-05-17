# open-law

대한민국 **법제처 국가법령정보 공동활용 OPEN API([law.go.kr](https://www.law.go.kr))** 의 법령·판례 데이터를 LLM 도구로 노출하는 MCP(Model Context Protocol) 서버.

웹 검색이 *사람이* 법령을 찾게 해주고, 이 MCP는 *AI 에이전트가* 법령·판례를 자연어로 직접 검색·인용할 수 있게 한다.

## 무엇을 하는가

법제처 OPEN API는 현행 법령·행정규칙·자치법규·법령해석례·판례·헌재결정례 등 9종 데이터(target)를 제공한다. 본 MCP v1.1은 그중 가장 활용도가 높은 **법령 본문**과 **판례**를 4개 도구로 노출하며, 옵션 인자(응답 모드·약칭·소관부처·법원·선고일 필터)와 디스크 캐싱을 지원한다.

> *예* — "개인정보 보호법 제3조 본문 보여줘", "산집법 시행령에서 'M&A' 관련 조문 찾아줘", "네이트 개인정보 유출 손해배상 판결 요지 정리해줘"

## 아키텍처

```
Claude ──stdio──▶ server.py(MCP) ──HTTPS──▶ NAS proxy(FastAPI) ──HTTPS──▶ law.go.kr
                                              │
                                              └─ OC 자동 주입
                                              └─ X-Proxy-Token 인증
                                              └─ path 화이트리스트
```

법제처 OPEN API는 신청 시 등록한 **IP만 화이트리스트**로 허용한다(최대 4개). 노트북·집·이동망 등 환경마다 IP가 달라지면 일일이 재등록해야 하는 한계가 있다. 이 MCP는 NAS의 고정 외부 IP를 단일 게이트웨이로 두고, 클라이언트는 토큰만 가지고 어디서든 호출할 수 있게 설계했다.

## 제공 도구 (v1.1 — 4개)

### 1. `search_law(query, display=20, org=None, include_abbreviation=False)`

법령명으로 현행 법령을 검색해 MST(법령일련번호)·법령ID 획득.

**인자**
- `query` *(string, required)* — 법령명 또는 약칭
- `display` *(int, optional, 기본 20)* — 최대 결과 개수
- `org` *(string, optional)* — 소관부처명 부분일치 필터 (응답 후처리)
- `include_abbreviation` *(bool, optional, 기본 False)* — True면 내장 약칭 사전(`산집법`·`청탁금지법`·`공운법` 등 13종)으로 query 매핑

**반환 예**
```json
{
  "LawSearch": {
    "law": [{
      "법령일련번호": "270351",
      "법령ID": "011357",
      "법령명한글": "개인정보 보호법",
      "법령구분명": "법률",
      "소관부처명": "개인정보보호위원회",
      "시행일자": "20251002",
      "현행연혁코드": "현행"
    }],
    "totalCnt": "2"
  }
}
```

### 2. `get_law_text(mst, jo=None, mode="full")`

법령 본문 전체 또는 특정 조문 조회.

**인자**
- `mst` *(string, required)* — `search_law` 결과의 법령일련번호(MST)
- `jo` *(string, optional)* — 조문 지정. `"제3조"` 또는 6자리 코드 `"000300"`. 생략 시 전체
- `mode` *(string, optional, 기본 `"full"`)* — 응답 크기 제어 (jo 미지정일 때만 적용)
  - `"summary"`: 기본정보 + 조문목록(번호·제목·여부)만 (수 KB)
  - `"articles_only"`: 기본정보 + 조문 (부칙·개정문 제외)
  - `"full"`: 전체 (기본값, 호환성). 부칙 평탄화 결과를 `법령.부칙_flat` 키로 추가 노출

> 주의: 산집법·민법 등 큰 법령은 `mode="full"` 응답이 500 KB를 넘는다. 먼저 `mode="summary"`로 조문 구조를 파악한 뒤 필요한 조문만 `jo` 지정 호출하는 패턴을 권장한다.

**반환 예 (jo="000300")**
```json
{
  "법령": {
    "기본정보": {"법령명_한글": "개인정보 보호법", "시행일자": "20251002"},
    "조문": {
      "조문단위": {
        "조문번호": "3",
        "조문제목": "개인정보 보호 원칙",
        "항": [
          {"항번호": "① ", "항내용": "① 개인정보처리자는 ..."}
        ]
      }
    }
  }
}
```

### 3. `search_decisions(query, display=20, court=None, date_from=None, date_to=None)`

판례를 키워드로 검색.

**인자**
- `query` *(string, required)* — 검색어 (예: `"개인정보 유출"`, `"손해배상"`)
- `display` *(int, optional, 기본 20)*
- `court` *(string, optional)* — 법원명 정확매칭 (예: `"대법원"`, `"서울고등법원"`)
- `date_from`·`date_to` *(string, optional)* — 선고일 범위. `YYYYMMDD` / `YYYY-MM-DD` / `YYYY.MM.DD` / `YYYY/MM/DD` 수용. 한쪽만 지정 시 반대편은 무한대로 보충
  - 법제처 API는 `prncYd='YYYYMMDD~YYYYMMDD'` 형식만 지원(실측). 단일 날짜·다른 키는 무효

**반환 예**
```json
{
  "PrecSearch": {
    "prec": {
      "사건번호": "2015다24904",
      "법원명": "대법원",
      "선고일자": "2018.01.25",
      "판례일련번호": "193332",
      "사건명": "손해배상(기) (네이트·싸이월드 회원 개인정보 유출 사건)"
    }
  }
}
```

### 4. `get_decision_text(decision_id)`

판례 전문(판시사항·판결요지·참조조문·판례내용) 조회.

**인자**
- `decision_id` *(string, required)* — `search_decisions` 응답의 판례일련번호

## 설치

```bash
git clone https://github.com/giovinazo/open-law.git
cd open-law
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

요구사항: Python 3.10+, `mcp>=1.0.0`, `requests>=2.31.0`

## 설정

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "open-law": {
      "command": "/absolute/path/to/open-law/venv/bin/python",
      "args": ["/absolute/path/to/open-law/server.py"],
      "env": {
        "LAW_PROXY_TOKEN": "your-proxy-token-here"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add open-law -s user \
  -e LAW_PROXY_TOKEN=your-proxy-token-here \
  -- /absolute/path/to/open-law/venv/bin/python \
     /absolute/path/to/open-law/server.py
```

### 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `LAW_PROXY_TOKEN` | ✓ | — | NAS 프록시 인증 토큰 (X-Proxy-Token 헤더) |
| `LAW_PROXY_URL` | | `http://giovinazo.synology.me:8765` | NAS 프록시 base URL |
| `OPEN_LAW_CACHE` | | `1` | `0`이면 디스크 캐시 우회 (테스트·디버깅용) |

### 디스크 캐싱

`_call` 진입점에서 응답을 `~/.cache/open-law-mcp/<sha1>.json`에 저장한다(TTL 7일). 같은 호출 두 번째부터는 API를 거치지 않고 즉시 반환(실측 0.26s → 0.001s, 약 260배 가속). 법령 본문은 시행일 변경 전까지 불변이므로 일일 호출 한도 절감 효과가 크다.

- 캐시 키: `sha1(path + "|" + urlencode(sorted(params)))` — 토큰은 헤더라 키에서 제외
- `mode`·`org` 등 후처리 인자는 `_call` 외부에서 처리되므로 동일 raw 응답을 공유
- 손상된 캐시 파일은 자동으로 무시·재생성
- 끄려면 `OPEN_LAW_CACHE=0`

## NAS 프록시

`proxy/` 폴더는 NAS에서 항상 실행되는 FastAPI 중계 서버다.

**구성**
- `law_proxy.py` — FastAPI 앱 (`/health`, `/{lawSearch.do|lawService.do}`)
- `Dockerfile` + `docker-compose.yml` — Synology Container Manager 배포용
- `.env` — `PROXY_TOKEN`, `LAW_OC` (repo 제외)

**보안 계층**
1. `X-Proxy-Token` 헤더 검증 (32자 랜덤 토큰)
2. path 화이트리스트(`lawSearch.do`, `lawService.do`만 허용)
3. OC 파라미터 서버측 자동 주입 (클라이언트 노출 없음)

**배포**
```bash
cd proxy
cp .env.example .env  # PROXY_TOKEN, LAW_OC 설정
docker compose up -d
```

## 사용 예시

Claude에서 자연어 한 줄로:

| 질의 | 동원되는 도구 |
|---|---|
| "개인정보 보호법 찾아줘" | `search_law("개인정보 보호법")` |
| "그 법 제3조 보여줘" | `get_law_text(mst, "000300")` |
| "산집법 찾아줘" | `search_law("산집법", include_abbreviation=True)` |
| "산업통상자원부 소관 법령 중에서…" | `search_law("법", org="산업통상자원부")` |
| "산집법 구조만 빠르게" | `search_law(...)` → `get_law_text(mst, mode="summary")` |
| "대법원 2020~2025 개인정보 판례" | `search_decisions("개인정보", court="대법원", date_from="20200101", date_to="20251231")` |
| "네이트 개인정보 유출 판결 요지" | `search_decisions("개인정보 유출")` → `get_decision_text(id)` |

## 주의사항

- **한글 query는 자동 URL 인코딩**: `type=JSON` 모드에서 한글 query를 인코딩 없이 보내면 응답 body가 `{}`로 비어 반환되는 함정이 있다. `requests` 라이브러리는 자동 처리하므로 본 MCP는 안전.
- **법령 약칭**: 기본은 정식 명칭 검색. `include_abbreviation=True`로 내장 사전(13종) 매핑 사용 가능. 사전에 없는 약칭은 그대로 검색됨.
- **일일 호출 제한**: 법제처 OPEN API는 일일 호출 한도가 있다(초과 시 차단). v1.1부터 디스크 캐시(TTL 7일)로 반복 호출 절감.
- **선고일 필터 형식**: `search_decisions`의 `date_from/to`는 반드시 범위 호출로 보내진다. 단일 날짜의 prncYd, prncYdStart/End, dateFrom/To는 API가 무시한다(실측 확인).

## 데이터 출처 / API 참고

| 엔드포인트 | 용도 | 사용 도구 |
|---|---|---|
| `GET /DRF/lawSearch.do?target=law` | 법령 검색 | `search_law` |
| `GET /DRF/lawService.do?target=law&MST=...` | 법령 본문/조문 | `get_law_text` |
| `GET /DRF/lawSearch.do?target=prec` | 판례 검색 | `search_decisions` |
| `GET /DRF/lawService.do?target=prec&ID=...` | 판례 전문 | `get_decision_text` |

법제처가 제공하는 9종 target 중 V1은 `law`·`prec` 2종 한정. 추후 `admrul`(행정규칙)·`expc`(법령해석례)·`pi`(공공기관 규정) 등 확대 예정.

## 라이선스

내부용(private). 외부 배포 미지원.

법제처가 제공하는 법령·판례 데이터 자체는 **공공누리 또는 공공데이터법**에 따른 공공 데이터로, 본 도구는 단순한 접근 인터페이스를 제공한다.

## 만든 이유

공공기관 자체감사·규정 검토 업무 중 근거 법령 인용·조문 확인·유사 판례 조회가 빈번한데, 매번 국가법령정보센터에서 검색해 본문을 복사하고 조문을 발췌하는 작업이 비효율적이었다. 더구나 IP 화이트리스트 정책으로 환경별 IP 변동에 매번 재등록이 필요해 불편했다. AI 에이전트가 직접 법령·판례를 검색·인용할 수 있고 어디서든 동작하는 환경을 만들기 위해 구축했다.

## 변경 이력

- **v1.1** (2026-05-17) — 외부 개선 지시서 1차 반영
  - `get_law_text`에 `mode=summary|articles_only|full` 파라미터(작업 4), 부칙 평탄화 `부칙_flat` 키(작업 3)
  - `search_law`에 약칭 사전 13종·`org` 소관부처 필터(작업 7)
  - `search_decisions`에 `court`·`date_from`·`date_to` 필터(작업 8, 법제처 API 실측 매핑)
  - `_call` 진입점에 디스크 캐싱 TTL 7일, `OPEN_LAW_CACHE` 토글(작업 5)
  - 4개 도구 docstring 형식 통일(작업 1·9)
- **v1.0** (2026-05-17) — GitHub private 등록. 도구 4종, NAS 프록시 경유 구조.
- (2026-05-16) NAS 프록시(IP 화이트리스트 우회) 도입
- (2026-04-26) 초기 FastMCP 서버 구축

## 후속 계획

- [ ] **`list_law_history` / `get_law_text_at`** — 법령 개정 이력·시점 본문 조회 (법제처 `lsHstGrp`/`lsHstInf` 엔드포인트 명세 확정 + NAS 프록시 `ALLOWED_PATHS` 확장 후)
- [ ] `verify_citations` — 본문 인용 검증 (인용된 법령·조문이 현행인지 / 개정 이력 추적)
- [ ] `chain_search_then_text` — 검색 후 자동으로 본문 조회까지 한 번에
- [ ] target 확대 — `admrul`(행정규칙)·`expc`(법령해석례)·`pi`(공공기관 규정) 도구 추가
- [ ] 약칭 사전 외부화 — 항목 20종 초과 시 별도 JSON 파일로 분리

---

**English summary**: MCP server exposing Korea's National Law Information Center (law.go.kr) for LLM agents. Provides 4 tools (law search, law text/article, case-law search, case-law text) with optional filters (response mode, abbreviation map, jurisdictional org, court, sentencing-date range) and 7-day disk cache. Uses a NAS-hosted FastAPI proxy to bypass the law.go.kr IP-whitelist limitation. v1.1.
