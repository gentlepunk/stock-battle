import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("yfinance가 필요합니다. 설치: pip install yfinance")

# 미국 동부 시간 (EDT/EST DST 자동 처리)
ET = ZoneInfo("America/New_York")
now_et = datetime.now(ET)
today = now_et.strftime("%Y-%m-%d")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")

# 미국 주식시장: 평일 09:30~16:00 ET
MARKET_OPEN  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
MARKET_CLOSE = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)


def is_market_open() -> bool:
    """평일 09:30~16:00 ET이면 True"""
    if now_et.weekday() >= 5:  # 토·일
        return False
    return MARKET_OPEN <= now_et <= MARKET_CLOSE


def get_current_price(ticker: str) -> float | None:
    """장중 현재가 조회 (yfinance fast_info)"""
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.last_price
        if price is not None:
            return round(float(price), 2)
    except Exception as e:
        print(f"  [오류] {ticker} 현재가 조회 실패: {e}")
    return None


def get_closing_price(ticker: str) -> tuple:
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


def fetch_price(ticker: str) -> tuple:
    """장중이면 현재가, 장 마감 후면 종가를 반환.
    반환값: (가격, 레이블) 또는 (None, None)
    """
    if is_market_open():
        price = get_current_price(ticker)
        return (price, "현재가") if price is not None else (None, None)
    else:
        price, trade_date = get_closing_price(ticker)
        if price is None:
            return None, None
        label = "종가" if trade_date == today else f"종가(기준:{trade_date})"
        return price, label


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    mode = "장중 (현재가)" if is_market_open() else "장 마감 후 (종가)"
    print(f"\n[{today} ET] 업데이트 시작 - {mode}")
    print("-" * 40)

    if today not in data["prices"]:
        data["prices"][today] = {}

    for pid, info in data["participants"].items():
        ticker = info["code"]
        price, label = fetch_price(ticker)
        if price is not None:
            data["prices"][today][pid] = price
            avg = info["avg_price"]
            pct = (price - avg) / avg * 100
            sign = "+" if pct >= 0 else ""
            print(f"  {pid} ({info['stock']}): ${price:.2f} [{label}]  수익률 {sign}{pct:.2f}%")
        else:
            print(f"  {pid} ({info['stock']}): 가져오기 실패")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("-" * 40)
    print("data.json 업데이트 완료\n")


if __name__ == "__main__":
    main()
