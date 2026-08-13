from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from app.db.database import get_db
from app.db import models
from app.core.schemas import AgentCreate, AgentOut

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

@router.post("/", response_model=AgentOut)
def create_agent(agent: AgentCreate, db: DBSession = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.id == agent.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    new_agent = models.Agent(name=agent.name, team_id=agent.team_id, budget=agent.budget)
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent

@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, db: DBSession = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent