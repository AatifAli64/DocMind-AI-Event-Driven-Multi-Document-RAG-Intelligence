import os
from openai import OpenAI
from dotenv import load_dotenv
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072

splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)

def load_and_chunk_pdf(path: str):
    # Fixed typo: PDFReaser -> PDFReader
    docs = PDFReader().load_data(file=path)
    
    # Check if 'text' attribute exists to avoid errors
    texts = [d.text for d in docs if getattr(d, "text", None)]
    
    chunks = []
    for t in texts:
        chunks.extend(splitter.split_text(t))
    return chunks

def embed_texts(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBED_MODEL,
        # Fixed error: input=text -> input=texts
        input=texts,
    )
    return [item.embedding for item in response.data]