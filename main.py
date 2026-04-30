from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import personas, news, analyze, segments, upload, search_ad
from services.db import setup_schema
from services.persona_store import seed_personas_if_empty
import os

app = FastAPI(title="Hatch Audience Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(personas.router,  prefix="/personas",   tags=["personas"])
app.include_router(news.router,      prefix="/news",        tags=["news"])
app.include_router(analyze.router,   prefix="/analyze",     tags=["analyze"])
app.include_router(segments.router,  prefix="/segments",    tags=["segments"])
app.include_router(upload.router,    prefix="/upload",      tags=["upload"])
app.include_router(search_ad.router, prefix="/search-ad",   tags=["search_ad"])

@app.on_event("startup")
def on_startup():
    if os.environ.get("DATABASE_URL"):
        try:
            setup_schema()
            seed_personas_if_empty(n_per_cluster=10)
        except Exception as e:
            print(f"Startup warning: {e}")
    else:
        print("DATABASE_URL not set — skipping DB setup.")

@app.get("/health")
def health():
    return {"status": "ok", "db_connected": bool(os.environ.get("DATABASE_URL"))}

@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")

@app.get("/segments-ui")
def serve_segments():
    return FileResponse("frontend/segments.html")

@app.get("/search-ad-ui")
def serve_search_ad():
    return FileResponse("frontend/search_ad.html")

if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
