import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone, timedelta

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST).strftime("%Y-%m-%d")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
JS_FILE   = os.path.join(BASE_DIR, "data.js")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_current_price(code: str) -> int | None:
    """네이버 증권에서 현재가 크롤링"""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 현재가: <p class="no_today"> 안의 em 태그에서 숫자 텍스트만 추출
        price_tag = soup.select_one("p.no_today em.no_up, p.no_today em.no_down, p.no_today em.no_same")
        if price_tag:
            # .strings 이터레이터로 개별 텍스트 노드 순회 → 첫 번째 숫자 토큰 사용
            for text in price_tag.strings:
                clean = text.strip().replace(",", "")
                if clean.isdigit():
                    return int(clean)

        # 대체: 페이지 전체에서 정규식으로 현재가 추출
        import re
        m = re.search(r'var\s+naver_stock_speed2_time[^;]+현재가["\s:]+([0-9,]+)', resp.text)
        if not m:
            m = re.search(r'"now"\s*:\s*"?([0-9,]+)"?', resp.text)
        if m:
            return int(m.group(1).replace(",", ""))

    except Exception as e:
        print(f"  [오류] {code} 크롤링 실패: {e}")
    return None


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n[{today}] 종가 업데이트 시작")
    print("-" * 40)

    if today not in data["prices"]:
        data["prices"][today] = {}

    for pid, info in data["participants"].items():
        code = info["code"]
        price = get_current_price(code)
        if price is not None:
            data["prices"][today][pid] = price
            avg = info["avg_price"]
            pct = (price - avg) / avg * 100
            sign = "+" if pct >= 0 else ""
            print(f"  {pid} ({info['stock']}): {price:,}원  수익률 {sign}{pct:.2f}%")
        else:
            print(f"  {pid} ({info['stock']}): 가져오기 실패")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # data.js 생성 (file:// 로컬 열람용 — script 태그는 CORS 제한 없음)
    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("const STOCK_DATA = ")
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print("-" * 40)
    print("data.json / data.js 업데이트 완료\n")


if __name__ == "__main__":
    main()
