# The Grand Unified Theory of X — Handoff Document
**Date:** 2026-04-12
**Live URL:** https://unifiedtheoryx.com
**GitHub:** https://github.com/Erstiv/unifiedtheoryx
**Hetzner:** filou (178.156.251.26), port 8016, systemd service `unified-theory`
**Local:** `/Users/JERS/Documents/Elliot Projects/unified-theory/`
**Server:** `/opt/unified-theory/`

---

## What This App Does
Takes any word/concept/phenomenon and generates a blog post + podcast script exploring it through etymology, neuroscience, history, culture, and more. Voice blends Adam Aleksic, Jess Zafarris, William Safire, Oliver Sacks, and Richard Feynman writing for Scientific American.

## Architecture
- **Stack:** Python 3.12 / FastAPI / SQLAlchemy / Jinja2+HTMX / Gemini API (Flash + Pro)
- **DB:** SQLite at `/opt/unified-theory/unified_theory.db`
- **Port:** 8016
- **Systemd:** `unified-theory.service`
- **Nginx:** `/etc/nginx/sites-available/unifiedtheoryx` → SSL via Let's Encrypt
- **Session middleware:** for admin auth + danger mode toggle

## 8-Agent Pipeline (3 Phases)
### Phase 1: Research
1. Deep Researcher (Flash + Google Search grounding)
2. Tangent Finder (Flash)
→ PAUSE: user reviews research + selects tangents
3. Tangent Researcher (Flash + Google Search) — runs after approval

### Phase 2: Writing
4. Paper Writer (Pro)
5. Script Writer (Pro) — supports 1/2/3 narrators
6. Title & Hook Generator (Flash)
→ PAUSE: user reviews drafts

### Phase 3: Polish
7. Editor (Pro) — refines both, strips citations, compiles appendix
8. Show Notes Generator (Flash)
→ AUTO-COMPLETE: Episode record created

## Key Features Built
- **Admin auth** — login at `/login`, password `gutx2026`. Topic creation now gated behind admin login.
- **Danger Zone** — hidden "danger zone — do not press" button (bottom-right). Red pulsing when active. Adds:
  - Full research display (all sections from deep researcher)
  - Custom tangent input (+ Add Tangent with depth selector)
  - Tangent research review page (editable text/sources, rerun with guidance)
  - Phase 2 editing (editable paper, script, title, cold open, cast bios, social hooks)
  - Inline citations [1] in paper/script → editor strips them → citations_appendix on Episode
  - References tab on episode page
- **Pope Me** — separate button above Danger Zone (bottom-right). Per-topic toggle stored in `topics.pope_mode` DB column. Injects Dr. Kâñé Štîvêřś Pōpé citation into paper/script.
- **Dr. Caroline Wallis** — permanent host character defined in `app/caroline.py`. Full method-actor character sheet (41yo, Asheville NC, UCSF cog-neuro PhD, "okay so" verbal tic). Prepended to script writer system prompt every episode.
- **Method-Actor Character Sheets** — 19-field schema per character (Expert + Everybody). Editable in Danger Zone on review-drafts cast tab. Printable character sheets.
- **Elastic Word Budget** — tangent depth (brief/paragraph/deep-dive) adjusts paper/script word target automatically. Base + per-tangent surcharge injected into LLM context.
- **3-Narrator System:**
  - HOST: Dr. Caroline Wallis (permanent, defined in `app/caroline.py`)
  - EXPERT (AI-invented character with name, title, personality — gender selectable)
  - THE EVERYBODY (AI-invented everyperson — gender selectable)
- **Rerun Failed Agents** — run status page shows rerun form when any agent fails. Review-drafts page also shows failed agents with rerun buttons. Approve button disabled until failures are resolved.
- **Startup Cleanup** — on boot, any `RUNNING` pipeline runs are marked `FAILED` and topic status reset. Prevents infinite "Pipeline running..." spinner after server restarts.
- **PDF Unicode Fonts** — DejaVu TrueType fonts registered in ReportLab (`app/output/pdf_generator.py`). Fixes black-box rendering for Dr. Pope's accented characters.
- **Export:** Paper PDF/DOCX + Script PDF/DOCX (ReportLab + python-docx)
- **Episode tracker/backlog** at `/backlog`
- **Knowledge Base** — admin-only, editable, 14 global seed entries (voice rules, episode structure, anti-patterns)
- **Topic delete** — admin-only with confirmation
- **Markdown rendering** — `| markdown` filter in templates
- **`| extract_text`** and **`| render_section`** filters — handle Gemini's inconsistent output shapes

## Known Issues / Rough Edges
1. **Gemini output shape inconsistency** — Deep researcher with Google Search grounding can't use `response_mime_type="application/json"`, so output structure varies. Templates have fallbacks (`render_section` filter) but some topics may still show empty sections.
2. **Citations end-to-end** — deployed but needs thorough testing through a full Danger Zone run.
3. **Gemini API key** — stored in `/opt/unified-theory/.env`. Key has gone invalid twice. Rotate at console.cloud.google.com → APIs & Services → Credentials if you start seeing `API_KEY_INVALID` errors. Never paste keys into chat.

## Deploy Process
```bash
# From the Air:
rsync -avz --exclude='*.db' --exclude='__pycache__' --exclude='.env' --exclude='topics/' --exclude='.git' --exclude='venv' \
  "/Users/JERS/Documents/Elliot Projects/unified-theory/" filou:/opt/unified-theory/

ssh filou "systemctl restart unified-theory"
```

## DB Migrations (if adding columns)
```bash
ssh filou "sqlite3 /opt/unified-theory/unified_theory.db 'ALTER TABLE tablename ADD COLUMN colname TYPE;'"
```

## Key File Map
| Purpose | Path |
|---------|------|
| Entry point | `app/main.py` (startup cleanup runs here) |
| Config | `app/config.py` (port, models, DR_POPE_MODE legacy fallback) |
| Models | `app/models.py` (6 tables, includes `pope_mode` on Topic) |
| Caroline (host) | `app/caroline.py` (full character sheet, `caroline_bio_block()`) |
| Base Agent | `app/agents/base.py` (Gemini calls, JSON parsing, KB writes, elastic word budget) |
| Pipeline Runner | `app/pipeline/runner.py` (phase orchestration, danger mode edit injection, topic status on failure) |
| All routes | `app/routes/{topics,pipeline,episodes,export,bible,auth}.py` |
| Pope toggle route | `app/routes/auth.py` — `/toggle-pope` POST |
| Shared templates | `app/templating.py` (markdown filter, extract_text, render_section, admin/danger/pope injection) |
| Knowledge Base | `app/bible/knowledge_base.py` |
| Voice/style seed | `bible_seed/seed_data.json` (14 entries — the creative DNA) |
| Prompts | `prompts/01-08_*.py` |
| CSS | `app/static/css/style.css` |
| Auth module | `app/auth.py` (password: gutx2026) |
| PDF generator | `app/output/pdf_generator.py` (DejaVu fonts for Unicode) |

## SSH Access
- Hetzner: `ssh filou` (alias for root@178.156.251.26)
- M4 Mac: `ssh elliotstivers@192.168.0.172` (local network only)
