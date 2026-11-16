import feedparser
from datetime import datetime, timedelta
from urllib.parse import quote


class NewsScraper:
    """
    Scrapes Google News RSS for breaking news in any niche.
    """

    NICHE_QUERIES = {
        'artificial intelligence': [
            'AI tools new 2024',
            'ChatGPT update',
            'artificial intelligence breakthrough',
        ],
        'self-improvement': [
            'productivity science research',
            'morning routine habits study',
        ],
        'personal finance': [
            'investing tips 2024',
            'personal finance advice',
        ],
        'health': [
            'fitness science research',
            'nutrition study 2024',
        ],
        'technology': [
            'technology news 2024',
            'tech innovation breakthrough',
        ]
    }

    def get_news(
        self,
        niche: str,
        max_age_hours: int = 48
    ) -> list:
        """Get recent news articles for a niche."""
        queries = self.NICHE_QUERIES.get(niche, [niche])
        all_articles = []
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        for query in queries:
            encoded_query = quote(query)
            url = (
                f"https://news.google.com/rss/search?"
                f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            )

            try:
                feed = feedparser.parse(url)

                for entry in feed.entries[:8]:
                    if hasattr(entry, 'published_parsed'):
                        pub_time = datetime(*entry.published_parsed[:6])
                    else:
                        pub_time = datetime.utcnow()

                    if pub_time < cutoff:
                        continue

                    hours_ago = (
                        datetime.utcnow() - pub_time
                    ).total_seconds() / 3600

                    all_articles.append({
                        'platform': 'google_news',
                        'title': entry.title,
                        'source': entry.get('source', {}).get('title', 'Unknown'),
                        'hours_ago': round(hours_ago, 1),
                        'query': query,
                        'niche': niche,
                        'signal_strength': max(0, 100 - hours_ago * 2)
                    })

            except Exception as e:
                print(f"[News] Error for '{query}': {e}")
                continue

        all_articles.sort(key=lambda x: x['hours_ago'])

        print(f"[News] '{niche}': {len(all_articles)} articles found")
        return all_articles

    def get_news_custom(
        self,
        queries: list,
        niche: str,
        max_age_hours: int = 48
    ) -> list:
        """Get recent news using custom query list (used by aggregator)."""
        all_articles = []
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        for query in queries:
            encoded_query = quote(query)
            url = (
                f"https://news.google.com/rss/search?"
                f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            )
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:8]:
                    if hasattr(entry, 'published_parsed'):
                        pub_time = datetime(*entry.published_parsed[:6])
                    else:
                        pub_time = datetime.utcnow()

                    if pub_time < cutoff:
                        continue

                    hours_ago = (
                        datetime.utcnow() - pub_time
                    ).total_seconds() / 3600

                    all_articles.append({
                        'platform': 'google_news',
                        'title': entry.title,
                        'source': entry.get('source', {}).get('title', 'Unknown'),
                        'hours_ago': round(hours_ago, 1),
                        'query': query,
                        'niche': niche,
                        'signal_strength': max(0, 100 - hours_ago * 2)
                    })
            except Exception as e:
                print(f"[News] Error for '{query}': {e}")
                continue

        all_articles.sort(key=lambda x: x['hours_ago'])
        print(f"[News] '{niche}': {len(all_articles)} articles found")
        return all_articles
