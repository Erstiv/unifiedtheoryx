"""Shared Jinja2 template instance with admin context injection and markdown filter."""
import re
import markupsafe
from starlette.templating import Jinja2Templates

_base = Jinja2Templates(directory="app/templates")


def _md_to_html(text):
    """Convert markdown text to HTML for display in templates."""
    if not text:
        return ""
    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("")
            continue

        # Headings
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h3>{_inline_format(stripped[4:])}</h3>')
            continue
        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2>{_inline_format(stripped[3:])}</h2>')
            continue
        if stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h1>{_inline_format(stripped[2:])}</h1>')
            continue

        # Blockquotes
        if stripped.startswith("> "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<blockquote>{_inline_format(stripped[2:])}</blockquote>')
            continue

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f'<li>{_inline_format(stripped[2:])}</li>')
            continue

        # Regular paragraph
        if in_list:
            html_parts.append("</ul>")
            in_list = False
        html_parts.append(f'<p>{_inline_format(stripped)}</p>')

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _inline_format(text):
    """Handle bold, italic, and inline code."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _render_section(data):
    """Render a research section that could be a dict with specific fields OR a generic {section_title, content} shape."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        # Check for generic Gemini shape: {section_title, content}
        if "content" in data and ("section_title" in data or len(data) <= 3):
            content = data.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            if isinstance(content, dict):
                parts = []
                for k, v in content.items():
                    label = k.replace("_", " ").title()
                    parts.append(f"<strong>{label}:</strong> {_extract_text(v)}")
                return "<br>".join(parts)
            return str(content)
    return ""


def _extract_text(item):
    """Extract display text from a value that might be a string, dict, or list."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        # Try common keys in priority order
        for key in ("fact", "text", "description", "content", "title", "name",
                     "headline", "reference", "finding", "event", "gap", "myth"):
            if key in item:
                return str(item[key])
        # Fallback: join all string values
        parts = [str(v) for v in item.values() if isinstance(v, (str, int, float))]
        return " — ".join(parts) if parts else str(item)
    if isinstance(item, list):
        return ", ".join(_extract_text(i) for i in item)
    return str(item)


# Register filters
_base.env.filters["markdown"] = lambda text: markupsafe.Markup(_md_to_html(text))
_base.env.filters["extract_text"] = _extract_text
_base.env.filters["render_section"] = lambda data: markupsafe.Markup(_render_section(data))


_orig = _base.TemplateResponse


def _inject_admin(request, name, context=None, **kwargs):
    if context is None:
        context = {}
    context["is_admin"] = request.session.get("is_admin", False) if hasattr(request, "session") else False
    context["danger_mode"] = request.session.get("danger_mode", False) if hasattr(request, "session") else False
    context["pope_mode"] = request.session.get("pope_mode", False) if hasattr(request, "session") else False
    return _orig(request, name, context, **kwargs)

_base.TemplateResponse = _inject_admin
templates = _base
