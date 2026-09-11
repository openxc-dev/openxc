from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import athletes, finishes, meets, races, readers, results, starts, tags, teams, timing

app = FastAPI(title="OpenXC Race Timing API", version="1.0.0")

origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meets.router)
app.include_router(races.router)
app.include_router(starts.router)
app.include_router(teams.router)
app.include_router(athletes.router)
app.include_router(timing.router)
app.include_router(finishes.router)
app.include_router(results.router)
app.include_router(readers.router)
app.include_router(tags.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
