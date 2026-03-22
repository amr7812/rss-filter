import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import os
import time
from urllib.parse import urlparse, parse_qs, unquote

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
    "-Informationen",
]

MAX_ARTICLES_TO_CHECK = 30
OUTPUT_FILE = "filtered_feed.xml"

# ============================================================


def extract_real_url(url: str) -> str:
    """يستخرج الرابط الحقيقي من رابط Google (News أو Alerts)"""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        # Google Alerts: google.com/url?rct=j&sa=t&url=https://...
        if "url" in params:
            return unquote(params["url"][0])
    except:
        pass
    # Google News RSS articles لا يمكن فكها بدون redirect
    # نرجع الرابط كما هو
    return url


def fetch_article_text(url: str, timeout: int = 10) -> tuple:
    """يفتح الرابط ويرجع (النص الكامل, الرابط الحقيقي)"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        real_url = response.url  # الرابط الحقيقي بعد الـ redirect
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True).lower(), real_url
    except Exception as e:
        print(f"  ⚠️  فشل فتح الرابط: {url[:60]}... ({e})")
        return "", url


def matches_keywords(text: str, keywords: list) -> tuple:
    """يتحقق إذا كان النص يحتوي على أي كلمة من القائمة (OR)"""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True, kw
    return False, ""


def build_rss_feed(articles: list, source_feed) -> str:
    """يبني ملف RSS XML من المقالات المفلترة"""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"Filtered: {source_feed.feed.get('title', 'RSS Feed')}"
    ET.SubElement(channel, "link").text = source_feed.feed.get("link", "")
    ET.SubElement(channel, "description").text = f"Filtered by keywords: {', '.join(FILTER_KEYWORDS)}"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["link"]  # ← رابط حقيقي الآن
        ET.SubElement(item, "description").text = article.get("summary", "")
        ET.SubElement(item, "pubDate").text = article.get("published", "")
        ET.SubElement(item, "guid").text = article["link"]
    return ET.tostring(rss, encoding="unicode", xml_declaration=True)


def process_feed(feed_url: str, seen_links: set) -> tuple:
    print(f"\n🔍 جاري قراءة: {feed_url[:70]}...")
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        print("  ❌ لم يتم العثور على مقالات")
        return [], feed

    entries = feed.entries[:MAX_ARTICLES_TO_CHECK]
    print(f"  📰 عدد المقالات للفحص: {len(entries)}")

    matched = []

    for i, entry in enumerate(entries):
        title = entry.get("title", "")
        link = entry.get("link", "")
        real_link = extract_real_url(link)  # ← استخرج الرابط الحقيقي

        if link in seen_links:
            print(f"  [{i+1}] ⏭️  مكرر، تم تخطيه")
            continue

        print(f"  [{i+1}/{len(entries)}] {title[:60]}...")

        # أولاً: تحقق من العنوان
        title_match, kw = matches_keywords(title, FILTER_KEYWORDS)
        if title_match:
            print(f"    ✅ تطابق في العنوان: '{kw}'")
            matched.append({
                "title": title,
                "link": real_link,  # ← رابط حقيقي
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
            })
            seen_links.add(link)
            continue

        # ثانياً: افتح المقال وتحقق من المحتوى
        article_text, fetched_url = fetch_article_text(real_link)
        if article_text:
            content_match, kw = matches_keywords(article_text, FILTER_KEYWORDS)
            if content_match:
                print(f"    ✅ تطابق في المحتوى: '{kw}'")
                matched.append({
                    "title": title,
                    "link": fetched_url,  # ← الرابط الحقيقي بعد الـ redirect
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
                seen_links.add(link)
            else:
                print(f"    ❌ لا تطابق")

        time.sleep(0.5)

    return matched, feed


def main():
    print(f"🔑 الكلمات المطلوبة (OR): {FILTER_KEYWORDS}")
    print(f"📡 عدد الـ Feeds: {len(RSS_FEEDS)}")

    all_matched = []
    seen_links = set()
    first_feed = None

    for feed_url in RSS_FEEDS:
        matched, feed = process_feed(feed_url, seen_links)
        all_matched.extend(matched)
        if first_feed is None:
            first_feed = feed

    print(f"\n📊 النتيجة الإجمالية: {len(all_matched)} مقال مطابق")

    xml_content = build_rss_feed(all_matched, first_feed)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_content)

    if all_matched:
        print(f"✅ تم حفظ الـ feed في: {OUTPUT_FILE}")
    else:
        print("⚠️  لم يتم العثور على مقالات مطابقة، تم حفظ feed فارغ")


if __name__ == "__main__":
    main()
