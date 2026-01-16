import pydantic
from typing import List, Optional

class RAGChunkAndSrc(pydantic.BaseModel):
    chunks: List[str]
    source_id: Optional[str] = None

class RAGUpsertResult(pydantic.BaseModel):
    ingested: int

class RAGSearchResult(pydantic.BaseModel):
    contexts: List[str]
    sources: List[str]

class RAGQueryResult(pydantic.BaseModel):
    answer: str
    sources: List[str]
    num_contexts: int