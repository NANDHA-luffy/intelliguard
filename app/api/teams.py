from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from app.db.database import get_db
from app.db import models
from app.core.schemas import TeamCreate, TeamOut

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])

@router.post("/", response_model=TeamOut)
def create_team(team: TeamCreate, db: DBSession = Depends(get_db)):
    existing = db.query(models.Team).filter(models.Team.name == team.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team already exists")

    new_team = models.Team(name=team.name, budget=team.budget)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return new_team

@router.get("/{team_id}", response_model=TeamOut)
def get_team(team_id: int, db: DBSession = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team