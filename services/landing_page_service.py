import os
import base64
import tempfile
from pathlib import Path

ALLOWED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_PDF_TYPES   = {".pdf"}
MAX_FRAMES          = 8

def image_to_base64(file_path: str, media_type: str = "image/jpeg") -> dict:
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return {"data": data, "media_type": media_type}

def pdf_to_frames(pdf_path: str, max_frames: int = MAX_FRAMES) -> list:
    try:
        import fitz
        doc    = fitz.open(pdf_path)
        total  = len(doc)
        step   = max(1, total // max_frames)
        pages  = list(range(0, total, step))[:max_frames]
        frames = []
        for page_num in pages:
            page = doc[page_num]
            mat  = fitz.Matrix(1.5, 1.5)
            pix  = page.get_pixmap(matrix=mat)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                pix.save(tmp.name)
                frames.append(image_to_base64(tmp.name, "image/jpeg"))
                os.unlink(tmp.name)
        doc.close()
        print(f"PDF: {len(frames)} frames from {total} pages")
        return frames
    except Exception as e:
        print(f"PDF error: {e}")
        return []

def process_landing_page_file(file_path: str, filename: str) -> dict:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_PDF_TYPES:
        frames    = pdf_to_frames(file_path)
        file_type = "pdf"
    elif ext in ALLOWED_IMAGE_TYPES:
        mt     = "image/jpeg" if ext in [".jpg",".jpeg"] else f"image/{ext.lstrip('.')}"
        frames = [image_to_base64(file_path, mt)]
        file_type = "image"
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use JPG, PNG, WebP or PDF.")
    return {"filename": filename, "file_type": file_type, "frames": frames, "frame_count": len(frames)}
