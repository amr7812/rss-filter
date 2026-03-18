import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import time
import threading
from flask import Flask, Response

app = Flask(__name__)

# ============================================================
# ⚙️ الإعدادات - عدّل هنا فقط
# ============================================================

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%22fc+bayern%22&hl=de&gl=DE&ceid=DE:de",
    # أضف روابط إضافية هنا
]

FILTER_KEYWORDS = [
    "EXKLUSIV",
    "Interview",
    "Fakt ist",
    "Fest steht",
    "weiß",
    "Informationen",
    "klärt",
]

MAX_ARTICLES_TO_CHECK = 30
UPDATE_INTERVAL = 300  # كل 5 دقائق (بالثواني)

# ============================================================

# cache يحفظ آخر نتيجة في الذاكرة
cached_feed_xml = ""
cache_lock = threading.Lock()


def fetch_article_text(url: str, timeout: int = 10) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; RSSFilter/1.0)"}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True).lower()
    except Exception as e:
        print(f"  ⚠️  فشل فتح الرابط: {url[:60]}... ({e})")
        return ""


def matches_keywords(text: str, keywords: list) -> tuple:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True, kw
    return False, ""


def build_rss_xml(articles: list, source_feed) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = f"Filtered: {source_feed.feed.get('title', 'RSS Feed')}"
    ET.SubElement(channel, "link").text = source_feed.feed.get("link", "")
    ET.SubElement(channel, "description").text = f"Filtered by: {', '.join(FILTER_KEYWORDS)}"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["link"]
        ET.SubElement(item, "description").text = article.get("summary", "")
        ET.SubElement(item, "pubDate").text = article.get("published", "")
        ET.SubElement(item, "guid").text = article["link"]

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)


def process_all_feeds() -> str:
    all_matched = []
    seen_links = set()
    first_feed = None

    for feed_url in RSS_FEEDS:
        print(f"\n🔍 جاري قراءة: {feed_url[:70]}...")
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            print("  ❌ لا مقالات")
            continue

        if first_feed is None:
            first_feed = feed

        entries = feed.entries[:MAX_ARTICLES_TO_CHECK]
        print(f"  📰 عدد المقالات: {len(entries)}")

        for i, entry in enumerate(entries):
            title = entry.get("title", "")
            link = entry.get("link", "")

            if link in seen_links:
                continue

            print(f"  [{i+1}] {title[:60]}...")

            # تحقق من العنوان أولاً
            title_match, kw = matches_keywords(title, FILTER_KEYWORDS)
            if title_match:
                print(f"    ✅ عنوان: '{kw}'")
                all_matched.append({
                    "title": title, "link": link,
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
                seen_links.add(link)
                continue

            # تحقق من المحتوى
            article_text = fetch_article_text(link)
            if article_text:
                content_match, kw = matches_keywords(article_text, FILTER_KEYWORDS)
                if content_match:
                    print(f"    ✅ محتوى: '{kw}'")
                    all_matched.append({
                        "title": title, "link": link,
                        "summary": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                    })
                    seen_links.add(link)
                else:
                    print(f"    ❌ لا تطابق")

            time.sleep(0.5)

    print(f"\n📊 النتيجة: {len(all_matched)} مقال مطابق")
    return build_rss_xml(all_matched, first_feed or feedparser.parse(""))


def background_updater():
    """يعمل في الخلفية ويحدث الـ cache كل 5 دقائق"""
    global cached_feed_xml
    while True:
        print("\n🔄 جاري تحديث الـ feed...")
        try:
            xml = process_all_feeds()
            with cache_lock:
                cached_feed_xml = xml
            print("✅ تم تحديث الـ cache")
        except Exception as e:
            print(f"❌ خطأ: {e}")
        time.sleep(UPDATE_INTERVAL)


# ============================================================
# Routes
# ============================================================

@app.route("/feed")
def serve_feed():
    """الرابط الرئيسي للـ RSS feed"""
    with cache_lock:
        xml = cached_feed_xml

    if not xml:
        return Response("Feed is loading, try again in a minute.", status=503)

    return Response(xml, mimetype="application/rss+xml; charset=utf-8")


@app.route("/")
def index():
    return "✅ RSS Filter is running. Feed available at <a href='/feed'>/feed</a>"


# ============================================================
# Start
# ============================================================

# شغّل الـ updater في background thread
updater_thread = threading.Thread(target=background_updater, daemon=True)
updater_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
