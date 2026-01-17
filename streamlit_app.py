import asyncio
from pathlib import Path
import time
import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests

#Loading environment
load_dotenv()
st.set_page_config(page_title="DocMind AI", page_icon="🤖", layout="wide")

#SESSION STATE
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "last_uploaded" not in st.session_state:
    st.session_state.last_uploaded = None

#CSS STYLING
st.markdown("""
    <style>
    .answer-card {
        background-color: #1E293B;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #6366F1;
        margin: 20px 0;
    }
    .answer-card p { color: #E2E8F0; font-size: 1.1rem; }
    .source-tag {
        background-color: #475569;
        color: white;
        padding: 4px 12px;
        border-radius: 15px;
        font-size: 0.8rem;
        margin-right: 5px;
        border: 1px solid #6366F1;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_inngest_client():
    return inngest.Inngest(app_id="rag_app", is_production=False)

def save_uploaded_pdf(file):
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path

async def send_ingest(pdf_path):
    client = get_inngest_client()
    await client.send(inngest.Event(
        name="rag/ingest_pdf",
        data={"pdf_path": str(pdf_path.resolve()), "source_id": pdf_path.name}
    ))

async def send_query(question, top_k, source_ids):
    client = get_inngest_client()
    await client.send(inngest.Event(
        name="rag_query_pdf_ai",
        data={"question": question, "top_k": top_k, "source_ids": source_ids}
    ))
    return client

def get_run_result(event_id_mock=None):
    pass

def _inngest_api_base(): return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")

def wait_for_run_output(event_id):
    start = time.time()
    while time.time() - start < 60:
        try:
            url = f"{_inngest_api_base()}/events/{event_id}/runs"
            resp = requests.get(url)
            if resp.status_code == 200:
                runs = resp.json().get("data", [])
                if runs:
                    run = runs[0]
                    if run.get("status") == "Completed":
                        return run.get("output", {})
        except: pass
        time.sleep(1)
    return {}

async def trigger_and_wait(question, top_k, source_ids):
    client = get_inngest_client()
    ids = await client.send(inngest.Event(
        name="rag_query_pdf_ai",
        data={"question": question, "top_k": top_k, "source_ids": source_ids}
    ))
    return wait_for_run_output(ids[0])

#SIDEBAR UI
with st.sidebar:
    st.title("📂 DocuMind")
    
    compare_mode = st.toggle("Compare Mode", value=False)
    
    st.divider()
    
    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded_file:
        if uploaded_file.name not in st.session_state.uploaded_files:
            with st.status("Ingesting...", expanded=False):
                path = save_uploaded_pdf(uploaded_file)
                asyncio.run(send_ingest(path))
                st.session_state.uploaded_files.append(uploaded_file.name)
                st.session_state.last_uploaded = uploaded_file.name
            st.success(f"Added: {uploaded_file.name}")

    st.divider()

    target_files = []
    
    if compare_mode:
        st.info("📊 **Comparison Mode Active**\nSelect 2 or more files to analyze differences.")
        target_files = st.multiselect(
            "Select Documents:",
            options=st.session_state.uploaded_files,
            default=st.session_state.uploaded_files[:2] if len(st.session_state.uploaded_files) >= 2 else st.session_state.uploaded_files
        )
    else:
        st.info("💬 **Chat Mode Active**\nFocus on one document at a time.")
        idx = 0
        if st.session_state.last_uploaded in st.session_state.uploaded_files:
            idx = st.session_state.uploaded_files.index(st.session_state.last_uploaded)
            
        selected_file = st.selectbox(
            "Select Document:",
            options=st.session_state.uploaded_files,
            index=idx if st.session_state.uploaded_files else None
        )
        if selected_file:
            target_files = [selected_file] # Wrap single file in a list

#MAIN PAGE
st.title("🤖 AI Intelligence Hub")

if not target_files:
    st.warning("👈 Please upload or select a document in the sidebar to begin.")
else:
    if compare_mode:
        st.caption(f"Comparing: {', '.join(target_files)}")
    else:
        st.caption(f"Chatting with: {target_files[0]}")

    with st.form("query_form"):
        col1, col2 = st.columns([5, 1])
        question = col1.text_input("Question:", placeholder="Ask something about the selected file(s)...")
        col2.write("##")
        submitted = col2.form_submit_button("Ask")

    if submitted and question:
        with st.spinner("Analyzing documents..."):
            output = asyncio.run(trigger_and_wait(question, 5, target_files))
            
            answer = output.get("answer", "No response generated.")
            sources = output.get("sources", [])

        #Display The Result
        st.markdown(f"""
            <div class="answer-card">
                <h3>Analysis Result</h3>
                <p>{answer}</p>
            </div>
        """, unsafe_allow_html=True)

        if sources:
            st.markdown("#### Sources Used:")
            #Unique sources only
            unique_src = list(set(sources))
            tags = "".join([f'<span class="source-tag">📄 {s}</span>' for s in unique_src])
            st.markdown(tags, unsafe_allow_html=True)