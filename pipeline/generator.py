import json
from database.db import MatiksDatabase
from pipeline.llm import GeminiClient
from pipeline.reel_styles import get_style
from research.aggregator import TrendAggregator


DURATION_WORD_COUNTS = {
    30: {'total': 65,  'hook': 12, 'body': 45, 'cta': 8},
    45: {'total': 97,  'hook': 15, 'body': 70, 'cta': 12},
    60: {'total': 130, 'hook': 15, 'body': 100, 'cta': 15},
    90: {'total': 195, 'hook': 20, 'body': 155, 'cta': 20},
}


class ContentGenerator:


    def __init__(
        self,
        llm: GeminiClient,
        db: MatiksDatabase,
        aggregator: TrendAggregator
    ):
        self.llm = llm
        self.db = db
        self.aggregator = aggregator

    async def generate_topics_for_channel(
        self,
        channel: dict,
        user_keyword: str = ""
    ) -> list:

        research = await self.aggregator.research_niche(
            niche=channel['niche'],
            keywords=channel['search_keywords'],
            genre=channel,
            user_keyword=user_keyword
        )

        briefing = self.aggregator.build_llm_briefing(research)
        recent_topics = self.db.get_recent_topics(
            channel_id=channel['id'],
            days=30
        )

        avoid_text = ""
        if recent_topics:
            avoid_text = (
                "\nDO NOT generate topics similar to these recent ones:\n"
                + '\n'.join(f"  - {t}" for t in recent_topics[:10])
            )

        duration = channel.get('duration_seconds', 60)
        reel_style = channel.get('reel_style', 'documentary')

        keyword_instruction = ""
        if user_keyword:
            keyword_instruction = (
                f"\nUSER REQUESTED: '{user_keyword}'\n"
                f"ALL topics MUST be specifically about '{user_keyword}' "
                f"within the {channel['niche']} context.\n"
            )

        prompt = f"""You are a viral {channel['name']} content strategist.

CHANNEL: {channel['name']}
NICHE: {channel['niche']}
AUDIENCE: {channel['target_audience']}
TONE: {channel['tone']}
REEL STYLE: {reel_style}
TARGET DURATION: {duration} seconds
{keyword_instruction}

{briefing}
{avoid_text}

Generate {channel['reels_per_day']} topics. Each must:
1. Come from the ACTUAL trend data above
2. Work as {duration}-second {reel_style} format video
3. Create immediate curiosity in first 3 seconds
4. Be SPECIFIC not generic

OUTPUT JSON only:
{{
  "topics": [
    {{
      "topic": "specific reel topic",
      "angle": "what makes this surprising",
      "hook_type": "curiosity_gap|contrarian|secret_reveal|urgency|number_fact",
      "inspired_by": "which trend signal",
      "why_now": "why this performs right now"
    }}
  ]
}}"""

        result = await self.llm.generate_json_async(prompt)
        topics = result.get('topics', [])

        if not topics:
            topics = [{
                'topic': f"The truth about {channel['niche']}",
                'angle': 'Insider knowledge',
                'hook_type': 'contrarian',
                'inspired_by': 'fallback',
                'why_now': 'evergreen'
            }]

        stored = []
        for t in topics[:channel['reels_per_day']]:
            topic_id = self.db.store_topic(
                channel_id=channel['id'],
                niche=channel['niche'],
                topic=t['topic'],
                angle=t.get('angle', ''),
                hook_type=t.get('hook_type', ''),
                inspired_by=t.get('inspired_by', ''),
                trend_context=briefing[:500]
            )
            print(f"  [Topic #{topic_id}] {t['topic']}")
            stored.append({'id': topic_id, **t})

        return stored

    async def generate_script(
        self,
        channel: dict,
        topic_data: dict,
        user_keyword: str = ""
    ) -> dict:


        duration = channel.get('duration_seconds', 60)
        reel_style_name = channel.get('reel_style', 'documentary')
        reel_style = get_style(reel_style_name)

        word_targets = DURATION_WORD_COUNTS.get(
            duration,
            DURATION_WORD_COUNTS[60]
        )

        keyword_instruction = ""
        if user_keyword:
            keyword_instruction = (
                f"\nUSER REQUESTED TOPIC: '{user_keyword}'\n"
                f"The script MUST be specifically about '{user_keyword}' "
                f"within the {channel['niche']} context.\n"
            )

        prompt = f"""You write viral short-form video scripts.

CHANNEL: {channel['name']}
NICHE: {channel['niche']}
TONE: {channel['tone']}
TOPIC: {topic_data['topic']}
ANGLE: {topic_data.get('angle', '')}
HOOK TYPE: {topic_data.get('hook_type', 'curiosity_gap')}
REEL STYLE: {reel_style_name}
{keyword_instruction}

CHANNEL RULES:
{chr(10).join(f'- {rule}' for rule in channel['content_rules'])}

REEL STYLE INSTRUCTIONS:
{reel_style['script_structure']}

DURATION: {duration} seconds
WORD COUNT TARGETS:
- Hook: ~{word_targets['hook']} words (first 3-5 seconds)
- Body: ~{word_targets['body']} words (middle section)
- CTA: ~{word_targets['cta']} words (last 3-5 seconds)
- Total: ~{word_targets['total']} words

OUTPUT: JSON only, no other text or markdown.
{{
  "hook": "opening line - creates immediate curiosity",
  "body": "main content - punchy points",
  "cta": "closing call to action",
  "full_script": "hook + body + cta combined, exactly as voice will speak it",
  "video_prompt": "simple and short 2 sentence visual description for CogVideoX-2B model which has 220 token limit for prompt, it generates bad videos with compex prompts and good videos with simple and short prompts, hence keep the visual description simple and related to {topic_data['topic']}",
  "editing_notes": {{
    "music_mood": "{channel.get('music_mood', 'background')}",
    "text_style": "{reel_style['editing'].get('text_animation', 'pop_scale')}",
    "pace": "fast|medium|slow"
  }},
  "caption": "instagram caption under 150 chars",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
}}"""

        result = await self.llm.generate_json_async(prompt)

        if not result:
            result = self._fallback_script(
                topic_data['topic'], duration, reel_style_name
            )

        required_fields = [
            'hook', 'body', 'cta', 'full_script',
            'video_prompt', 'editing_notes',
            'caption', 'hashtags'
        ]
        for field in required_fields:
            if field not in result:
                result[field] = (
                    [] if field in ['hashtags']
                    else {} if field == 'editing_notes'
                    else f"[{field} failed]"
                )

        result['reel_style'] = reel_style_name
        result['duration_seconds'] = duration

        script_id = self.db.store_script(
            channel_id=channel['id'],
            topic=topic_data['topic'],
            script=result
        )

        print(f"  [Script #{script_id}] {reel_style_name} | {duration}s")
        print(f"  Hook: {result.get('hook', '')[:60]}...")

        return {'id': script_id, **result}

    def _fallback_script(
        self,
        topic: str,
        duration: int,
        reel_style_name: str
    ) -> dict:
        #fallback for script generation
        return {
            'hook': f"Nobody is talking about this side of {topic}...",
            'body': f"Here is what you need to know. " * 3,
            'cta': "Follow for more content like this.",
            'full_script': (
                f"Nobody is talking about this side of {topic}. "
                f"Here is what you need to know. Follow for more."
            ),
            'video_prompt': (
                f"generate visuals of {topic},ensure no text in visuals"
            ),
            'editing_notes': {
                'music_mood': 'dramatic cinematic',
                'text_style': 'pop_scale',
                'pace': 'fast'
            },
            'caption': f"The truth about {topic} 👇",
            'hashtags': ['#viral', '#trending', '#facts', '#reels'],
            'reel_style': reel_style_name,
            'duration_seconds': duration
        }
