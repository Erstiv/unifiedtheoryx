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


# Register the filter
_base.env.filters["markdown"] = lambda text: markupsafe.Markup(_md_to_html(text))


_orig = _base.TemplateResponse


def _inject_admin(request, name, context=None, **kwargs):
    if context is None:
        context = {}
    context["is_admin"] = request.session.get("is_admin", False) if hasattr(request, "session") else False
    return _orig(request, name, context, **kwargs)

_base.TemplateResponse = _inject_admin
templates = _base
