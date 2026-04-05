"""Routes — Knowledge Base viewer + admin edit/delete."""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BibleEntry, BibleScope, BibleCategory
from app.templating import templates
from app.auth import is_admin

router = APIRouter()


@router.get("/bible", response_class=HTMLResponse)
async def bible_viewer(request: Request, scope: str = "global", topic_id: int = None,
                       db: Session = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    if scope == "global":
        entries = db.query(BibleEntry).filter(
            BibleEntry.scope == BibleScope.GLOBAL,
            BibleEntry.is_active == True,
        ).order_by(BibleEntry.category, BibleEntry.sort_order).all()
    else:
        entries = db.query(BibleEntry).filter(
            BibleEntry.scope == BibleScope.TOPIC,
            BibleEntry.topic_id == topic_id,
            BibleEntry.is_active == True,
        ).order_by(BibleEntry.category, BibleEntry.sort_order).all()

    # Group by category
    grouped = {}
    for entry in entries:
        cat_label = entry.category.value.replace("_", " ").title()
        if cat_label not in grouped:
            grouped[cat_label] = []
        grouped[cat_label].append(entry)

    categories = [c.value for c in BibleCategory]

    return templates.TemplateResponse(request, "bible/viewer.html", {
        "entries": entries,
        "grouped": grouped,
        "scope": scope,
        "topic_id": topic_id,
        "categories": categories,
    })


@router.post("/bible/add")
async def add_entry(
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    scope: str = Form("global"),
    topic_id: int = Form(None),
    db: Session = Depends(get_db),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    try:
        cat = BibleCategory(category)
    except ValueError:
        return JSONResponse({"error": f"Invalid category: {category}"}, status_code=400)

    entry = BibleEntry(
        scope=BibleScope.GLOBAL if scope == "global" else BibleScope.TOPIC,
        topic_id=topic_id if scope == "topic" else None,
        category=cat,
        title=title,
        content=content,
        source="admin",
    )
    db.add(entry)
    db.commit()
    return RedirectResponse(f"/bible?scope={scope}" + (f"&topic_id={topic_id}" if topic_id else ""), status_code=303)


@router.post("/bible/{entry_id}/edit")
async def edit_entry(
    request: Request,
    entry_id: int,
    title: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    entry = db.query(BibleEntry).filter(BibleEntry.id == entry_id).first()
    if not entry:
        return HTMLResponse("Entry not found", status_code=404)

    entry.title = title
    entry.content = content
    db.commit()

    scope = "global" if entry.scope == BibleScope.GLOBAL else "topic"
    return RedirectResponse(f"/bible?scope={scope}" + (f"&topic_id={entry.topic_id}" if entry.topic_id else ""), status_code=303)


@router.post("/bible/{entry_id}/delete")
async def delete_entry(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
):
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)

    entry = db.query(BibleEntry).filter(BibleEntry.id == entry_id).first()
    if not entry:
        return HTMLResponse("Entry not found", status_code=404)

    scope = "global" if entry.scope == BibleScope.GLOBAL else "topic"
    tid = entry.topic_id
    entry.is_active = False
    db.commit()

    return RedirectResponse(f"/bible?scope={scope}" + (f"&topic_id={tid}" if tid else ""), status_code=303)
