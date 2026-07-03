"""
OPENTIX 全新登場 → RSS feed 產生器
使用官方 API 分頁抓取節目，產出 docs/feed.xml
每週一、週四執行，只輸出新增節目
"""

import os
import sys
import json
import time
import hashlib
import logging
import html
import requests
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOPIC_ID = "1378018195831590913"
API_BASE = f"https://csm.api.opentix.life/topics/{TOPIC_ID}"
TOPIC_URL = f"https://www.opentix.life/topic/{TOPIC_ID}"
EVENT_URL_BASE = "https://www.opentix.life/event"

OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "feed.xml")
SEEN_IDS_FILE = os.path.join(OUTPUT_DIR, "seen_ids.json")

ROW_COUNT = 30
DELAY = 0.5

# 連續碰到幾個已知 ID 才提早停止翻頁
EARLY_STOP_THRESHOLD = 10

TW = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9",
}


def load_seen_ids() -> set[str]:
    if not os.path.exists(SEEN_IDS_FILE):
        log.info("seen_ids.json 不存在，視為第一次執行")
        return set()
    with open(SEEN_IDS_FILE, encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_ids(ids: set[str]) -> None:
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)
    log.info(f"已更新 seen_ids.json，共 {len(ids)} 筆")


def ts_to_str(ts: int) -> str:
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts, tz=TW)
    return dt.strftime("%Y/%m/%d %H:%M")


def fetch_all_events(seen_ids: set[str]) -> tuple[list[dict], bool]:
    """
    翻頁抓取節目。
    API 為新的在前，碰到連續 EARLY_STOP_THRESHOLD 個已知 ID 時提早停止。

    回傳 (all_events, success)：
    - success=True  時 all_events 是完整、可信賴的抓取結果，呼叫端可以用來更新
      feed.xml 與 seen_ids.json。
    - success=False 時代表抓取中途出錯，all_events 只包含錯誤發生前抓到的部分，
      不完整。呼叫端絕對不能用這份不完整的資料更新 seen_ids.json（否則會讓
      未抓到的新節目被誤判為「已知」，之後永遠不會被推送）。正確做法是整批捨棄，
      等下次排程重跑。
    """
    all_events = []
    page = 1
    consecutive_seen = 0  # 連續已知 ID 計數

    while True:
        url = f"{API_BASE}?page={page}&rowCount={ROW_COUNT}&version=1"
        log.info(f"抓取第 {page} 頁...")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error(f"網路請求失敗（第 {page} 頁），可能是暫時性問題，等下次重跑：{e}")
            return all_events, False

        try:
            data = resp.json()
            result = data["result"]
            items = result.get("contentData", [])
        except (KeyError, ValueError) as e:
            log.error(f"回應格式異常（第 {page} 頁），API 可能已改版，需要檢查程式：{e}")
            return all_events, False

        if not items:
            log.info("沒有更多資料，結束翻頁")
            break

        for item in items:
            event_id = item.get("id")
            if event_id in seen_ids:
                consecutive_seen += 1
            else:
                consecutive_seen = 0  # 碰到新的就重置

            all_events.append(item)

            if consecutive_seen >= EARLY_STOP_THRESHOLD:
                log.info(
                    f"連續 {EARLY_STOP_THRESHOLD} 個已知節目，提早停止翻頁"
                    f"（第 {page} 頁、目前累計 {len(all_events)} 筆）"
                )
                return all_events, True

        log.info(f"  第 {page} 頁取得 {len(items)} 筆，累計 {len(all_events)} 筆")

        next_page = result.get("contentNextPage")
        if not next_page:
            break

        page = next_page
        time.sleep(DELAY)

    return all_events, True


