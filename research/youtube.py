import isodate
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeScraper:
    """
    Scrapes trending YouTube Shorts for a given niche.
    """

    def __init__(self, api_key: str):
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.quota_used = 0

    def get_trending_shorts(
        self,
        niche: str,
        keywords: list,
        days_back: int = 7
    ) -> list:
        """
        Get trending Shorts for a niche.
        """
        published_after = (
            datetime.utcnow() - timedelta(days=days_back)
        ).strftime('%Y-%m-%dT%H:%M:%SZ')

        all_videos = []
        seen_ids = set()

        for keyword in keywords[:3]:
            videos = self._search_and_fetch(
                keyword=keyword,
                niche=niche,
                published_after=published_after,
                seen_ids=seen_ids
            )
            all_videos.extend(videos)

        all_videos.sort(key=lambda x: x['views'], reverse=True)

        print(
            f"[YouTube] '{niche}': {len(all_videos)} Shorts found. "
            f"Quota used: {self.quota_used}"
        )
        return all_videos

    def search_with_queries(
        self,
        queries: list,
        niche: str,
        days_back: int = 7
    ) -> list:
        """
        Search YouTube with custom queries.
        Alias for get_trending_shorts but accepts pre-built queries.
        """
        return self.get_trending_shorts(niche, queries, days_back)

    def _search_and_fetch(
        self,
        keyword: str,
        niche: str,
        published_after: str,
        seen_ids: set
    ) -> list:
        """Two-step: search (get IDs) then fetch stats."""
        try:
            search_response = self.youtube.search().list(
                q=f"{keyword} shorts",
                part='id,snippet',
                type='video',
                videoDuration='short',
                order='viewCount',
                publishedAfter=published_after,
                maxResults=25,
                relevanceLanguage='en',
                regionCode='US'
            ).execute()

            self.quota_used += 100

            video_ids = [
                item['id']['videoId']
                for item in search_response.get('items', [])
                if item['id']['videoId'] not in seen_ids
            ]

            if not video_ids:
                return []

            seen_ids.update(video_ids)

            stats_response = self.youtube.videos().list(
                part='statistics,contentDetails,snippet',
                id=','.join(video_ids)
            ).execute()

            self.quota_used += len(video_ids)

            results = []
            for item in stats_response.get('items', []):
                duration_seconds = self._parse_duration(
                    item['contentDetails']['duration']
                )
                if duration_seconds > 60:
                    continue

                stats = item.get('statistics', {})
                snippet = item['snippet']

                views = int(stats.get('viewCount', 0))
                likes = int(stats.get('likeCount', 0))
                comments = int(stats.get('commentCount', 0))

                if views < 10_000:
                    continue

                engagement = (
                    (likes + comments) / views * 100
                ) if views > 0 else 0

                results.append({
                    'platform': 'youtube_shorts',
                    'video_id': item['id'],
                    'title': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'views': views,
                    'likes': likes,
                    'comments': comments,
                    'engagement_rate': round(engagement, 3),
                    'duration_seconds': duration_seconds,
                    'tags': snippet.get('tags', [])[:10],
                    'niche': niche,
                    'keyword': keyword,
                    'signal_strength': min(views / 100_000, 100)
                })

            return results

        except HttpError as e:
            if e.resp.status == 403:
                print(f"[YouTube] QUOTA EXCEEDED after {self.quota_used} units")
            else:
                print(f"[YouTube] HTTP error '{keyword}': {e}")
            return []
        except Exception as e:
            print(f"[YouTube] Error '{keyword}': {e}")
            return []

    def extract_hooks(self, videos: list) -> list:
        """Extract viral titles."""
        return [
            v['title']
            for v in videos
            if v['views'] > 100_000
        ][:10]

    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration."""
        try:
            return int(
                isodate.parse_duration(duration_str).total_seconds()
            )
        except Exception:
            return 999
