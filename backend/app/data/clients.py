"""소스별 얇은 클라이언트 함수.

설계 원칙:
- **graceful degradation**: 키 없음 / 네트워크 오류 / 라이브러리 미설치 → 예외를 밖으로
  던지지 않고 ``None`` 반환(호출자가 gap 으로 기록). 앱은 절대 죽지 않는다.
- **lazy import**: yfinance 등 무거운 선택적 의존성은 함수 안에서 import.
- **injectable fetch**: 모든 HTTP 클라이언트는 ``fetch`` 콜러블을 주입받아 테스트에서
  네트워크 없이 모킹 가능. 기본값은 httpx GET.
- **smart retry**: 일시 오류는 tenacity 지수 백오프로 소수 횟수 재시도.
- 숫자는 오직 소스 응답에서만 추출(여기서 값을 지어내지 않는다).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.core.exceptions import DataSourceError
from app.core.logging import get_logger
from app.core.reliability import with_retry
from app.data.normalize import build_metric, build_source

logger = get_logger(__name__)

# fetch(url, params=None, headers=None, timeout=...) -> parsed JSON(dict/list)
FetchFn = Callable[..., Any]


def _default_fetch(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 10.0,
) -> Any:
    """기본 HTTP fetcher (httpx GET). httpx 는 런타임 의존성에 이미 존재.

    네트워크/HTTP 오류는 ``DataSourceError`` 로 변환 → tenacity 재시도 대상.
    """
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx 는 필수 의존성
        raise DataSourceError("HTTP 클라이언트 사용 불가", f"httpx import 실패: {exc}") from exc

    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - 모든 네트워크 오류를 재시도 대상으로
        raise DataSourceError("외부 데이터 소스 호출 실패", f"{url}: {exc}") from exc


@with_retry(max_attempts=3)
def _fetch_with_retry(fetch: FetchFn, url: str, **kwargs: Any) -> Any:
    """주입된 fetch 를 스마트 재시도로 감싼다(DataSourceError 만 재시도)."""
    return fetch(url, **kwargs)


def _safe_fetch(fetch: FetchFn, url: str, **kwargs: Any) -> Optional[Any]:
    """재시도까지 모두 실패하면 None 반환(예외 비전파)."""
    try:
        return _fetch_with_retry(fetch, url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        logger.warning("fetch 실패(gap 처리): %s (%s)", url, exc)
        return None


# ---------------------------------------------------------------------------
# FRED — 미국 거시 시계열 (FFR, US10Y, DXY 류). API 키 필요.
# ---------------------------------------------------------------------------
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fred_series(
    code: str,
    series_id: str,
    unit: str,
    *,
    api_key: str,
    fetch: FetchFn = _default_fetch,
) -> Optional[dict]:
    """FRED 관측치 시계열의 최신값을 Metric 으로 반환. 키 없으면 None(gap)."""
    if not api_key:
        logger.info("FRED 키 없음 → %s gap", code)
        return None

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }
    data = _safe_fetch(fetch, FRED_BASE, params=params)
    if not data:
        return None

    try:
        obs = data["observations"][0]
        raw = obs["value"]
        if raw in (".", "", None):  # FRED 결측 표기
            return None
        source = build_source(
            title=f"FRED {series_id}",
            url=f"https://fred.stlouisfed.org/series/{series_id}",
            ref=series_id,
            published_at=obs.get("date"),
        )
        return build_metric(code, float(raw), unit, source, observed_at=obs.get("date"))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("FRED 응답 파싱 실패 %s: %s", code, exc)
        return None


# ---------------------------------------------------------------------------
# ECOS — 한국은행 (KR 금리, USD/KRW). API 키 필요.
# ---------------------------------------------------------------------------
ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"


def ecos_latest(
    code: str,
    stat_code: str,
    item_code: str,
    unit: str,
    *,
    api_key: str,
    cycle: str = "M",
    fetch: FetchFn = _default_fetch,
) -> Optional[dict]:
    """ECOS 통계의 최신 1건을 Metric 으로 반환. 키 없으면 None(gap)."""
    if not api_key:
        logger.info("ECOS 키 없음 → %s gap", code)
        return None

    # ECOS REST 경로 파라미터: /키/json/kr/시작/끝/통계코드/주기/시작일/종료일/항목
    url = (
        f"{ECOS_BASE}/{api_key}/json/kr/1/1/"
        f"{stat_code}/{cycle}/2000/2100/{item_code}"
    )
    data = _safe_fetch(fetch, url)
    if not data:
        return None

    try:
        rows = data["StatisticSearch"]["row"]
        row = rows[-1]
        source = build_source(
            title=f"ECOS {stat_code}/{item_code}",
            url="https://ecos.bok.or.kr/",
            ref=f"{stat_code}:{item_code}",
            published_at=row.get("TIME"),
        )
        return build_metric(
            code, float(row["DATA_VALUE"]), unit, source, observed_at=row.get("TIME")
        )
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("ECOS 응답 파싱 실패 %s: %s", code, exc)
        return None


# ---------------------------------------------------------------------------
# FMP — 무료 티어 시세(주가/지수/코인). API 키 필요.
# ---------------------------------------------------------------------------
FMP_BASE = "https://financialmodelingprep.com/api/v3/quote"


def fmp_quote(
    code: str,
    symbol: str,
    unit: str,
    *,
    api_key: str,
    fetch: FetchFn = _default_fetch,
) -> Optional[dict]:
    """FMP 시세 최신 price 를 Metric 으로 반환. 키 없으면 None(gap)."""
    if not api_key:
        logger.info("FMP 키 없음 → %s gap", code)
        return None

    url = f"{FMP_BASE}/{symbol}"
    data = _safe_fetch(fetch, url, params={"apikey": api_key})
    if not data:
        return None

    try:
        row = data[0] if isinstance(data, list) else data
        price = row["price"]
        source = build_source(
            title=f"FMP {symbol}",
            url=f"https://financialmodelingprep.com/quote/{symbol}",
            ref=symbol,
            published_at=None,
        )
        return build_metric(code, float(price), unit, source)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("FMP 응답 파싱 실패 %s: %s", code, exc)
        return None


# ---------------------------------------------------------------------------
# yfinance — 키 불필요 폴백(지연 import, 네트워크 없으면 None).
# ---------------------------------------------------------------------------
def yfinance_quote(code: str, symbol: str, unit: str) -> Optional[dict]:
    """yfinance 최근 종가를 Metric 으로 반환. 미설치/오류 시 None(gap)."""
    try:
        import yfinance  # 지연 import: 하드 런타임 의존성 아님
    except ImportError:
        logger.info("yfinance 미설치 → %s gap", code)
        return None

    try:
        ticker = yfinance.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist is None or hist.empty:
            return None
        last = hist["Close"].dropna()
        if last.empty:
            return None
        value = float(last.iloc[-1])
        observed = str(last.index[-1].date())
        source = build_source(
            title=f"Yahoo Finance {symbol}",
            url=f"https://finance.yahoo.com/quote/{symbol}",
            ref=symbol,
            published_at=observed,
        )
        return build_metric(code, value, unit, source, observed_at=observed)
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        logger.warning("yfinance 실패(gap 처리) %s: %s", code, exc)
        return None


# ---------------------------------------------------------------------------
# CoinGecko — 키 불필요 코인 시세(코인은 섹터와 분리 표시).
# ---------------------------------------------------------------------------
COINGECKO_BASE = "https://api.coingecko.com/api/v3/simple/price"


def coingecko_price(
    code: str,
    coin_id: str,
    unit: str = "USD",
    *,
    vs_currency: str = "usd",
    fetch: FetchFn = _default_fetch,
) -> Optional[dict]:
    """CoinGecko 단순 시세를 Metric 으로 반환. 오류 시 None(gap)."""
    params = {"ids": coin_id, "vs_currencies": vs_currency}
    data = _safe_fetch(fetch, COINGECKO_BASE, params=params)
    if not data:
        return None

    try:
        price = data[coin_id][vs_currency]
        source = build_source(
            title=f"CoinGecko {coin_id}",
            url=f"https://www.coingecko.com/en/coins/{coin_id}",
            ref=coin_id,
            published_at=None,
        )
        return build_metric(code, float(price), unit, source)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("CoinGecko 응답 파싱 실패 %s: %s", code, exc)
        return None
