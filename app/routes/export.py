"""Routes — PDF and DOCX export."""
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import TOPICS_DIR
from app.models import Topic, Episode, OutputDocument

router = APIRouter()


@router.post("/topic/{topic_id}/export/{doc_type}")
async def export_document(topic_id: int, doc_type: str, db: Session = Depends(get_db)):
    """Export paper or script as PDF or DOCX."""
    if doc_type not in ("paper_pdf", "paper_docx", "script_pdf", "script_docx"):
        return JSONResponse({"error": "Invalid doc_type"}, status_code=400)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    episode = db.query(Episode).filter(Episode.topic_id == topic_id).first()
    if not topic or not episode:
        return JSONResponse({"error": "Topic or episode not found"}, status_code=404)

    # Create topic output directory
    topic_dir = TOPICS_DIR / str(topic_id)
    topic_dir.mkdir(parents=True, exist_ok=True)

    ext = "pdf" if doc_type.endswith("pdf") else "docx"
    content_type = "paper" if doc_type.startswith("paper") else "script"
    filename = f"{topic.slug}_{content_type}.{ext}"
    output_path = topic_dir / filename

    try:
        if doc_type == "paper_pdf":
            from app.output.pdf_generator import generate_paper_pdf
            generate_paper_pdf(
                title=episode.title or topic.title,
                subtitle=episode.subtitle or "",
                content=episode.paper_content or "",
                output_path=str(output_path),
            )
        elif doc_type == "paper_docx":
            from app.output.docx_generator import generate_paper_docx
            generate_paper_docx(
                title=episode.title or topic.title,
                subtitle=episode.subtitle or "",
                content=episode.paper_content or "",
                output_path=str(output_path),
            )
        elif doc_type == "script_pdf":
            from app.output.pdf_generator import generate_script_pdf
            generate_script_pdf(
                title=episode.title or topic.title,
                script=episode.script_content or "",
                output_path=str(output_path),
            )
        elif doc_type == "script_docx":
            from app.output.docx_generator import generate_script_docx
            generate_script_docx(
                title=episode.title or topic.title,
                script=episode.script_content or "",
                output_path=str(output_path),
            )

        # Record the export
        doc_record = OutputDocument(
            topic_id=topic_id,
            doc_type=doc_type,
            file_path=str(output_path),
            file_name=filename,
        )
        db.add(doc_record)
        db.commit()

        media_type = "application/pdf" if ext == "pdf" else \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(str(output_path), media_type=media_type, filename=filename)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
