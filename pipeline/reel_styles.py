"""
Reel Style System

Each style defines:
- Script structure (what the LLM writes)
- Visual direction (what Kling generates)
- Editing instructions (how FFmpeg composes it)
- Hook format (the specific opening pattern)
- Caption and text animation styles

This is what makes content feel native to platform
instead of like repurposed blog content.
"""

REEL_STYLES = {

    "rapid_fire": {
        "name": "Rapid Fire Facts",
        "description": "Fast cuts, numbered points, high energy",
        "hook_pattern": "{number} things about {topic} that will change how you think",
        "script_structure": """
STRUCTURE FOR RAPID FIRE FORMAT:
- Hook (3 sec): Bold number claim. "3 things about X nobody tells you."
- Point 1 (8 sec): Fact + one sentence explanation
- Point 2 (8 sec): Fact + one sentence explanation  
- Point 3 (8 sec): Fact + one sentence explanation
- CTA (3 sec): "Save this before they remove it"

TONE: Fast. Punchy. Every word earns its place.
No transitions. No "furthermore". Direct cuts.
Write like you're texting a friend who has 30 seconds.
        """,
        "visual_direction": """
Fast-paced montage style.
Each point gets its own visual scene.
High contrast. Dynamic angles. 
Abstract representations of each concept.
No static shots. Always moving.
        """,
        "editing": {
            "cut_style": "every_2_seconds",
            "text_animation": "pop_scale",
            "music_intensity": "high",
            "color_grade": "high_contrast_vivid",
            "hook_overlay": True,
            "hook_overlay_style": "number_countdown"
        }
    },

    "pov": {
        "name": "POV Format",
        "description": "Second person, immersive, personal",
        "hook_pattern": "POV: you just found out {topic}",
        "script_structure": """
STRUCTURE FOR POV FORMAT:
- Hook (3 sec): "POV: [situation they recognize]"
- Setup (10 sec): Paint the scenario in second person
  "You're doing X. You think Y. But here's what's actually happening..."
- Revelation (20 sec): The thing they didn't know
- Impact (10 sec): How this changes their life specifically
- CTA (5 sec): "Tell me if this happened to you"

TONE: Intimate. Like you're talking to one specific person.
Heavy on "you" and "your". Make them feel seen.
        """,
        "visual_direction": """
Immersive point-of-view aesthetic.
Footage that feels personal and relatable.
Warm or moody color grading depending on topic.
Slow zooms rather than hard cuts.
Lifestyle aesthetics that match the audience.
        """,
        "editing": {
            "cut_style": "slow_cinematic",
            "text_animation": "fade_in_words",
            "music_intensity": "medium",
            "color_grade": "warm_moody",
            "hook_overlay": True,
            "hook_overlay_style": "pov_label"
        }
    },

    "news_style": {
        "name": "Breaking News Style",
        "description": "Urgent, just happened, you need to know",
        "hook_pattern": "This just happened with {topic} and everyone needs to know",
        "script_structure": """
STRUCTURE FOR NEWS STYLE:
- Hook (3 sec): "Breaking: [thing that just happened/changed]"
- What happened (10 sec): The facts. Journalist style.
- Why it matters (15 sec): The implications for them personally
- What to do (10 sec): The action they should take
- CTA (5 sec): "Follow for daily updates on this"

TONE: Urgent but not alarmist. Credible. Like a friend
who works in the industry tipping you off.
        """,
        "visual_direction": """
Clean, professional aesthetic.
News ticker style elements.
Graphs and data visualizations.
Corporate but sleek.
Minimal color palette: black, white, accent color.
        """,
        "editing": {
            "cut_style": "medium_professional",
            "text_animation": "slide_in_left",
            "music_intensity": "low_tension",
            "color_grade": "clean_neutral",
            "hook_overlay": True,
            "hook_overlay_style": "breaking_label"
        }
    },

    "storytime": {
        "name": "Storytime",
        "description": "Narrative arc, beginning middle end",
        "hook_pattern": "Let me tell you what happened when {topic}",
        "script_structure": """
STRUCTURE FOR STORYTIME:
- Hook (5 sec): Drop into the middle of the story
  "I couldn't believe what I was seeing..."
- Setup (10 sec): Context. Who, what, where.
- Rising tension (15 sec): The conflict or discovery
- Resolution (15 sec): What happened / what was learned
- Lesson (5 sec): The one-line takeaway
- CTA (5 sec): "Has this ever happened to you?"

TONE: Conversational. Like telling a friend.
Short sentences. Natural pauses. 
Feels real even if it's general.
        """,
        "visual_direction": """
Cinematic narrative visuals.
Scene changes that match story beats.
Emotional color grading.
Slow reveals. Build atmosphere.
        """,
        "editing": {
            "cut_style": "narrative_beats",
            "text_animation": "typewriter",
            "music_intensity": "emotional_build",
            "color_grade": "cinematic_warm",
            "hook_overlay": False,
            "hook_overlay_style": None
        }
    },

    "documentary": {
        "name": "Mini Documentary",
        "description": "Educational, authoritative, cinematic",
        "hook_pattern": "The truth about {topic} they never taught you",
        "script_structure": """
STRUCTURE FOR DOCUMENTARY:
- Hook (5 sec): The surprising claim
- Context (15 sec): Why this matters / history
- Deep dive (25 sec): The actual information
- Implication (10 sec): What this means for them
- CTA (5 sec): "Follow for more truths like this"

TONE: Authoritative but accessible. 
Like a Netflix documentary but 60 seconds.
Slightly dramatic. Makes them feel educated.
        """,
        "visual_direction": """
Cinematic wide shots. Atmospheric.
Professional grade aesthetics.
Documentary color grade: slightly desaturated, film look.
Slow camera movements.
        """,
        "editing": {
            "cut_style": "slow_cinematic",
            "text_animation": "fade_elegant",
            "music_intensity": "atmospheric",
            "color_grade": "documentary_film",
            "hook_overlay": True,
            "hook_overlay_style": "title_card"
        }
    },

    "reaction": {
        "name": "Reaction / Commentary",
        "description": "Responding to something, hot take energy",
        "hook_pattern": "Wait. Did you see what just happened with {topic}?",
        "script_structure": """
STRUCTURE FOR REACTION:
- Hook (3 sec): "Wait. Did you see this?"
- What they're reacting to (10 sec): Set up the thing
- The take (20 sec): The opinion / analysis nobody said
- Why this matters (10 sec): Stakes
- CTA (5 sec): "Do you agree? Comment below"

TONE: Authentic reaction energy. Slightly unfiltered.
Like the most knowledgeable person in the room
just saw something and has thoughts.
        """,
        "visual_direction": """
Dynamic, energetic visuals.
Mix of abstract and concrete imagery.
Feels current and relevant.
Bold colors. High energy.
        """,
        "editing": {
            "cut_style": "energetic_medium",
            "text_animation": "bounce_in",
            "music_intensity": "medium_high",
            "color_grade": "vibrant_punchy",
            "hook_overlay": True,
            "hook_overlay_style": "reaction_emoji"
        }
    },

    "aesthetic": {
        "name": "Aesthetic Montage",
        "description": "Mood-first, minimal text, vibe-heavy",
        "hook_pattern": "This is what {topic} actually looks like",
        "script_structure": """
STRUCTURE FOR AESTHETIC:
- Minimal voiceover - let visuals carry it
- 2-3 key lines maximum
- Text on screen does most of the work
- Music IS the content
- End with one powerful line

TONE: Cool. Understated. The opposite of loud.
Less is more. Let them feel something.
        """,
        "visual_direction": """
Beautiful, carefully art-directed visuals.
Strong aesthetic coherence throughout.
Color palette locked to the mood.
Slow motion where appropriate.
Feels like a fashion film or Apple ad.
        """,
        "editing": {
            "cut_style": "slow_aesthetic",
            "text_animation": "minimal_fade",
            "music_intensity": "music_led",
            "color_grade": "strong_aesthetic",
            "hook_overlay": False,
            "hook_overlay_style": None
        }
    }

}


def get_style(style_name: str) -> dict:
    """Get style config, fallback to documentary if not found."""
    return REEL_STYLES.get(style_name, REEL_STYLES['documentary'])


def list_styles() -> list[str]:
    """Get all available style names."""
    return list(REEL_STYLES.keys())
