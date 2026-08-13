from pydantic import BaseModel

class TeamCreate(BaseModel):
    name: str
    budget: float

class TeamOut(BaseModel):
    id: int
    name: str
    budget: float

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    name: str
    team_id: int
    budget: float

class AgentOut(BaseModel):
    id: int
    name: str
    team_id: int
    budget: float

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    agent_id: int
    budget: float

class SessionOut(BaseModel):
    id: int
    agent_id: int
    budget: float
    used: float

    class Config:
        from_attributes = True