"""
NewsAPI + Google News RSS fetcher — pulls articles for each client based on their config.
"""

import difflib
import html
import re
import requests
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict


class NewsFetcher:
    BASE_URL = "https://newsapi.org/v2/everything"

    # High-quality Australian news domains
    AU_DOMAINS = (
        "abc.net.au,smh.com.au,afr.com,theaustralian.com.au,"
        "itnews.com.au,innovationaus.com,theage.com.au,news.com.au,"
        "businessinsider.com.au,crikey.com.au,zdnet.com.au,"
        "computerworld.com.au,reneweconomy.com.au,pv-magazine-australia.com,"
        "solarchoice.net.au,brisbanetimes.com.au,watoday.com.au,"
        "startup.daily,startupdaily.net,dynamicbusiness.com.au"
    )

    # International domains for global clients
    GLOBAL_DOMAINS = (
        "reuters.com,bloomberg.com,techcrunch.com,wired.com,"
        "theverge.com,arstechnica.com,zdnet.com,securityweek.com,"
        "darkreading.com,bleepingcomputer.com,helpnetsecurity.com,"
        "infosecurity-magazine.com,threatpost.com,theregister.com,"
        "renewableenergyworld.com,pv-tech.org,energymonitor.ai,"
        "fortune.com,wsj.com,ft.com,businesswire.com"
    )

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _build_query(self, keywords: List[str], max_kw: int = 6) -> str:
        """Build a NewsAPI boolean query from a keyword list."""
        parts = []
        for kw in keywords[:max_kw]:
            if " " in kw:
                parts.append(f'"{kw}"')
            else:
                parts.append(kw)
        return " OR ".join(parts)

    def fetch_articles(self, client: Dict, config: Dict) -> List[Dict]:
        """Fetch up to 100 articles for a client from NewsAPI."""
        days_back = client.get("days_back") or config.get("default_settings", {}).get("days_back", 7)
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = self._build_query(client["keywords"])
        scope = client.get("scope", "global")

        params = {
            "q": query,
            "from": from_date,
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": 100,
            "apiKey": self.api_key,
        }

        if scope == "australia":
            params["domains"] = self.AU_DOMAINS
        elif scope == "australia_global":
            pass
        # global: no domain filter

        if client.get("exclude_sources"):
            params["excludeDomains"] = ",".join(client["exclude_sources"])

        response = requests.get(self.BASE_URL, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            articles = [
                a for a in articles
                if a.get("title") and "[Removed]" not in a.get("title", "")
                and a.get("url") and a.get("url") != "https://removed.com"
            ]
            for a in articles:
                a["_source_api"] = "newsapi"
            return articles

        elif response.status_code == 429:
            raise Exception("NewsAPI rate limit reached. Try again shortly.")
        else:
            try:
                err = response.json().get("message", f"HTTP {response.status_code}")
            except Exception:
                err = f"HTTP {response.status_code}"
            raise Exception(f"NewsAPI error: {err}")

    def _fetch_google_rss(self, client: Dict) -> List[Dict]:
        """Fetch articles from Google News RSS."""
        keywords = client["keywords"][:5]
        query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)
        scope = client.get("scope", "global")

        if scope == "australia":
            params = {"q": query, "hl": "en-AU", "gl": "AU", "ceid": "AU:en"}
        else:
            params = {"q": query, "hl": "en", "gl": "US", "ceid": "US:en"}

        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()

            root = ET.fromstring(content)
            channel = root.find("channel")
            if channel is None:
                return []

            articles = []
            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                pub   = item.findtext("pubDate") or ""
                desc  = item.findtext("description") or ""
                src_el = item.find("source")

                if not title or not link:
                    continue
                if "[Removed]" in title:
                    continue

                # Source name from <source> element, or strip " - Source" suffix from title
                if src_el is not None and src_el.text:
                    source_name = src_el.text.strip()
                else:
                    parts = title.rsplit(" - ", 1)
                    if len(parts) == 2:
                        title, source_name = parts[0].strip(), parts[1].strip()
                    else:
                        source_name = "Google News"

                # Clean description
                desc = html.unescape(desc)
                desc = re.sub(r"<[^>]+>", "", desc).strip()

                # Parse date to ISO
                pub_iso = ""
                if pub:
                    try:
                        pub_iso = parsedate_to_datetime(pub).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        pass

                articles.append({
                    "source": {"id": None, "name": source_name},
                    "author": None,
                    "title": title,
                    "description": desc[:500],
                    "url": link,
                    "urlToImage": None,
                    "publishedAt": pub_iso,
                    "content": None,
                    "_source_api": "google_rss",
                })
            return articles

        except Exception as e:
            print(f"  [RSS] Google News RSS failed: {e}")
            return []

    def _deduplicate(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicates by exact URL or title similarity (>80%)."""
        seen_urls   = set()
        seen_titles = []
        unique = []
        for article in articles:
            url   = article.get("url", "")
            title = article.get("title", "").lower().strip()
            if url and url in seen_urls:
                continue
            is_dup = any(
                difflib.SequenceMatcher(None, title, t).ratio() > 0.80
                for t in seen_titles
            )
            if is_dup:
                continue
            if url:
                seen_urls.add(url)
            seen_titles.append(title)
            unique.append(article)
        return unique

    def fetch_with_fallback(self, client: Dict, config: Dict) -> List[Dict]:
        """
        Fetch from NewsAPI and Google News RSS, merge and deduplicate.
        Falls back to a broader NewsAPI query if both return nothing.
        """
        newsapi_articles = self.fetch_articles(client, config)   # tagged "newsapi"
        rss_articles     = self._fetch_google_rss(client)        # tagged "google_rss"

        merged = self._deduplicate(newsapi_articles + rss_articles)
        if merged:
            return merged

        # Fallback: broad query, no domain restriction
        fallback_client = client.copy()
        fallback_client["keywords"] = client["keywords"][:2]
        fallback_client["scope"] = "global"
        fallback_client["exclude_sources"] = []
        time.sleep(0.5)
        fallback = self.fetch_articles(fallback_client, config)
        return self._deduplicate(fallback)
