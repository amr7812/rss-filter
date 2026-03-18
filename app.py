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

# ============================================================


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
        print(f"  فشل: {url[:60]}... ({e})")
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
        print(f"قراءة: {feed_url[:70]}...")
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            continue

        entries = feed.entries[:MAX_ARTICLES_TO_CHECK]

        for i, entry in enumerate(entries):
            title = entry.get("title", "")
            link = entry.get("link", "")

            if link in seen_links:
                continue

            title_match, kw = matches_keywords(title)
            if title_match:
                all_matched.append({
                    "title": title, "link": link,
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
                seen_links.add(link)
                continue

            article_text = fetch_article_text(link)
            if article_text:
                content_match, kw = matches_keywords(article_text)
                if content_match:
                    all_matched.append({
                        "title": title, "link": link,
                        "summary": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                    })
                    seen_links.add(link)

            time.sleep(0.3)

    print(f"النتيجة: {len(all_matched)} مقال")
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
