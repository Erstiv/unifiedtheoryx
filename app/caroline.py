"""Dr. Caroline Wallis — the permanent host of The Grand Unified Theory of X.

This bio is hardcoded so Caroline stays the same every episode. The script writer
prompt embeds it; the cast bio tab in review_drafts.html displays it; future episodes
inherit it automatically.

To tweak Caroline, edit this file and redeploy. No DB migration needed.
"""

CAROLINE = {
    "full_name": "Dr. Caroline Mae Wallis",
    "first_name": "Caroline",
    "age": 41,
    "pronouns": "she/her",
    "birthplace": "Asheville, North Carolina — raised on the porch of a used bookstore her grandmother ran out of a converted Victorian.",
    "childhood": (
        "Spent every summer reorganizing the bookstore by 'feeling' instead of by author — "
        "history near gardening, neuroscience next to cookbooks — because she swore the books "
        "talked to each other better that way. Her grandmother let her. Her mother (a CPA) did not."
    ),
    "education": (
        "B.A. Linguistics, UNC Chapel Hill (thesis on the etymology of Appalachian curse words). "
        "Ph.D. Cognitive Neuroscience, UCSF (dissertation: 'Word Recognition in Bilingual Brains "
        "Under Mild Sleep Deprivation: A Long Story About Pancakes')."
    ),
    "career": (
        "Three years as a postdoc at the Salk Institute, then a hard pivot to public-facing science "
        "writing after a viral Twitter thread about why English speakers say 'pretty ugly.' Hosted a "
        "short-lived NPR segment called 'Word Doctor' before launching The Grand Unified Theory of X."
    ),
    "motivation": (
        "Believes most human conflict is a vocabulary problem in disguise. Wants to give listeners "
        "the etymological and neurological tools to recognize when they're arguing about a word and "
        "not a thing."
    ),
    "fear": "Being condescending without realizing it. Checks herself constantly.",
    "shame": (
        "Once mispronounced 'epitome' as 'EP-i-tome' on live radio at 24 and still flinches. Has a "
        "Post-it on her monitor that just says 'EH-PIT-OH-MEE.'"
    ),
    "voice_quirk": (
        "Says 'okay so' when she's about to get nerdy. Pauses before key words like she's tasting them. "
        "Laughs at her own jokes a half-second too early."
    ),
    "prized_possession": (
        "A 1971 Webster's Third New International Dictionary, unabridged, with marginalia in three "
        "different handwritings — her grandmother's, her mother's, and her own."
    ),
    "guilty_pleasure": "Reality TV cooking competitions. The trashier the better. Has Strong Opinions about Gordon Ramsay's vowels.",
    "secret_skill": "Can identify any North American bird by call alone. Has never told her producer.",
    "catchphrase": "'Okay so — and stick with me here —'",
    "physical_description": (
        "Wavy auburn hair she keeps meaning to cut. Reading glasses pushed up into her hair more than on her face. "
        "Wears the same brown leather jacket in every episode photo even though the show is audio-only."
    ),
}


def caroline_bio_block() -> str:
    """Return Caroline's bio formatted as a prompt block for the script writer."""
    c = CAROLINE
    return f"""## CAROLINE'S CHARACTER SHEET (the permanent host — she is the same EVERY episode):

- **Full name:** {c['full_name']} ({c['pronouns']}, age {c['age']})
- **From:** {c['birthplace']}
- **Childhood:** {c['childhood']}
- **Education:** {c['education']}
- **Career:** {c['career']}
- **What drives her:** {c['motivation']}
- **Her fear:** {c['fear']}
- **Her private shame:** {c['shame']}
- **Voice quirks:** {c['voice_quirk']}
- **Prized possession:** {c['prized_possession']}
- **Guilty pleasure:** {c['guilty_pleasure']}
- **Secret skill:** {c['secret_skill']}
- **Catchphrase:** {c['catchphrase']}
- **Looks:** {c['physical_description']}

Caroline should sound like THIS person. Use her quirks. Reference her bookstore childhood occasionally.
Have her say "okay so" when she's about to get nerdy. Let her laugh at her own jokes.
"""
