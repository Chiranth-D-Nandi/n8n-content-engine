"""
Main Entry Point - Genre Selection & Pipeline Orchestration

User flow:
1. Select a genre from list
2. Optionally enter a keyword/topic hint
3. Specify how many reels to generate
4. System produces complete reels
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from pipeline.full_pipeline import FullPipeline
from genres import list_genres, get_genre


def load_config() -> dict:
    """Load configuration from config.json"""
    with open("config.json") as f:
        return json.load(f)


def display_menu() -> tuple[dict, str]:
    """
    Two-step menu:
    1. Pick a genre
    2. Optionally enter a keyword/topic hint
    
    Returns: (genre_config, user_keyword)
    """

    genres = list_genres()

    print("\n" + "="*55)
    print("  MATIKS AI REEL GENERATOR")
    print("  Select a genre to create content for")
    print("="*55)
    print()
    print("  AVAILABLE GENRES:")
    print()

    for i, g in enumerate(genres, 1):
        print(
            f"  {i:2}. {g['name']:<28} "
            f"[{g['reel_style']:<12}] "
            f"{g['duration']}"
        )

    print()

    # Genre selection
    while True:
        try:
            choice = input("  Enter genre number: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(genres):
                selected_genre = get_genre(genres[idx]['id'])
                break
            print(f"  Please enter a number between 1 and {len(genres)}")
        except ValueError:
            print("  Please enter a valid number")

    print()
    print(f"  Selected: {selected_genre['name']}")
    print()

    # Optional keyword for guided generation
    print("  OPTIONAL: Enter a specific topic")
    print("  Examples: 'monkey punch', 'cold showers', 'ai news'")
    print("  Leave blank to find trending topics automatically")
    print()

    user_keyword = input("  Topic hint (press Enter to skip): ").strip()

    if user_keyword:
        print(f"\n  Will search for: '{user_keyword}'")
        print(f"     in context of: {selected_genre['name']}")
    else:
        print(f"\n  Will find trending topics in: {selected_genre['name']}")

    # How many reels
    print()
    try:
        count_input = input("  How many reels? (1-3, default 1): ").strip()
        if count_input:
            count = int(count_input)
            count = max(1, min(3, count))
        else:
            count = 1
    except ValueError:
        count = 1

    selected_genre['reels_per_day'] = count

    return selected_genre, user_keyword


def print_report(jobs: list, elapsed: float):
    """Print final generation report."""
    complete = [j for j in jobs if j.is_complete()]
    failed = [j for j in jobs if not j.is_complete()]

    print("\n\n" + "="*55)
    print("  GENERATION COMPLETE")
    print("="*55)
    print(f"\n  Completed: {len(complete)}/{len(jobs)}")
    print(f"  Failed:    {len(failed)}/{len(jobs)}")
    print(f"  Time:      {elapsed:.0f}s ({elapsed/60:.1f}m)")

    if complete:
        print(f"\n  {'─'*51}")
        print("  YOUR REELS (ready to upload):")
        for j in complete:
            if j.final_path:
                size_mb = (
                    j.final_path.stat().st_size / 1024 / 1024
                    if j.final_path.exists() else 0
                )
                print(f"\n  {j.topic[:47]}")
                print(f"     {j.final_path}")
                print(f"     {size_mb:.1f}MB")

    if failed:
        print(f"\n  {'─'*51}")
        print("  FAILED REELS:")
        for j in failed:
            print(f"\n  {j.topic[:47]}")
            if j.errors:
                print(f"     Error: {j.errors[0][:45]}")

    print(f"\n  {'='*55}")
    print("  Open outputs/ folder to find your reels")
    print("="*55)


async def main():
    """Main entry point - Menu, Config, Pipeline."""
    
    # Get config
    config = load_config()

    # User picks genre + optional keyword
    genre, user_keyword = display_menu()

    print(f"\n  Starting pipeline...")
    print(f"  Each reel takes ~5-8 minutes")
    print(f"     (Kling video generation: 3-5 min)\n")

    # Set up pipeline with selected genre(s)
    config['channels'] = [genre]
    config['user_keyword'] = user_keyword

    pipeline = FullPipeline(config)

    start = datetime.now()
    jobs = await pipeline.run_all_channels()
    elapsed = (datetime.now() - start).total_seconds()

    print_report(jobs, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
