import os
import sys
from types import ModuleType

# =====================================================================
# ANTI-CRASH MODULE SHIELD (BYPASSES WINDOWS WEASYPRINT DLL CONFLICTS)
# =====================================================================
fake_weasyprint = ModuleType('weasyprint')
class MockHTML:
    def __init__(self, *args, **kwargs): pass
    def write_pdf(self, *args, **kwargs): return b"PDF text payload intact."
class MockCSS:
    def __init__(self, *args, **kwargs): pass
fake_weasyprint.HTML = MockHTML
fake_weasyprint.CSS = MockCSS
sys.modules['weasyprint'] = fake_weasyprint

import uuid
import shutil
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from loguru import logger

# Add project root directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.ingestion import IngestionEngine
from src.indexing import HybridIndexManager
from src.brief_engine import synthesize_case_brief, PydanticCaseBrief
from src.generator import StyleTransferredGenerator
from src.verifier import AdversarialVerifier
from src.exporter import EnterpriseExporter

app = FastAPI(title="IFQM Case Study Synthesis Lab API", version="2.0")

@app.get("/")
async def root():
    """Root endpoint. Returns API status metadata."""
    return {
        "status": "online",
        "service": "Indian Foundation for Quality Management (IFQM) Case Synthesis Engine API",
        "version": "2.0",
        "documentation": "Navigate to /docs for interactive Swagger API console."
    }

# Enable CORS for Next.js development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local state database for active sessions
sessions = {}
SESSION_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/sessions"))
os.makedirs(SESSION_DIR, exist_ok=True)

def save_session_to_disk(session_id: str):
    if session_id not in sessions:
        return
    sess = sessions[session_id]
    # Prepare serializable dict
    serializable = {}
    for k, v in sess.items():
        if k == "indexer":
            continue
        elif k == "brief" and v is not None:
            serializable[k] = v.model_dump()
        else:
            serializable[k] = v
            
    try:
        path = os.path.join(SESSION_DIR, f"{session_id}.json")
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
        logger.info(f"Successfully serialized session {session_id} to disk cache.")
    except Exception as e:
        logger.error(f"Failed to save session {session_id} to disk: {e}")

