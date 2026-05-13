# research/aggregator.py

import asyncio
from datetime import datetime

from research.youtube import YouTubeScraper
from research.trends import GoogleTrendsScraper
from research.news import NewsScraper
from research.query_builder import QueryBuilder
from database.db import MatiksDatabase


class TrendAggregator:
    """
    Coordinates all scrapers and builds LLM briefings.
    
    Sources:
    - YouTube Data API (trending Shorts)
    - Google Trends (rising searches)  
    - Google News RSS (breaking news)
    
    Reddit removed: requires commercial approval from Reddit.
    Three sources is sufficient for strong trend signals.
    """

    def __init__(self, config: dict, db: MatiksDatabase):
        apis = config['apis']

        self.youtube = YouTubeScraper(apis['youtube_api_key'])
        self.trends = GoogleTrendsScraper()
        self.news = NewsScraper()
        self.query_builder = QueryBuilder()
        self.db = db

    async def research_niche(
        self,
        niche: str,
        keywords: list[str],
        genre: dict = None,
        user_keyword: str = ""
    ) -> dict:
        """
        Full research run for one niche.
        Runs YouTube in parallel with Trends + News.
        """

        print(f"\n[Aggregator] Researching: {niche}")

        # Build queries
        if genre and user_keyword:
            queries = self.query_builder.build_queries(
                genre, user_keyword
            )
            print(f"  Mode: GUIDED - '{user_keyword}'")
        elif genre:
            queries = self.query_builder.build_queries(genre, "")
            print(f"  Mode: TRENDING in {genre['name']}")
        else:
            queries = {
                'is_guided': False,
                'user_keyword': None,
                'youtube': keywords[:4],
                'google_trends': keywords[:5],
                'news': keywords[:3],
                'disambiguation_context': ''
            }

        results = {
            'niche': niche,
            'user_keyword': user_keyword,
            'is_guided': queries.get('is_guided', False),
            'disambiguation_context': queries.get(
                'disambiguation_context', ''
            ),
            'youtube_videos': [],
            'youtube_hooks': [],
            'rising_queries': [],
            'breakout_queries': [],
            'news_articles': [],
            'timestamp': datetime.utcnow().isoformat()
        }

        # Run all three scrapers in parallel
        yt_queries = queries.get('youtube', keywords[:3])
        trend_queries = queries.get('google_trends', keywords[:5])
        news_queries = queries.get('news', [niche])

        yt_task = asyncio.to_thread(
            self.youtube.search_with_queries,
            yt_queries, niche
        )
        trends_task = asyncio.to_thread(
            self.trends.get_rising_queries,
            trend_queries
        )
        news_task = asyncio.to_thread(
            self.news.get_news_custom,
            news_queries, niche
        )

        yt_result, trends_result, news_result = await asyncio.gather(
            yt_task, trends_task, news_task,
            return_exceptions=True
        )

        # YouTube
        if isinstance(yt_result, list):
            results['youtube_videos'] = yt_result
            results['youtube_hooks'] = self.youtube.extract_hooks(
                yt_result
            )
            for v in yt_result[:20]:
                self.db.store_trend_signal(
                    platform='youtube',
                    title=v['title'],
                    niche=niche,
                    signal_strength=v['signal_strength'],
                    raw_data=v
                )
            print(f"  YouTube: {len(yt_result)} videos")
        else:
            print(f"  YouTube failed: {yt_result}")

        # Trends
        if isinstance(trends_result, dict):
            results['rising_queries'] = trends_result.get('rising', [])
            results['breakout_queries'] = trends_result.get('breakout', [])
            total = (
                len(results['rising_queries'])
                + len(results['breakout_queries'])
            )
            print(
                f"  Trends: {total} queries "
                f"({len(results['breakout_queries'])} breakout)"
            )
        else:
            print(f"  Trends failed: {trends_result}")

        # News
        if isinstance(news_result, list):
            results['news_articles'] = news_result
            for article in news_result[:5]:
                self.db.store_trend_signal(
                    platform='google_news',
                    title=article['title'],
                    niche=niche,
                    signal_strength=article['signal_strength'],
                    raw_data=article
                )
            print(f"  News: {len(news_result)} articles")
        else:
            print(f"  News failed: {news_result}")

        return results

    def build_llm_briefing(self, research: dict) -> str:
        """Format research data into LLM prompt context."""

        niche = research['niche']
        lines = []

        if research.get('is_guided') and research.get('user_keyword'):
            lines.append(
                f"=== TARGETED RESEARCH: {niche.upper()} ==="
            )
            lines.append(
                f"User wants content about: "
                f"'{research['user_keyword']}'"
            )
            if research.get('disambiguation_context'):
                lines.append(research['disambiguation_context'])
        else:
            lines.append(
                f"=== TRENDING RESEARCH: {niche.upper()} ==="
            )

        lines.append(f"Scraped: {research['timestamp'][:19]}")
        lines.append("")

        # YouTube viral hooks
        if research['youtube_hooks']:
            lines.append(
                "VIRAL YOUTUBE SHORTS (100K+ views this week):"
            )
            lines.append(
                "These titles are proven to stop scrolling."
            )
            lines.append(
                "Learn the hook pattern, do not copy directly."
            )
            lines.append("")
            for hook in research['youtube_hooks'][:6]:
                lines.append(f"  • {hook}")
            lines.append("")

        # Breakout searches
        if research['breakout_queries']:
            lines.append(
                "BREAKOUT SEARCHES (5000%+ increase this week):"
            )
            lines.append(
                "First channel to make content on these wins."
            )
            lines.append("")
            for q in research['breakout_queries'][:5]:
                lines.append(f"  • {q['query']}")
            lines.append("")

        # Rising searches
        if research['rising_queries']:
            lines.append("RISING SEARCH QUERIES:")
            for q in research['rising_queries'][:6]:
                lines.append(
                    f"  • +{q['value']}%: {q['query']}"
                )
            lines.append("")

        # Breaking news
        if research['news_articles']:
            lines.append("BREAKING NEWS (last 48 hours):")
            lines.append(
                "Fresh news = content before others react."
            )
            lines.append("")
            for n in research['news_articles'][:4]:
                lines.append(
                    f"  • [{n['hours_ago']}h ago] {n['title']}"
                )
            lines.append("")

        return '\n'.join(lines)
