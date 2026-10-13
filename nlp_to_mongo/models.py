from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union

class QueryRequest(BaseModel):
    text: str
    collection: Optional[str] = None
    db_name: str = "test"
    execute: bool = False
    page: int = 1
    page_size: int = 50

class QueryResponse(BaseModel):
    mongo_query: Union[Dict[str, Any], List[Any], Any]
    explanation: Optional[str] = None
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    total_count: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None

class RefreshSchemaRequest(BaseModel):
    collection: str
    db_name: str = "test"
