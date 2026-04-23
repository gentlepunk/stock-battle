import re
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone, timedelta

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(KST)
today = now_kst.strftime("%Y-%m-%d")
today_naver = now_kst.strftime("%Y.%m.%d")  # 네이버 날짜 형식

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MARKET_OPEN  = now_kst.replace(hour=9,  minute=0,  second=0, microsecond=0)
MARKET_CLOSE = now_kst.replace(hour=15, minute=30, second=0, microsecond=0)


def is_market_open() -> bool:
    """평일 09:00~15:30 KST 사이면 True"""
    if now_kst.weekday() >= 5:  # 토·일
        return False
    return MARKET_OPEN <= now_kst <= MARKET_CLOSE


def get_current_price(code: str) -> int | None:
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


def get_closing_price(code: str) -> tuple:
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


def fetch_price(code: str) -> tuple:
    """장중이면 현재가, 장 마감 후면 종가를 반환.
    반환값: (가격, 레이블) 또는 (None, None)
    """
    if is_market_open():
        price = get_current_price(code)
        return (price, "현재가") if price is not None else (None, None)
    else:
        price, trade_date = get_closing_price(code)
        if price is None:
            return None, None
        label = "종가" if trade_date == today_naver else f"종가(기준:{trade_date})"
        return price, label


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    mode = "장중 (현재가)" if is_market_open() else "장 마감 후 (종가)"
    print(f"\n[{today}] 업데이트 시작 - {mode}")
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
            print(f"  {pid} ({info['stock']}): {price:,}원 [{label}]  수익률 {sign}{pct:.2f}%")
        else:
            print(f"  {pid} ({info['stock']}): 가져오기 실패")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("-" * 40)
    print("data.json 업데이트 완료\n")


if __name__ == "__main__":
    main()
