from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Signal(BaseModel):
    id: str
    timestamp: datetime

    source: str
    environment: str

    service: str
    component: str

    type: str

    value: Optional[float] = None
    template_id: Optional[str] = None
    message: Optional[str] = None