def format_event_description(e: dict) -> str:
    lines = []

    if e.get("displayCategory"):
        lines.append(f"🎭 類別：{e['displayCategory']}")

    events = e.get("events", [])
    if events:
        first_start = ts_to_str(events[0].get("startDateTime", 0))
        last_end = ts_to_str(events[-1].get("endDateTime", 0))
        if len(events) == 1:
            lines.append(f"📅 演出時間：{first_start}")
        else:
            lines.append(f"📅 演出期間：{first_start} ～ {last_end}（共 {len(events)} 場）")

    cities = e.get("cities", [])
    if cities:
        lines.append(f"📍 城市：{'、'.join(cities)}")

    min_p = e.get("minPrice")
    max_p = e.get("maxPrice")
    if min_p is not None and max_p is not None:
        if min_p == max_p:
            lines.append(f"🎟 票價：${min_p:,}")
        else:
            lines.append(f"🎟 票價：${min_p:,} - ${max_p:,}")

    age = e.get("ageRestriction")
    if age is None:
        age = e.get("filmRating")
    if age is not None and age != "":
        lines.append(f"👶 限制：{age}")

    return "\n".join(lines)


def build_rss(events: list[dict], now_str: str) -> str:
    rss = Element("rss", version="2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:media", "http://search.yahoo.com/mrss/")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "OPENTIX 全新登場"
    SubElement(channel, "link").text = TOPIC_URL
    SubElement(channel, "description").text = "OPENTIX 兩廳院文化生活 每週新上架節目"
    SubElement(channel, "language").text = "zh-TW"

    SubElement(channel, "lastBuildDate").text = now_str

    for e in events:
        item = SubElement(channel, "item")

        title = e.get("name") or "（無標題）"
        event_id = e.get("id", "")
        event_url = f"{EVENT_URL_BASE}/{event_id}"
        image_url = e.get("imageUrl", "")
        image_alt = e.get("imageDescription", title)

        SubElement(item, "title").text = title
        SubElement(item, "link").text = event_url

        guid = SubElement(item, "guid", isPermaLink="false")
        guid.text = hashlib.md5(event_id.encode()).hexdigest()

        SubElement(item, "pubDate").text = now_str

        desc_text = format_event_description(e)
        SubElement(item, "description").text = desc_text

        if image_url:
            safe_image_url = html.escape(image_url, quote=True)
            safe_image_alt = html.escape(image_alt, quote=True)
            safe_event_url = html.escape(event_url, quote=True)
            safe_desc_text = html.escape(desc_text)
            html_content = (
                f'<img src="{safe_image_url}" alt="{safe_image_alt}" style="max-width:100%"/>'
                f"<br/><pre>{safe_desc_text}</pre>"
                f'<br/><a href="{safe_event_url}">→ 查看詳情與購票</a>'
            )
            SubElement(item, "content:encoded").text = html_content
            SubElement(item, "media:content", url=image_url, medium="image")

    raw = tostring(rss, encoding="unicode")
    dom = minidom.parseString(raw)
    return dom.toprettyxml(indent="  ", encoding=None)


def main():
    log.info("開始抓取 OPENTIX 全新登場（API 模式）...")

    seen_ids = load_seen_ids()
    log.info(f"上次已推送 {len(seen_ids)} 筆")

    all_events, success = fetch_all_events(seen_ids)

    if not success:
        log.error("抓取中途發生錯誤，本次不更新 feed 與 seen_ids，等下次重跑")
        sys.exit(1)

    if not all_events:
        log.error("沒有抓到任何節目，終止")
        sys.exit(1)

    # 過濾出新節目
    new_events = [e for e in all_events if e.get("id") not in seen_ids]
    log.info(f"本次新增：{len(new_events)} 筆（共抓到 {len(all_events)} 筆）")

    all_ids = seen_ids | {e["id"] for e in all_events if e.get("id")}

    if not new_events:
        log.info("沒有新節目，不更新 feed")
        save_seen_ids(all_ids)
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    now_str = datetime.now(TW).strftime("%a, %d %b %Y %H:%M:%S %z")
    xml_str = build_rss(new_events, now_str)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_str)
    log.info("已輸出 feed.xml")

    save_seen_ids(all_ids)


if __name__ == "__main__":
    main()