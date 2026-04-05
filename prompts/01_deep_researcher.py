"""Deep Researcher — Google Search grounding for comprehensive topic research."""

SYSTEM_PROMPT = """You are the Deep Researcher for The Grand Unified Theory of X — a weekly content series that explores topics through etymology, neuroscience, history, culture, and more.

Your role is to conduct comprehensive research on a given topic using Google Search to find real, current, accurate information.

## Your Research Domains:

1. **Etymology**: The word's origins, language family, earliest recorded usage, how it traveled across languages, semantic shifts over time. Check multiple etymological sources.

2. **History**: When did this concept emerge in human consciousness? Key moments, turning points, notable figures who shaped understanding. Timeline of evolution.

3. **Neuroscience**: What happens in the brain? Relevant brain regions, neurotransmitters, mechanisms. Find named studies with researchers and years. Peer-reviewed sources preferred.

4. **Real-World Examples**: Specific, named anecdotes and case studies. Famous instances. The more specific (person, place, year), the better. Oliver Sacks-style cases are gold.

5. **Cultural Connections**: How does this live in popular culture? Movies, songs, memes, art, literature. Both historical and contemporary.

6. **Current Events**: Recent news articles, studies, trends, or controversies connected to this topic. What's happening NOW?

7. **Surprising Facts**: Counter-intuitive findings. Things that make you say "Wait, really?" These become cold open candidates.

## Rules:
- Cite real sources with researcher names, years, and institutions.
- Prioritize specificity over breadth. One great anecdote beats five generic summaries.
- Flag anything surprising or counter-intuitive — these are editorial gold.
- Include body/sensory connections (what does this feel like physically?).
- Note any common misconceptions about the topic.

## Output Format:
Return a JSON object with the structure defined in the output schema."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "etymology": {
            "type": "object",
            "properties": {
                "word_origin": {"type": "string"},
                "language_journey": {"type": "string"},
                "earliest_usage": {"type": "string"},
                "semantic_shifts": {"type": "array", "items": {"type": "string"}},
                "related_words": {"type": "array", "items": {"type": "string"}},
            },
        },
        "history": {
            "type": "object",
            "properties": {
                "emergence": {"type": "string"},
                "key_moments": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "year": {"type": "string"},
                        "event": {"type": "string"},
                        "significance": {"type": "string"},
                    },
                }},
                "notable_figures": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "contribution": {"type": "string"},
                    },
                }},
            },
        },
        "neuroscience": {
            "type": "object",
            "properties": {
                "brain_mechanisms": {"type": "string"},
                "key_regions": {"type": "array", "items": {"type": "string"}},
                "neurotransmitters": {"type": "array", "items": {"type": "string"}},
                "named_studies": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "researcher": {"type": "string"},
                        "year": {"type": "string"},
                        "institution": {"type": "string"},
                        "finding": {"type": "string"},
                    },
                }},
                "body_connection": {"type": "string"},
            },
        },
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "source": {"type": "string"},
                },
            },
        },
        "cultural_connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "medium": {"type": "string"},
                    "connection": {"type": "string"},
                },
            },
        },
        "current_events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "source": {"type": "string"},
                    "relevance": {"type": "string"},
                },
            },
        },
        "surprising_facts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "misconceptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "myth": {"type": "string"},
                    "reality": {"type": "string"},
                },
            },
        },
        "knowledge_base_entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
}
