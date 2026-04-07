"""PDF Export — editorial magazine layout for papers, screenplay format for scripts."""
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Brand colors
NAVY = HexColor("#1a1f36")
AMBER = HexColor("#d4a574")
CREAM = HexColor("#faf7f2")
DARK_TEXT = HexColor("#2c2c2c")
MUTED = HexColor("#6b7280")


def _get_paper_styles():
    """Editorial magazine styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="EpisodeTitle",
        fontName="Times-Bold",
        fontSize=28,
        leading=34,
        textColor=NAVY,
        spaceAfter=8,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="EpisodeSubtitle",
        fontName="Times-Italic",
        fontSize=14,
        leading=18,
        textColor=MUTED,
        spaceAfter=24,
    ))
    styles.add(ParagraphStyle(
        name="SectionHead",
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        textColor=NAVY,
        spaceBefore=18,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="BodyText_Custom",
        fontName="Times-Roman",
        fontSize=11,
        leading=16,
        textColor=DARK_TEXT,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="PullQuote",
        fontName="Times-Italic",
        fontSize=13,
        leading=18,
        textColor=AMBER,
        leftIndent=36,
        rightIndent=36,
        spaceBefore=12,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="Footer",
        fontName="Helvetica",
        fontSize=8,
        textColor=MUTED,
        alignment=TA_CENTER,
    ))
    return styles


def _md_to_flowables(md_text: str, styles) -> list:
    """Convert markdown-ish text to ReportLab flowables."""
    flowables = []
    lines = md_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            flowables.append(Spacer(1, 6))
            continue

        # Section headings
        if line.startswith("## "):
            text = line[3:].strip()
            flowables.append(Spacer(1, 8))
            flowables.append(Paragraph(text, styles["SectionHead"]))
            continue

        # Bold/italic conversion for inline markup
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\*(.+?)\*", r"<i>\1</i>", line)

        # Blockquotes as pull quotes
        if line.startswith("> "):
            text = line[2:].strip()
            flowables.append(Paragraph(text, styles["PullQuote"]))
            continue

        flowables.append(Paragraph(line, styles["BodyText_Custom"]))

    return flowables


def generate_paper_pdf(title: str, subtitle: str, content: str, output_path: str):
    """Generate an editorial-style PDF for the blog post."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=1 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=1.2 * inch,
        rightMargin=1.2 * inch,
    )

    styles = _get_paper_styles()
    story = []

    # Title page
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph(title, styles["EpisodeTitle"]))
    if subtitle:
        story.append(Paragraph(subtitle, styles["EpisodeSubtitle"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "The Grand Unified Theory of X",
        ParagraphStyle("SeriesName", fontName="Helvetica", fontSize=10, textColor=AMBER)
    ))
    story.append(PageBreak())

    # Content
    if content:
        story.extend(_md_to_flowables(content, styles))

    # Footer
    story.append(Spacer(1, 24))
    story.append(Paragraph("&mdash; The Grand Unified Theory of X &mdash;", styles["Footer"]))

    doc.build(story)


def _get_script_styles():
    """Screenplay-format styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="ScriptTitle",
        fontName="Courier-Bold",
        fontSize=16,
        leading=20,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceAfter=24,
    ))
    styles.add(ParagraphStyle(
        name="CharacterName",
        fontName="Courier-Bold",
        fontSize=11,
        leading=14,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=2,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="Dialogue",
        fontName="Courier",
        fontSize=10,
        leading=14,
        textColor=DARK_TEXT,
        leftIndent=72,
        rightIndent=72,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Direction",
        fontName="Courier-Oblique",
        fontSize=9,
        leading=12,
        textColor=MUTED,
        leftIndent=36,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="TimingMarker",
        fontName="Courier",
        fontSize=9,
        textColor=AMBER,
        alignment=TA_RIGHT,
        spaceBefore=8,
        spaceAfter=4,
    ))
    return styles


def _substitute_cast_names(script: str) -> str:
    """If the script has a [CAST] block defining character names, replace
    generic role tags ([HOST], [EXPERT], [EVERYBODY]) with the actual first
    name in CAPS so the dialogue reads with real names.

    Looks for lines like:
        HOST: Dr. Caroline Wallis ...
        EXPERT: Marco Bellini, ...
        EVERYBODY: Sue Hartwell, ...
    inside a [CAST] ... [/CAST] block.
    """
    cast_match = re.search(r"\[CAST\](.*?)\[/CAST\]", script, re.DOTALL | re.IGNORECASE)
    if not cast_match:
        return script

    cast_text = cast_match.group(1)
    name_map = {}
    for role in ("HOST", "EXPERT", "EVERYBODY", "NARRATOR"):
        m = re.search(rf"{role}\s*:\s*(?:Dr\.?\s+|Prof\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+)?([A-Z][a-zA-Z'\-]+)",
                      cast_text)
        if m:
            name_map[role] = m.group(1).upper()

    if not name_map:
        return script

    def _replace(match):
        tag = match.group(1).upper()
        if tag in name_map:
            return f"[{name_map[tag]}]:"
        return match.group(0)

    return re.sub(r"\[(HOST|EXPERT|EVERYBODY|NARRATOR)\]:?", _replace, script)


def generate_script_pdf(title: str, script: str, output_path: str):
    """Generate a screenplay-format PDF for the podcast script."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=1 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
    )

    styles = _get_script_styles()
    story = []

    story.append(Paragraph(title, styles["ScriptTitle"]))
    story.append(Paragraph(
        "The Grand Unified Theory of X &mdash; Podcast Script",
        ParagraphStyle("ScriptSub", fontName="Courier", fontSize=10, textColor=MUTED, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 24))

    # Substitute generic role labels with actual cast names if a [CAST] block is present.
    # Old scripts use [HOST]/[EXPERT]/[EVERYBODY]; new scripts already use names directly.
    script = _substitute_cast_names(script) if script else script

    if script:
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
                continue

            # Timing markers
            if line.startswith("[TIMING:"):
                story.append(Paragraph(line, styles["TimingMarker"]))
                continue

            # Directions
            if line.startswith("[DIRECTION:") or line.startswith("[SFX:"):
                story.append(Paragraph(f"<i>{line}</i>", styles["Direction"]))
                continue

            # Character names (e.g., [HOST]:, [NARRATOR]:)
            char_match = re.match(r"\[([A-Z]+)\]:?\s*(.*)", line)
            if char_match:
                char_name = char_match.group(1)
                dialogue = char_match.group(2)
                story.append(Paragraph(char_name, styles["CharacterName"]))
                if dialogue:
                    story.append(Paragraph(dialogue, styles["Dialogue"]))
                continue

            # Regular dialogue
            story.append(Paragraph(line, styles["Dialogue"]))

    doc.build(story)
