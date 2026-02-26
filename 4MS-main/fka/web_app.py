import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import re
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core.evaluator import EvaluationEngine
from core.question_generator import QuestionGenerator
from core.jd_paerser import JDParser


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
# Single .env at project root
load_dotenv(PROJECT_ROOT / ".env")


class SubmitPayload(BaseModel):
    session_id: str
    responses: List[str]


class SessionData(BaseModel):
    role: str
    jd_text: str
    questions: List[dict]
    responses: Optional[List[str]] = None
    total_time: float = 0.0
    evaluation: Optional[dict] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    cv_filename: Optional[str] = None


class WebFKAEngine:
    """Lightweight wrapper around the existing FKA core logic for the web UI."""

    def __init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not found. Please create a .env file in the project root "
                "and add your Groq API key, e.g. GROQ_API_KEY=sk_xxx"
            )

        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

        self.jd_parser = JDParser()
        self.evaluator = EvaluationEngine(api_key, model)
        self.question_generator = QuestionGenerator(api_key, model)

        # In‑memory session store: fine for a single-machine assessment tool
        self.sessions: Dict[str, SessionData] = {}

    def _load_default_jd_bytes(self) -> Tuple[str, bytes]:
        """
        Load the default JD file used for the web UI.

        Returns (filename, bytes_content).
        """
        # Look for the default JD in the CV filtering module
        jd_path = PROJECT_ROOT / "cv_filtering" / "Job Descriptions" / "Junior AI Engineer (Entry-Level) JD.pdf"
        if not jd_path.exists():
            raise FileNotFoundError(
                f"Default JD file not found at {jd_path}. "
                "Place a JD file there or adjust the path in web_app.py."
            )

        with jd_path.open("rb") as f:
            content = f.read()

        return jd_path.name, content

    def _parse_jd_from_bytes(self, filename: str, content: bytes) -> str:
        """Use JDParser to extract text from raw bytes in a file-like wrapper."""
        import io

        # Use a BytesIO buffer that behaves like an uploaded file for PyPDF2/docx
        buffer = io.BytesIO(content)
        buffer.name = filename  # Used by JDParser to detect extension

        # Provide getvalue for DOCX/TXT parsing path
        def _getvalue() -> bytes:
            return content

        buffer.getvalue = _getvalue  # type: ignore[attr-defined]

        jd_text = self.jd_parser.parse_uploaded_file(buffer)
        return jd_text

    def _extract_candidate_from_cv(self, filename: str, content: bytes) -> Tuple[Optional[str], Optional[str]]:
        """
        Best-effort extraction of candidate name and email from a CV/resume file.
        Keeps this lightweight (regex + filename heuristics) compared to the full CV filtering pipeline.
        """
        text = ""
        try:
            text = self._parse_jd_from_bytes(filename, content)
        except Exception:
            try:
                text = content.decode("utf-8", errors="ignore")
            except Exception:
                text = ""

        email: Optional[str] = None
        if text:
            emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z.-]+\.[A-Za-z]{2,}", text)
            if emails:
                email = emails[0]

        # Derive a human-looking name from the filename if possible
        name: Optional[str] = None
        base = Path(filename).stem
        # Remove common noise words
        base = re.sub(r"(?i)\b(cv|resume|curriculum|vitae)\b", " ", base)
        base = re.sub(r"[_\-]+", " ", base)
        parts = [p for p in base.split() if p.strip()]
        if parts:
            # Use first 2 tokens as a simple "First Last" guess
            name = " ".join(parts[:2])

        return name, email

    def init_session(
        self,
        jd_filename: Optional[str] = None,
        jd_bytes: Optional[bytes] = None,
        candidate_name: Optional[str] = None,
        candidate_email: Optional[str] = None,
        cv_filename: Optional[str] = None,
        questions: Optional[List] = None,  # NEW: Accept pre-generated questions
    ) -> Tuple[str, SessionData]:
        """
        Create a new interview session.

        If jd_bytes is provided, it will be used; otherwise the default JD file is loaded.
        If questions is provided, use them; otherwise generate them.
        """
        if jd_bytes is None or jd_filename is None:
            jd_filename, jd_bytes = self._load_default_jd_bytes()

        jd_text = self._parse_jd_from_bytes(jd_filename, jd_bytes)
        role = self.jd_parser.detect_job_role(jd_text)
        
        # Only generate questions if not provided
        if questions is None:
            pool = self.question_generator.generate_fka_pool(role, jd_text)
            # Flatten pool categories into a single list
            questions = []
            for qs in pool.values():
                questions.extend(qs)
            # Limit to 5 for consistency if generated as fallback
            questions = questions[:5]

        session_id = uuid.uuid4().hex
        session = SessionData(
            role=role,
            jd_text=jd_text,
            questions=questions,
            responses=[""] * len(questions),
            total_time=0.0,
            evaluation=None,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            cv_filename=cv_filename,
        )
        self.sessions[session_id] = session
        return session_id, session

    def submit_responses(self, payload: SubmitPayload) -> SessionData:
        session = self.sessions.get(payload.session_id)
        if not session:
            raise KeyError("Session not found")

        if len(payload.responses) != len(session.questions):
            raise ValueError("Number of responses does not match number of questions")

        session.responses = payload.responses
        # Simple approximation: assume 1 minute per question
        session.total_time = float(len(payload.responses))
        self.sessions[payload.session_id] = session
        return session

    def evaluate_session(self, session_id: str) -> SessionData:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("Session not found")

        if session.evaluation is not None:
            return session

        if not session.responses:
            raise ValueError("No responses submitted for this session")

        responses_data = []
        per_question_time = session.total_time / max(len(session.questions), 1)
        for i, q in enumerate(session.questions):
            responses_data.append(
                {
                    "question": q.get("question"),
                    "type": q.get("type"),
                    "difficulty": q.get("difficulty"),
                    "expected_keywords": q.get("expected_keywords", []),
                    "response": session.responses[i],
                    "response_time": per_question_time,
                }
            )

        evaluation = self.evaluator.evaluate_fundamental_responses(
            session.role,
            session.jd_text[:1000],
            session.questions,
            responses_data,
        )
        session.evaluation = evaluation
        self.sessions[session_id] = session
        return session


