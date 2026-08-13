from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.db.database import engine, Base
from app.db import models
from app.api import teams, agents, sessions, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="IntelliGuard", version="0.1.0")

app.include_router(teams.router)
app.include_router(agents.router)
app.include_router(sessions.router)
app.include_router(chat.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def dashboard():
    return FileResponse("app/static/index.html")

@app.get("/health")
def health():
    return {"status": "ok"}