import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import time
from flask import Flask, Response

app = Flask(__name__)

# ============================================================
# ⚙️ الإعدادات - عدّل هنا فقط
# ============================================================

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%22fc+bayern%22&hl=de&gl=DE&ceid=DE:de",
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

# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def resolve_google_news_url(url: str) -> str:
    """يتبع الـ redirect من Google News للوصول للرابط الحقيقي"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except:
        return url


def fetch_article_text(url: str) -> str:
    """يفتح الرابط ويرجع النص الكامل"""
    try:
        # تتبع الـ redirect أولاً
        real_url = resolve_google_news_url(url)
        print(f"    رابط حقيقي: {real_url[:80]}...")

        r = requests.get(real_url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        print(f"    نص المقال: {len(text)} حرف")
        return text.lower()
    except Exception as e:
        print(f"    فشل fetch: {e}")
        return ""


def matches_keywords(text: str) -> tuple:
    text_lower = text.lower()
    for kw in FILTER_KEYWORDS:
        if kw.lower() in text_lower:
            return True, kw
    return False, ""


def build_rss_xml(articles: list) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Bayern Filtered Feed"
    ET.SubElement(channel, "link").text = "https://news.google.com"
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

    for feed_url in RSS_FEEDS:
        print(f"قراءة RSS: {feed_url[:70]}...")
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            print("لا مقالات في الـ feed!")
            continue

        entries = feed.entries[:MAX_ARTICLES_TO_CHECK]
        print(f"عدد المقالات: {len(entries)}")

        for i, entry in enumerate(entries):
            title = entry.get("title", "")
            link = entry.get("link", "")

            if link in seen_links:
                continue

            print(f"[{i+1}] {title[:70]}...")

            # تحقق من العنوان أولاً
            title_match, kw = matches_keywords(title)
            if title_match:
                print(f"  ✅ تطابق في العنوان: '{kw}'")
                all_matched.append({
                    "title": title, "link": link,
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
                seen_links.add(link)
                continue

            # افتح المقال
            article_text = fetch_article_text(link)
            if article_text:
                content_match, kw = matches_keywords(article_text)
                if content_match:
                    print(f"  ✅ تطابق في المحتوى: '{kw}'")
                    all_matched.append({
                        "title": title, "link": link,
                        "summary": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                    })
                    seen_links.add(link)
                else:
                    print(f"  ❌ لا تطابق")
            else:
                print(f"  ⚠️ فشل قراءة المقال")

            time.sleep(0.3)

    print(f"النتيجة النهائية: {len(all_matched)} مقال مطابق")
    return build_rss_xml(all_matched)


@app.route("/feed")
def serve_feed():
    xml = process_all_feeds()
    return Response(xml, mimetype="application/rss+xml; charset=utf-8")


@app.route("/")
def index():
    return '✅ RSS Filter is running. Feed available at <a href="/feed">/feed</a>'


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
