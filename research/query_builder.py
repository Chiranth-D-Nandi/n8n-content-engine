# research/query_builder.py

class QueryBuilder:
    """
    Builds contextual search queries from genre + keyword.
    
    Solves the disambiguation problem:
    keyword="punch" + genre="animals"
    → queries target animal-related punch content
    → not boxing, not the car, not the drink
    """

    def build_queries(
        self,
        genre: dict,
        user_keyword: str = ""
    ) -> dict:
        """
        Build search queries for all scrapers.
        Returns different query sets per platform.
        """
        niche = genre['niche']
        base_keywords = genre['keywords']
        context = genre.get('context_hint', niche)

        if user_keyword:
            return self._guided_queries(
                user_keyword, genre, niche,
                context, base_keywords
            )
        else:
            return self._trending_queries(
                niche, context, base_keywords
            )

    def _guided_queries(
        self,
        keyword: str,
        genre: dict,
        niche: str,
        context: str,
        base_keywords: list[str]
    ) -> dict:
        """
        Build queries when user provided a keyword.
        
        Example:
        keyword = "punch"
        genre = animals
        context = "animals, wildlife, pets, nature"
        
        genre_context = "animals" (first word of context)
        
        youtube queries:
          "punch animals"
          "punch viral"  
          "animals punch"
          "punch animals shorts"
        
        The LLM then sees all results AND the disambiguation
        instruction, and correctly identifies this as
        animal-related punch content.
        """
        kw = keyword.strip().lower()
        # First word of context hint = main genre word
        genre_context = context.split(',')[0].strip()

        return {
            'user_keyword': kw,
            'is_guided': True,

            'youtube': [
                f"{kw} {genre_context}",
                f"{kw} viral",
                f"{genre_context} {kw}",
                f"viral {kw} {genre_context}",
                f"{kw} {genre_context} shorts"
            ],

            'google_trends': [
                kw,
                f"{kw} {genre_context}",
                f"{genre_context} {kw}"
            ][:5],

            'news': [
                f"{kw} {genre_context}",
                f"viral {kw}",
                f"{genre_context} {kw}"
            ],

            # This goes into LLM prompt
            # Tells LLM how to interpret the keyword
            'disambiguation_context': (
                f"The user wants content about '{kw}'. "
                f"The genre is {genre['name']} "
                f"(context: {context}). "
                f"Interpret '{kw}' within this genre only. "
                f"Example: genre=animals + keyword=punch means "
                f"an animal punching, not boxing or the drink."
            )
        }

    def _trending_queries(
        self,
        niche: str,
        context: str,
        base_keywords: list[str]
    ) -> dict:
        """No user keyword - find trending topics in genre."""
        return {
            'user_keyword': None,
            'is_guided': False,
            'youtube': base_keywords[:5],
            'google_trends': base_keywords[:5],
            'news': base_keywords[:3],
            'disambiguation_context': ''
        }
