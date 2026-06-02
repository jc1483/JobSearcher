from __future__ import annotations

from pathlib import Path


def extract_resume_text(resume_path: Path) -> str:
    suffix = resume_path.suffix.lower()
    if suffix in {".txt", ".md", ".rtf"}:
        return resume_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            raise ImportError(
                "PDF resume support requires PyPDF2. Install with: pip install PyPDF2"
            ) from exc
        reader = PdfReader(resume_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ImportError(
                "Word resume support requires python-docx. Install with: pip install python-docx"
            ) from exc
        document = Document(resume_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    raise ValueError("Unsupported resume file type. Use .txt, .md, .rtf, .pdf, or .docx.")
