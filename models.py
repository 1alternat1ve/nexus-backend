from pydantic import BaseModel

class ActivateRequest(BaseModel):
    code: str

class UserResponse(BaseModel):
    telegram_id: str
    username: str

class ActivateResponse(BaseModel):
    success: bool
    user: UserResponse | None = None
    error: str | None = None

class StatsResponse(BaseModel):
    total_activations: int
    last_activation: int | None
