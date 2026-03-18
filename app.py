import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import time
import base64
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


def decode_google_news_url(url: str) -> str:
    """يفك تشفير رابط Google News ويرجع الرابط الحقيقي"""
    try:
        # الروابط من نوع /rss/articles/ تحتوي على الرابط الحقيقي مشفر في base64
        if "/rss/articles/" in url:
            # استخدم Google News API لفك الرابط
            article_id = url.split("/rss/articles/")[-1].split("?")[0]
            
            # طريقة 1: فك base64 مباشرة
            try:
                # أضف padding إذا ناقص
                padding = 4 - len(article_id) % 4
                if padding != 4:
                    article_id += "=" * padding
                decoded = base64.b64decode(article_id.replace("-", "+").replace("_", "/"))
                # البحث عن URL في الـ bytes
                text = decoded.decode("latin-1")
                import re
                urls = re.findall(r'https?://[^\s\x00-\x1f"<>]+', text)
                if urls:
                    # تصفية روابط google نفسها
                    real_urls = [u for u in urls if "google.com" not in u]
                    if real_urls:
                        print(f"    decoded URL: {real_urls[0][:80]}")
                        return real_urls[0]
            except Exception as e:
                print(f"    base64 decode failed: {e}")

        # طريقة 2: follow redirects مع session
        session = requests.Session()
        session.max_redirects = 10
        r = session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        final_url = r.url
        print(f"    redirect URL: {final_url[:80]}")
        
        if "google.com" not in final_url:
            return final_url
            
        # طريقة 3: ابحث عن canonical URL في الصفحة
        soup = BeautifulSoup(r.text, "html.parser")
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            href = canonical["href"]
            if "google.com" not in href:
                print(f"    canonical URL: {href[:80]}")
                return href
                
        return final_url
        
    except Exception as e:
        print(f"    decode error: {e}")
        return url


def fetch_article_text(url: str) -> str:
    """يفتح المقال الحقيقي ويرجع النص"""
    try:
        real_url = decode_google_news_url(url)
        
        if "google.com" in real_url:
            print(f"    ⚠️ لا يزال رابط Google، تخطي")
            return ""
        
        r = requests.get(real_url, headers=HEADERS, timeout=15)
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
            print("لا مقالات!")
            continue

        entries = feed.entries[:MAX_ARTICLES_TO_CHECK]
        print(f"عدد المقالات: {len(entries)}")

        for i, entry in enumerate(entries):
            title = entry.get("title", "")
            link = entry.get("link", "")

            if link in seen_links:
                continue

            print(f"[{i+1}] {title[:70]}...")

            title_match, kw = matches_keywords(title)
            if title_match:
                print(f"  ✅ عنوان: '{kw}'")
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
                    print(f"  ✅ محتوى: '{kw}'")
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

            time.sleep(0.5)

    print(f"النتيجة: {len(all_matched)} مقال مطابق")
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
