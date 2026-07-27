import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

MARKET = data.get("market", "US")  # "KR" 또는 "US" - data.json에서 라운드별로 전환

if MARKET == "KR":
    import re
    import requests
    from bs4 import BeautifulSoup

    TZ = ZoneInfo("Asia/Seoul")
    OPEN_HOUR,  OPEN_MIN  = 9, 0
    CLOSE_HOUR, CLOSE_MIN = 15, 30

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
else:
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("yfinance가 필요합니다. 설치: pip install yfinance")

    TZ = ZoneInfo("America/New_York")
    OPEN_HOUR,  OPEN_MIN  = 9, 30
    CLOSE_HOUR, CLOSE_MIN = 16, 0

now_tz = datetime.now(TZ)
today = now_tz.strftime("%Y-%m-%d")
today_naver = now_tz.strftime("%Y.%m.%d")  # 네이버 날짜 형식 (KR 전용)

MARKET_OPEN  = now_tz.replace(hour=OPEN_HOUR,  minute=OPEN_MIN,  second=0, microsecond=0)
MARKET_CLOSE = now_tz.replace(hour=CLOSE_HOUR, minute=CLOSE_MIN, second=0, microsecond=0)


def is_market_open() -> bool:
    """평일 장중 시간대(KR: 09:00~15:30 KST, US: 09:30~16:00 ET)이면 True"""
    if now_tz.weekday() >= 5:  # 토·일
        return False
    return MARKET_OPEN <= now_tz <= MARKET_CLOSE


def get_current_price_kr(code: str) -> int | None:
    """네이버 증권 main 페이지에서 현재가 크롤링 (장중 전용)"""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        price_tag = soup.select_one(
            "p.no_today em.no_up, p.no_today em.no_down, p.no_today em.no_same"
        )
        if price_tag:
            for text in price_tag.strings:
                clean = text.strip().replace(",", "")
                if clean.isdigit():
                    return int(clean)

        m = re.search(r'"now"\s*:\s*"?([0-9,]+)"?', resp.text)
        if m:
            return int(m.group(1).replace(",", ""))

    except Exception as e:
        print(f"  [오류] {code} 현재가 크롤링 실패: {e}")
    return None


def get_closing_price_kr(code: str) -> tuple:
    """네이버 증권 일별 시세에서 종가 크롤링 (장 마감 후 전용).
    오늘 종가가 있으면 오늘 종가, 없으면 가장 최근 거래일 종가 반환.
    반환값: (가격, 실제날짜) 또는 (None, None)
    """
    url = f"https://finance.naver.com/item/sise_day.naver?code={code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")

        date_pat = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
        first_valid = None

        for row in soup.select("table.type2 tr"):
            tds = row.find_all("td")
            if len(tds) < 2:
                continue

            date_text = tds[0].get_text(strip=True)
            if not date_pat.match(date_text):
                continue

            close_text = tds[1].get_text(strip=True).replace(",", "")
            if not close_text.isdigit():
                continue

            price = int(close_text)

            if first_valid is None:
                first_valid = (price, date_text)

            if date_text == today_naver:
                return price, date_text

        if first_valid:
            return first_valid

    except Exception as e:
        print(f"  [오류] {code} 종가 크롤링 실패: {e}")

    return None, None


def get_current_price_us(ticker: str) -> float | None:
    """장중 현재가 조회 (yfinance fast_info)"""
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.last_price
        if price is not None:
            return round(float(price), 2)
    except Exception as e:
        print(f"  [오류] {ticker} 현재가 조회 실패: {e}")
    return None


def get_closing_price_us(ticker: str) -> tuple:
    """장 마감 후 최신 종가 조회 (yfinance history).
    반환값: (가격, 날짜) 또는 (None, None)
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            price = round(float(hist["Close"].iloc[-1]), 2)
            date  = hist.index[-1].strftime("%Y-%m-%d")
            return price, date
    except Exception as e:
        print(f"  [오류] {ticker} 종가 조회 실패: {e}")
    return None, None


def fetch_price(code: str) -> tuple:
    """장중이면 현재가, 장 마감 후면 종가를 반환.
    반환값: (가격, 레이블) 또는 (None, None)
    """
    if MARKET == "KR":
        get_current, get_closing, today_label = get_current_price_kr, get_closing_price_kr, today_naver
    else:
        get_current, get_closing, today_label = get_current_price_us, get_closing_price_us, today

    if is_market_open():
        price = get_current(code)
        return (price, "현재가") if price is not None else (None, None)
    else:
        price, trade_date = get_closing(code)
        if price is None:
            return None, None
        label = "종가" if trade_date == today_label else f"종가(기준:{trade_date})"
        return price, label


def format_price(price: float) -> str:
    return f"{price:,.0f}원" if MARKET == "KR" else f"${price:.2f}"


def main():
    market_name = "한국" if MARKET == "KR" else "미국"
    tz_name = "KST" if MARKET == "KR" else "ET"
    mode = "장중 (현재가)" if is_market_open() else "장 마감 후 (종가)"
    print(f"\n[{today} {tz_name}] {market_name}주식 업데이트 시작 - {mode}")
    print("-" * 40)

    if today not in data["prices"]:
        data["prices"][today] = {}

    for pid, info in data["participants"].items():
        code = info["code"]
        price, label = fetch_price(code)
        if price is not None:
            data["prices"][today][pid] = price
            avg = info["avg_price"]
            pct = (price - avg) / avg * 100
            sign = "+" if pct >= 0 else ""
            print(f"  {pid} ({info['stock']}): {format_price(price)} [{label}]  수익률 {sign}{pct:.2f}%")
        else:
            print(f"  {pid} ({info['stock']}): 가져오기 실패")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("-" * 40)
    print("data.json 업데이트 완료\n")


if __name__ == "__main__":
    main()
