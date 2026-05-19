"""
OPENTIX 全新登場 → RSS feed 產生器
使用官方 API 分頁抓取節目，產出 docs/feed.xml
每週一、週四執行，只輸出新增節目
"""

import os
import json
import time
import hashlib
import logging
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
EARLY_STOP_THRESHOLD = 5

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
    回傳 (所有抓到的節目, 是否正常完成)。
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
            data = resp.json()
        except Exception as e:
            log.error(f"API 請求失敗（第 {page} 頁）：{e}")
            return all_events, False  # 中斷，標記為不完整

        result = data.get("result", {})
        items = result.get("contentData", [])

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
                log.info(f"連續 {EARLY_STOP_THRESHOLD} 個已知節目，提早停止翻頁")
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

    age = e.get("ageRestriction") or e.get("filmRating")
    if age:
        lines.append(f"👶 限制：{age}")

    return "\n".join(lines)


def build_rss(events: list[dict]) -> str:
    rss = Element("rss", version="2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:media", "http://search.yahoo.com/mrss/")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "OPENTIX 全新登場"
    SubElement(channel, "link").text = TOPIC_URL
    SubElement(channel, "description").text = "OPENTIX 兩廳院文化生活 每週新上架節目"
    SubElement(channel, "language").text = "zh-TW"

    now_str = datetime.now(TW).strftime("%a, %d %b %Y %H:%M:%S %z")
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

        events_list = e.get("events", [])
        first_ts = events_list[0].get("startDateTime") if events_list else None
        if first_ts:
            pub_dt = datetime.fromtimestamp(first_ts, tz=TW)
            pub_date = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        else:
            pub_date = now_str
        SubElement(item, "pubDate").text = pub_date

        desc_text = format_event_description(e)
        SubElement(item, "description").text = desc_text

        if image_url:
            html_content = (
                f'<img src="{image_url}" alt="{image_alt}" style="max-width:100%"/>'
                f"<br/><pre>{desc_text}</pre>"
                f'<br/><a href="{event_url}">→ 查看詳情與購票</a>'
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

    if not all_events:
        log.error("沒有抓到任何節目，終止")
        return

    if not success:
        log.warning("抓取中途發生錯誤，本次不更新 feed 與 seen_ids，等下次重跑")
        return

    # 過濾出新節目
    new_events = [e for e in all_events if e.get("id") not in seen_ids]
    log.info(f"本次新增：{len(new_events)} 筆（共抓到 {len(all_events)} 筆）")

    if not new_events:
        log.info("沒有新節目，不更新 feed")
        # 仍然更新 seen_ids，確保抓到的舊節目也被記錄
        all_ids = seen_ids | {e["id"] for e in all_events if e.get("id")}
        if all_ids != seen_ids:
            save_seen_ids(all_ids)
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    xml_str = build_rss(new_events)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_str)
    log.info("已輸出 feed.xml")

    all_ids = seen_ids | {e["id"] for e in all_events if e.get("id")}
    save_seen_ids(all_ids)


if __name__ == "__main__":
    main()