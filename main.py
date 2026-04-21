from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import personas, news, analyze
from services.db import setup_schema
from services.persona_store import seed_personas_if_empty
import os

app = FastAPI(title="Soltrex Synthetic Audience API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(personas.router, prefix="/personas", tags=["personas"])
app.include_router(news.router,     prefix="/news",     tags=["news"])
app.include_router(analyze.router,  prefix="/analyze",  tags=["analyze"])

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

# Serve frontend static files
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
