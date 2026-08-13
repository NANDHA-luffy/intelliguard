from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from app.db.database import get_db
from app.db import models
from app.core.schemas import SessionCreate, SessionOut

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

@router.post("/", response_model=SessionOut)
def create_session(session: SessionCreate, db: DBSession = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == session.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_session = models.Session(agent_id=session.agent_id, budget=session.budget, used=0.0)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s