engine = WebFKAEngine()

app = FastAPI(title="FKA Web Interface")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=FileResponse)
def candidate_dashboard() -> FileResponse:
    """Serve the candidate dashboard invitation page."""
    html_path = BASE_DIR / "Candidate Dashboard"
    return FileResponse(path=str(html_path), media_type="text/html")


@app.get("/assessment", response_class=FileResponse)
def assessment_page() -> FileResponse:
    """Serve the main FKA assessment UI."""
    html_path = BASE_DIR / "FKA HTML"
    return FileResponse(path=str(html_path), media_type="text/html")


@app.get("/submitting", response_class=FileResponse)
def submitting_page() -> FileResponse:
    """Serve the submitting/progress page."""
    html_path = BASE_DIR / "FKA Submitting"
    return FileResponse(path=str(html_path), media_type="text/html")


@app.post("/api/init")
def api_init():
    """Initialize a new FKA session and return questions to the frontend."""
    session_id, session = engine.init_session()
    return {
        "session_id": session_id,
        "role": session.role,
        "questions": session.questions,
    }


@app.post("/api/init_from_upload")
async def api_init_from_upload(
    jd_file: UploadFile = File(...),
    cv_file: Optional[UploadFile] = File(None),
):
    """
    Initialize a session from an uploaded JD file and optional candidate information.
    """
    jd_bytes = await jd_file.read()
    cv_filename: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None

    if cv_file is not None:
        cv_bytes = await cv_file.read()
        cv_filename = cv_file.filename
        name_guess, email_guess = engine._extract_candidate_from_cv(cv_file.filename, cv_bytes)
        candidate_name = name_guess
        candidate_email = email_guess

    session_id, session = engine.init_session(
        jd_filename=jd_file.filename,
        jd_bytes=jd_bytes,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        cv_filename=cv_filename,
    )

    return {
        "session_id": session_id,
        "role": session.role,
        "questions": session.questions,
        "candidate_name": session.candidate_name,
        "candidate_email": session.candidate_email,
    }


@app.get("/api/session/{session_id}")
def api_get_session(session_id: str):
    """Return existing session metadata and questions."""
    session = engine.sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Session not found"})

    return {
        "session_id": session_id,
        "role": session.role,
        "questions": session.questions,
        "candidate_name": session.candidate_name,
        "candidate_email": session.candidate_email,
    }


@app.post("/api/submit")
def api_submit(payload: SubmitPayload):
    """Store the candidate's responses for a given session."""
    try:
        session = engine.submit_responses(payload)
        return {"ok": True, "session_id": payload.session_id, "question_count": len(session.questions)}
    except (KeyError, ValueError) as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.get("/api/evaluate/{session_id}")
def api_evaluate(session_id: str):
    """Run the full evaluation for a given session and return the results."""
    try:
        session = engine.evaluate_session(session_id)
        return {
            "session_id": session_id,
            "role": session.role,
            "total_time": session.total_time,
            "evaluation": session.evaluation,
        }
    except KeyError as e:
        if "not found" in str(e).lower() or "session" in str(e).lower():
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "Session not found or expired. Please take the assessment again from your portal."},
            )
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.get("/health")
def healthcheck():
    return {"status": "ok"}

