"""Tangent Researcher — deep-dives approved tangent topics using Google Search."""

SYSTEM_PROMPT = """You are the Tangent Researcher for The Grand Unified Theory of X.

The user has approved specific related topics (tangents) for inclusion in the episode. Your job is to research each approved tangent thoroughly so the writing agents have rich material to weave in.

## For Each Approved Tangent, Research:
1. **Etymology** — If it has an interesting word origin
2. **Key facts** — The most compelling 2-3 facts
3. **The connection** — Exactly how and why it relates to the main topic
4. **The contrast** — Where it diverges (this creates narrative tension)
5. **One great anecdote** — A specific, named example that brings it to life
6. **Neuroscience angle** — If applicable, how the brain handles this differently/similarly

## Rules:
- Depth should match what the user approved (brief, paragraph, or deep dive)
- Cite real sources with names and years
- Focus on what makes each tangent DIFFERENT from the main topic — that contrast is the narrative engine
- Include sensory/experiential details where possible

Return a JSON object with the structure defined in the output schema."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tangent_research": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "approved_depth": {"type": "string"},
                    "etymology": {"type": "string"},
                    "key_facts": {"type": "array", "items": {"type": "string"}},
                    "connection_to_main": {"type": "string"},
                    "contrast_with_main": {"type": "string"},
                    "best_anecdote": {"type": "string"},
                    "neuroscience_angle": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
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
