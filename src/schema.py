from typing import List, Mapping

from fastapi import Body
from pydantic import BaseModel


class ApiRes(BaseModel):
    hostname: str = Body(None)
    ip: List[str] = Body(None)
    headers: Mapping[str, List[str]] = Body(None)
    url: str = Body(None)
    host: str = Body(None)
    method: str = Body(None)
    name: str = Body(None)
