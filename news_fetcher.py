"""
NewsAPI fetcher — pulls articles for each client based on their config.
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict
import time


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
        """Fetch up to 100 articles for a client from the past 7 days."""
        days_back = config.get("default_settings", {}).get("days_back", 7)
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
            # Blend AU + global — no domain restriction, but AU sources naturally appear
            pass
        # global: no domain filter

        # Apply client-level exclusions
        if client.get("exclude_sources"):
            params["excludeDomains"] = ",".join(client["exclude_sources"])

        response = requests.get(self.BASE_URL, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])
            # Remove deleted/removed articles
            articles = [
                a for a in articles
                if a.get("title") and "[Removed]" not in a.get("title", "")
                and a.get("url") and a.get("url") != "https://removed.com"
            ]
            return articles

        elif response.status_code == 429:
            raise Exception("NewsAPI rate limit reached. Try again shortly.")
        else:
            try:
                err = response.json().get("message", f"HTTP {response.status_code}")
            except Exception:
                err = f"HTTP {response.status_code}"
            raise Exception(f"NewsAPI error: {err}")

    def fetch_with_fallback(self, client: Dict, config: Dict) -> List[Dict]:
        """
        Try primary keyword query; if zero results, fall back to a broader query
        using only the first two keywords without domain restriction.
        """
        articles = self.fetch_articles(client, config)
        if articles:
            return articles

        # Fallback: broader query
        fallback_client = client.copy()
        fallback_client["keywords"] = client["keywords"][:2]
        fallback_client["scope"] = "global"
        fallback_client["exclude_sources"] = []
        time.sleep(0.5)
        return self.fetch_articles(fallback_client, config)