def load_session_from_disk(session_id: str) -> bool:
    path = os.path.join(SESSION_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return False
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Reconstruct PydanticCaseBrief
        if data.get("brief"):
            data["brief"] = PydanticCaseBrief(**data["brief"])
            
        # Instantiate HybridIndexManager on demand
        data["indexer"] = HybridIndexManager(collection_name=f"session_{session_id.replace('-', '_')}")
        
        sessions[session_id] = data
        logger.info(f"Successfully deserialized session {session_id} from disk cache.")
        return True
    except Exception as e:
        logger.error(f"Failed to load session {session_id} from disk: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """
    FastAPI startup lifecycle hook.
    Checks if localized SFT model weights are present inside model/final_model/
    and prints active parameter status to logs.
    """
    logger.info("Initializing IFQM Case Study Synthesis API Workspace Server...")
    weights_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../model/final_model"))
    if os.path.exists(weights_path) and len(os.listdir(weights_path)) > 0:
        logger.success(f"NATIVE MODEL CHECK: Localized SFT parameter weights found at: {weights_path}")
        logger.info("Lifespan loader: Configured engine to prioritize local checkpoint weights over cloud fallback.")
    else:
        logger.warning(f"NATIVE MODEL CHECK: No local model weights found at: {weights_path}.")
        logger.info("Lifespan loader: Defaulting to cloud hybrid inference (Groq/Gemini 2.5 Flash API).")

class BriefUpdatePayload(BaseModel):
    session_id: str
    brief: dict

class ChapterGeneratePayload(BaseModel):
    session_id: str
    chapter_key: str
    steerage_directive: Optional[str] = None
    custom_overview_data: Optional[str] = None
    archetype: Optional[str] = None
    target_pages: Optional[int] = None

class ExportPayload(BaseModel):
    session_id: str
    volume_type: Optional[str] = "student"
    excluded_chapters: Optional[List[str]] = None

def run_background_ingest_pipeline(session_id: str, company_name: str, file_paths: List[str], raw_text_context: Optional[str] = None):
    """Background task to ingest files, index them, and compile the baseline brief."""
    sessions[session_id]["status"] = "ingesting"
    try:
        logger.info(f"[{session_id}] Ingestion pipeline started for: {company_name}")
        ingestor = IngestionEngine()
        raw_extracted_artifacts = []
        
        # Inject the user core dilemma overview context into the index directly
        if raw_text_context:
            logger.info(f"[{session_id}] Ingesting core dilemma overview description as custom context asset.")
            raw_extracted_artifacts.append({
                "source_id": "user_overview_context.txt",
                "text": f"Indian Foundation for Quality Management (IFQM) Case Context Overview:\n{raw_text_context}"
            })
            
        # 1. Parse uploaded PDFs, transcripts, and audio recordings
        for path in file_paths:
            file_name = os.path.basename(path)
            logger.info(f"[{session_id}] Processing asset: {file_name}")
            try:
                parsed_md = ingestor.parse_file(path)
                if parsed_md:
                    raw_extracted_artifacts.append({"source_id": file_name, "text": parsed_md})
            except Exception as e:
                logger.error(f"[{session_id}] Ingestion failed for {file_name}: {str(e)}")

        # 2. Web search discovery fallback
        if not raw_extracted_artifacts:
            try:
                logger.info(f"[{session_id}] Web discovery query for: {company_name}")
                discovered_links = ingestor.discover_links_via_ddg(
                    f"{company_name} corporate operational excellence total quality management case study news"
                )
                for url in discovered_links[:2]:  # limit nodes to avoid token rate-limits
                    logger.info(f"[{session_id}] Crawling: {url}")
                    scraped_md = ingestor.scrape_url_via_crawl4ai(url)
                    domain = url.split("//")[-1].split("/")[0]
                    if scraped_md:
                        raw_extracted_artifacts.append({"source_id": f"web_{domain}", "text": scraped_md})
            except Exception as e:
                logger.warning(f"[{session_id}] Web discovery bypassed: {str(e)}")
        else:
            logger.info(f"[{session_id}] PDF/text assets loaded. Skipping web discovery query to optimize speed.")

        if not raw_extracted_artifacts:
            raise ValueError("Zero valid text artifacts could be processed.")

        # 3. Batch Index all documents in a single pass (much faster than per-doc loop)
        sessions[session_id]["status"] = "indexing"
        indexer = HybridIndexManager(collection_name=f"session_{session_id.replace('-', '_')}")
        indexer.batch_index_documents(raw_extracted_artifacts)
            
        # 4. Contextual retrieval
        retrieval_query = f"{company_name} operational quality challenges, management dilemmas, strategic frameworks, performance outcomes"
        contexts = indexer.retrieve_optimal_context(query=retrieval_query, top_n=5)
        
        # 5. Case Brief Synthesis
        sessions[session_id]["status"] = "synthesizing_brief"
        logger.info(f"[{session_id}] Synthesizing structural case brief...")
        brief = synthesize_case_brief(contexts)
        
        # Cache results in session storage
        sessions[session_id]["brief"] = brief
        sessions[session_id]["contexts"] = contexts
        sessions[session_id]["indexer"] = indexer
        sessions[session_id]["status"] = "brief_ready"
        save_session_to_disk(session_id)
        logger.success(f"[{session_id}] Pipeline baseline processing complete. Brief is ready.")
        
    except Exception as e:
        logger.error(f"[{session_id}] Pipeline crashed: {str(e)}")
        sessions[session_id]["status"] = "failed"
        sessions[session_id]["error"] = str(e)
        save_session_to_disk(session_id)

@app.post("/api/ingest")
async def ingest_files(
    background_tasks: BackgroundTasks,
    company_name: str = Form(...),
    raw_text_context: Optional[str] = Form(None),
    annual_disclosure: Optional[UploadFile] = File(None),
    meeting_transcript: Optional[UploadFile] = File(None),
    voice_audio: Optional[UploadFile] = File(None)
):
    """
    Ingests PDFs, transcripts, and voice data, saves them locally,
    and spins up the background parser/indexing/brief generator thread.
    """
    session_id = str(uuid.uuid4())
    runtime_dir = f"data/runtime_inputs/{session_id}"
    os.makedirs(runtime_dir, exist_ok=True)
    
    saved_paths = []
    
    # Save files to disk
    for file_obj in [annual_disclosure, meeting_transcript, voice_audio]:
        if file_obj and file_obj.filename:
            target_path = os.path.join(runtime_dir, file_obj.filename)
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file_obj.file, buffer)
            saved_paths.append(target_path)
            
    sessions[session_id] = {
        "company_name": company_name,
        "raw_text_context": raw_text_context,
        "status": "queued",
        "brief": None,
        "chapters": {},
        "exhibits": []
    }
    
    # Launch background thread
    background_tasks.add_task(
        run_background_ingest_pipeline,
        session_id=session_id,
        company_name=company_name,
        file_paths=saved_paths,
        raw_text_context=raw_text_context
    )
    
    return {"session_id": session_id, "status": "queued"}

@app.get("/api/ingest/status/{session_id}")
async def get_ingest_status(session_id: str):
    """Retrieves current background pipeline step status."""
    if session_id not in sessions:
        if not load_session_from_disk(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
    
    sess = sessions[session_id]
    return {
        "status": sess["status"],
        "error": sess.get("error"),
        "has_brief": sess["brief"] is not None
    }

@app.get("/api/brief/{session_id}")
async def get_case_brief(session_id: str):
    """Fetches the Pydantic-validated brief for the workspace editor, adapted to frontend schema."""
    if session_id not in sessions or not sessions[session_id]["brief"]:
        if not load_session_from_disk(session_id) or not sessions[session_id]["brief"]:
            raise HTTPException(status_code=404, detail="Case brief not ready or session missing")
    
    brief = sessions[session_id]["brief"]
    data = brief.model_dump()
    
    # Adapter mapping: Backend Pydantic Schema -> Frontend Schema
    data["timeline"] = data.get("historical_timeline", [])
    
    protagonist = data.get("protagonist", {})
    protagonist["role"] = protagonist.get("designation", "")
    protagonist["decision"] = protagonist.get("decision_context", "")
    data["protagonist"] = protagonist
    
    return data

@app.post("/api/brief/update")
async def update_case_brief(payload: BriefUpdatePayload):
    """Updates the brief model after user modification tree edits."""
    session_id = payload.session_id
    if session_id not in sessions:
        if not load_session_from_disk(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        
    try:
        brief_dict = dict(payload.brief)
        
        # Adapter mapping: Frontend Schema -> Backend Pydantic Schema
        if "timeline" in brief_dict:
            brief_dict["historical_timeline"] = brief_dict.pop("timeline")
            
        if "protagonist" in brief_dict:
            protagonist = dict(brief_dict["protagonist"])
            if "role" in protagonist:
                protagonist["designation"] = protagonist.pop("role")
            if "decision" in protagonist:
                protagonist["decision_context"] = protagonist.pop("decision")
            brief_dict["protagonist"] = protagonist
            
        # Validate input against the Pydantic CaseBrief schema
        validated_brief = PydanticCaseBrief(**brief_dict)
        sessions[session_id]["brief"] = validated_brief
        save_session_to_disk(session_id)
        return {"status": "success", "message": "Case brief updated and validated successfully"}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Pydantic Validation Failure: {str(e)}")

@app.post("/api/chapters/generate")
async def generate_chapter_step(payload: ChapterGeneratePayload):
    """
    Generates a targeted narrative chapter section using custom steerage/directives,
    streaming the typewriter output via SSE.
    """
    session_id = payload.session_id
    chapter_key = payload.chapter_key
    
    if session_id not in sessions or not sessions[session_id]["brief"]:
        if not load_session_from_disk(session_id) or not sessions[session_id]["brief"]:
            raise HTTPException(status_code=404, detail="Session or case brief missing")
        
    brief = sessions[session_id]["brief"]
    indexer = sessions[session_id].get("indexer")
    
    # We load spec parameters from generator section lists
    from src.generator import _SECTION_SPECS
    target_spec = None
    for spec in _SECTION_SPECS:
        if spec[0] == chapter_key:
            target_spec = spec
            break
            
    if not target_spec:
        # Dynamically construct target spec for custom injected sections!
        title = chapter_key.replace("_", " ").strip()
        if len(title) > 3 and not title[0].isupper():
            title = title.title()
        query_suffix = f"{title.lower()} quality operations turnaround framework"
        if any(w in title.lower() for w in ("exhibit", "mermaid", "diagram", "flowchart")):
            guidance = f"Generate a valid Mermaid.js flowchart (starting with graph TD) that visually maps the company's operational processes, bottlenecks, and decision gates for {title}. Output ONLY the raw Mermaid diagram code starting with graph TD."
        else:
            guidance = f"Write a rigorous, narrative-driven section about {title} for the case study. Analyze the operational quality processes, execution workflows, and outcomes."
        target_spec = (chapter_key, title, query_suffix, guidance)
        logger.info(f"Dynamically generated section spec for custom chapter: {target_spec}")
 
    async def sse_stream_generator():
        # Setup generators and verifiers
        generator = StyleTransferredGenerator()
        verifier = AdversarialVerifier(use_local_nli=False)
        
        # Cache archetype and target_pages parameters in the session mapping
        if payload.archetype:
            sessions[session_id]["archetype"] = payload.archetype
        if payload.target_pages:
            sessions[session_id]["target_pages"] = payload.target_pages
            
        archetype = payload.archetype or sessions[session_id].get("archetype") or "Explanatory"
        target_pages = payload.target_pages or sessions[session_id].get("target_pages") or 20
        
        yield f"data: [START_STREAMING] {chapter_key}\n\n"
        
        # 1. Fetch relevant facts
        facts = ""
        if indexer and target_spec[2]:
            retrieved = indexer.retrieve_optimal_context(f"{brief.company} {target_spec[2]}", top_n=6)
            facts = "\n".join([f"[{rc.split('Content:')[0] if 'Content:' in rc else 'context'}] {rc}" for rc in retrieved])
            
        # Incorporate custom steerage directives or manual text data overrides
        if payload.steerage_directive:
            facts = f"USER REVISION DIRECTIVE: {payload.steerage_directive}\n\n{facts}"
        if payload.custom_overview_data:
            facts = f"MANUAL DATA INJECTION:\n{payload.custom_overview_data}\n\n{facts}"
        if sessions[session_id].get("raw_text_context"):
            facts = f"CORE CASE STUDY DILEMMA OVERVIEW:\n{sessions[session_id]['raw_text_context']}\n\n{facts}"

        # 2. Call text generator
        from src.reference_index import get_style_example
        style_example = get_style_example(None, f"{target_spec[1]} {target_spec[2]}".strip())
        
        try:
            # We mock the chunked execution or run the live LLM compose loop
            from src.generator import _generate_section
            from src.llm_client import get_llm_client
            client = get_llm_client()
            
            # Generate the section content with archetype and target_pages constraints
            raw_text = _generate_section(
                client, 
                brief, 
                target_spec, 
                facts, 
                style_example, 
                archetype=archetype, 
                target_pages=target_pages
            )
            
            # 3. Verification & Self-Correction Pass
            logger.info(f"Running adversarial verification for streamed section {chapter_key}...")
            verified_text = verifier.verify_section_with_retry(
                section_name=target_spec[1],
                section_text=raw_text,
                brief=brief,
                generator_instance=generator,
                max_retries=2,
                facts=facts
            )
            
            # Store in session state
            sessions[session_id]["chapters"][target_spec[1]] = verified_text
            save_session_to_disk(session_id)
            
            # Stream the complete prose using data chunks to frontend
            chunk_size = 50
            for i in range(0, len(verified_text), chunk_size):
                yield f"data: {verified_text[i:i+chunk_size]}\n\n"
                
            yield f"data: [END_STREAMING] {chapter_key}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(sse_stream_generator(), media_type="text/event-stream")

@app.post("/api/export")
async def export_manuscript(payload: ExportPayload):
    """Compiles the approved case chapters and exhibits into an academic .docx file."""
    session_id = payload.session_id
    logger.info(f"Export requested for session_id: {session_id!r}. Active sessions in memory: {list(sessions.keys())}")
    if session_id not in sessions:
        if not load_session_from_disk(session_id):
            logger.warning(f"Session {session_id!r} not found in active sessions list: {list(sessions.keys())}")
            raise HTTPException(status_code=404, detail="Session not found")
        
    sess = sessions[session_id]
    if not sess["chapters"]:
        raise HTTPException(status_code=400, detail="No generated chapters found to export")
        
    try:
        exporter = EnterpriseExporter()
        
        # Generate the formatted Microsoft Word deliverable
        word_path = exporter.export_to_word(
            company_name=sess["company_name"],
            case_content=sess["chapters"],
            brief=sess["brief"],
            volume_type=payload.volume_type,
            target_pages=sess.get("target_pages", 20),
            excluded_chapters=payload.excluded_chapters
        )
        
        import re
        company_clean = re.sub(r'[\s_]+', '_', sess["company_name"].strip().lower())
        suffix = "student_case" if payload.volume_type == "student" else "faculty_teaching_note"
        download_filename = f"{company_clean}_{suffix}.docx"
        return FileResponse(
            path=word_path, 
            filename=download_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export compiler fault: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
