"""
Claude AI processor — scores relevance, summarises articles, and generates
WIP meeting angles for each client.
"""

import anthropic
import json
import re
from datetime import datetime
from typing import List, Dict


class AIProcessor:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def process_articles(self, articles: List[Dict], client: Dict) -> List[Dict]:
        """Score, summarise, and generate meeting angles for all articles."""
        if not articles:
            return []

        batch_size = 15
        all_processed = []

        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            try:
                processed = self._process_batch(batch, client)
                all_processed.extend(processed)
            except Exception as e:
                print(f"  [AI] Batch {i//batch_size + 1} failed: {e}")

        all_processed.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return all_processed[:40]

    def _process_batch(self, articles: List[Dict], client: Dict) -> List[Dict]:
        """Send a batch of articles to Claude and parse the structured response."""
        articles_block = ""
        for i, a in enumerate(articles):
            title = a.get("title", "No title")
            source = a.get("source", {}).get("name", "Unknown")
            desc = (a.get("description") or "")[:250]
            date = (a.get("publishedAt") or "")[:10]
            articles_block += f"\n[{i+1}] {title}\nSource: {source} | {date}\n{desc}\n"

        exclude_note = ""
        if client.get("exclude_topics"):
            exclude_note = f"\nIgnore articles primarily about: {', '.join(client['exclude_topics'])}"

        relevance_note = ""
        if client.get("relevance_context"):
            relevance_note = f"\nSCORING GUIDANCE: {client['relevance_context']}"

        prompt = f"""You are a senior PR strategist at AndIron Group, an Australian marketing and communications agency.

CLIENT: {client['name']}
INDUSTRY: {client['industry']}
ABOUT: {client.get('description', '')}
TRACK: {', '.join((client.get('topics') or client.get('keywords', []))[:15])}{exclude_note}{relevance_note}

For each article below, assess relevance to this client and, for relevant ones, provide:
- "index": article number (integer, 1-based)
- "relevance_score": 1–10 (how relevant to the client's business or industry)
- "summary": One sharp sentence summarising the article
- "meeting_angle": A specific, actionable PR/comms angle for this client's weekly WIP meeting — e.g. "Opportunity to position {client['name']} as expert source on X", "Proactively brief {client['name']} on reputational risk from Y", "Pitch {client['name']} response to Z to [outlet type]", "Use to inform client messaging around X"

Only include articles with relevance_score ≥ 5.
Return ONLY a valid JSON array — no explanation, no markdown fences.

ARTICLES:
{articles_block}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=3500,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        results = self._parse_json(raw)
        if results is None:
            return []

        processed = []
        for result in results:
            idx = result.get("index", 0) - 1
            if not (0 <= idx < len(articles)):
                continue
            score = result.get("relevance_score", 0)
            if score < 5:
                continue
            article = articles[idx].copy()
            article["relevance_score"] = score
            article["summary"] = result.get("summary", "")
            article["meeting_angle"] = result.get("meeting_angle", "")
            article["formatted_date"] = self._fmt_date(article.get("publishedAt", ""))
            processed.append(article)

        return processed

    def _parse_json(self, text: str):
        """Robustly extract a JSON array from Claude's response."""
        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?", "", text).strip()
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None

    def _fmt_date(self, iso: str) -> str:
        """Format ISO date string to '5 April 2026'."""
        if not iso:
            return ""
        try:
            dt = datetime.strptime(iso[:10], "%Y-%m-%d")
            return f"{dt.day} {dt.strftime('%B %Y')}"
        except ValueError:
            return iso[:10]
