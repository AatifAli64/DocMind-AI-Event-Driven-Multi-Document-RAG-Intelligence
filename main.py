import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from inngest.experimental import ai
from dotenv import load_dotenv
import uuid
import os
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc, RAGUpsertResult, RAGSearchResult
from qdrant_client import models 

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()
)

@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf")
)
async def rag_ingest(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunk_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunk_and_src.chunks
        source_id = chunk_and_src.source_id
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run(step_id="load-and-chunk", handler=lambda: _load(ctx), output_type=RAGChunkAndSrc)
    ingested =  await ctx.step.run(step_id="embed-and-upsert", handler=lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()

@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag_query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    # 1. Get inputs
    target_sources = ctx.event.data.get("source_ids", []) 
    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))

    def _search(question: str, top_k: int, target_sources: list[str]) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        
        q_filter = None
        if target_sources:
            q_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source", 
                        match=models.MatchAny(any=target_sources)
                    )
                ]
            )
            
        found = store.search(query_vec, top_k, query_filter=q_filter)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    found = await ctx.step.run("embed-and-search", lambda: _search(question, top_k, target_sources), output_type=RAGSearchResult)

    context_block = ""
    for i, txt in enumerate(found.contexts):
        context_block += f"\n--- SOURCE: {found.sources[i]} ---\n{txt}\n"

    if len(target_sources) > 1:
        user_content = (
            "You are an expert Document Analyst. The user has provided multiple documents.\n"
            "Your task is to COMPARE and CONTRAST the information found in them.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {question}\n\n"
            "Guidelines:\n"
            "1. Explicitly mention which document each fact comes from.\n"
            "2. Highlight contradictions or differences.\n"
            "3. Use a Markdown table if comparing numerical data."
        )
    else:
        user_content = (
            "You are a helpful AI assistant. Answer the question based strictly on the provided context.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {question}\n\n"
            "Guidelines:\n"
            "1. Be concise and direct.\n"
            "2. Do not hallucinate information not present in the context."
        )

    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_content}
            ]
        }
    )

    answer = res["choices"][0]["message"]["content"].strip()
    return {"answer": answer, "sources": found.sources, "num_contexts": len(found.contexts)}

app = FastAPI()
inngest.fast_api.serve(app, inngest_client, functions=[rag_ingest, rag_query_pdf_ai])