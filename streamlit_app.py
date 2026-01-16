import asyncio
from pathlib import Path
import time
import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests

# Load environment and set theme-friendly config
load_dotenv()
st.set_page_config(
    page_title="AI Document Intelligence", 
    page_icon="🧪", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS (Fixed for Dark/Light Mode Visibility) ---
st.markdown("""
    <style>
    /* Fixed Answer Card: Dark Background with White Text for 100% Visibility */
    .answer-card {
        background-color: #1E293B !important; /* Deep Navy Blue */
        padding: 30px;
        border-radius: 12px;
        border-left: 8px solid #4F46E5; /* Bright Indigo Accent */
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        margin-top: 25px;
        margin-bottom: 25px;
    }
    .answer-card h3 {
        color: #F8FAFC !important; /* Off-White Header */
        margin-top: 0 !important;
        font-weight: 700 !important;
    }
    .answer-card p, .answer-card li {
        color: #E2E8F0 !important; /* Light Gray Body Text */
        line-height: 1.8 !important;
        font-size: 1.1rem !important;
    }
    
    /* Button Styling */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3.5em;
        background-color: #4F46E5;
        color: white !important;
        font-weight: bold;
        border: none;
    }
    
    /* Source Tags */
    .source-tag {
        display: inline-block;
        background-color: #4F46E5;
        color: white !important;
        padding: 5px 15px;
        border-radius: 20px;
        font-size: 0.85rem;
        margin-right: 8px;
        margin-bottom: 8px;
        border: 1px solid #6366F1;
    }
    </style>
    """, unsafe_allow_html=True)

# --- LOGIC FUNCTIONS ---
@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)

def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path

async def send_rag_ingest_event(pdf_path: Path) -> None:
    client = get_inngest_client()
    await client.send(inngest.Event(
        name="rag/ingest_pdf",
        data={"pdf_path": str(pdf_path.resolve()), "source_id": pdf_path.name}
    ))

async def send_rag_query_event(question: str, top_k: int) -> str:
    client = get_inngest_client()
    result = await client.send(inngest.Event(
        name="rag_query_pdf_ai",
        data={"question": question, "top_k": top_k}
    ))
    return result[0]

def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")

def fetch_runs(event_id: str) -> list[dict]:
    try:
        url = f"{_inngest_api_base()}/events/{event_id}/runs"
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except: return []

def wait_for_run_output(event_id: str) -> dict:
    start = time.time()
    while time.time() - start < 60:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            if run.get("status") in ("Completed", "Succeeded", "Success"):
                return run.get("output") or {}
        time.sleep(1)
    return {}

# --- SIDEBAR ---
with st.sidebar:
    st.title("📂 Knowledge Base")
    uploaded = st.file_uploader("Upload PDF Documents", type=["pdf"])
    if uploaded:
        with st.status("Analyzing PDF...", expanded=False):
            path = save_uploaded_pdf(uploaded)
            asyncio.run(send_rag_ingest_event(path))
        st.success(f"File Ready: {uploaded.name}")
    st.divider()
    top_k = st.slider("Context Detail (Chunks)", 1, 20, 5)

# --- MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>🤖 AI Intelligence Hub</h1>", unsafe_allow_html=True)

with st.container():
    with st.form("rag_query_form", clear_on_submit=False):
        col1, col2 = st.columns([5, 1])
        with col1:
            question = st.text_input("What would you like to know?", placeholder="Ask a question about your documents...")
        with col2:
            st.write("##") # Vertical alignment
            submitted = st.form_submit_button("Search")

if submitted and question.strip():
    with st.spinner("🔍 Deep-scanning documents..."):
        event_id = asyncio.run(send_rag_query_event(question.strip(), int(top_k)))
        output = wait_for_run_output(event_id)
        answer = output.get("answer", "")
        sources = output.get("sources", [])

    # Displaying the High-Contrast Answer Card
    st.markdown(f"""
        <div class="answer-card">
            <h3>Result Found</h3>
            <p>{answer or "No matching information was found in your documents."}</p>
        </div>
    """, unsafe_allow_html=True)
    
    if sources:
        st.markdown("### 📚 Reference Citations")
        source_html = "".join([f'<span class="source-tag">📄 {s}</span>' for s in sources])
        st.markdown(source_html, unsafe_allow_html=True)
else:
    if not submitted:
        st.write("---")
        st.info("💡 Tip: Upload a PDF in the sidebar first, then type your question above.")