import time
import random
from pytrends.request import TrendReq


class GoogleTrendsScraper:
    """
    Scrapes Google Trends for rising queries.
    No API key needed. Completely free.
    """

    def __init__(self):
        self.pytrends = TrendReq(
            hl='en-US',
            tz=360,
            timeout=(10, 25)
        )

    def get_rising_queries(
        self,
        keywords: list
    ) -> dict:
        """Get rising and trending queries."""
        keywords_to_use = keywords[:5]

        result = {
            'rising': [],
            'breakout': [],
            'error': None
        }

        try:
            self.pytrends.build_payload(
                keywords_to_use,
                timeframe='now 7-d',
                geo='US'
            )

            related = self.pytrends.related_queries()

            for keyword in keywords_to_use:
                if keyword not in related:
                    continue

                rising_df = related[keyword].get('rising')

                if rising_df is None or rising_df.empty:
                    continue

                for _, row in rising_df.head(10).iterrows():
                    query_data = {
                        'query': row['query'],
                        'value': int(row['value']),
                        'seed': keyword,
                        'is_breakout': int(row['value']) >= 5000
                    }

                    if query_data['is_breakout']:
                        result['breakout'].append(query_data)
                    else:
                        result['rising'].append(query_data)

            time.sleep(random.uniform(3, 6))

            total = len(result['rising']) + len(result['breakout'])
            print(
                f"[Trends] Found {total} rising queries "
                f"({len(result['breakout'])} breakout)"
            )

        except Exception as e:
            print(f"[Trends] Error: {e}")
            result['error'] = str(e)

        return result

    def get_today_trending(self) -> list:
        """Get today's overall trending searches."""
        try:
            trending_df = self.pytrends.trending_searches(pn='united_states')
            time.sleep(random.uniform(2, 4))
            return trending_df[0].tolist()[:15]
        except Exception as e:
            print(f"[Trends] Today's trending error: {e}")
            return []
