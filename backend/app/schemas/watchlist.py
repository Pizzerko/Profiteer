from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistAdd(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    created_at: datetime
