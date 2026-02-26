from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import json
import math
from datetime import datetime, date


def _json_safe(obj):
    """Convert NaN/Inf, numpy scalars, and datetimes so JSON serialization does not fail."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (int, str, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    # Numpy/pandas scalars (e.g. numpy.int64, numpy.float64, pd.NA)
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            return _json_safe(obj.item())
        except (ValueError, TypeError):
            return None
    try:
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        pass
    # Fallback: stringify so we never raise in json.dumps
    try:
        return str(obj)
    except Exception:
        return None
import importlib.util

from fastapi import FastAPI, File, HTTPException, Request, Depends, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import base64
import tempfile

"""
FastAPI app for IntiqAI: APIs (CV filter, FKA mount, etc.).
The previous HTML GUI has been disconnected and saved under the PreGUI folder.
"""

# This file lives in the "gui" module directory.
BASE_DIR = Path(__file__).resolve().parent
# So modules can be imported from root
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

GUI_DIR = BASE_DIR / "static"
FKA_DIR = ROOT_DIR / "fka"
LATEST_RUN_PATH = ROOT_DIR / "cv_filtering" / "latest_cv_run.json"
# Stable directory for latest upload-run results so dashboard can always load them
CV_FILTER_LATEST_DIR = ROOT_DIR / "cv_filtering" / "cv_filter_latest_run"

# Single .env at project root
load_dotenv(ROOT_DIR / ".env")
HR_PASSWORD = os.getenv("HR_PASSWORD", "hr2024")  # default for dev; set in .env for production

app = FastAPI(title="IntiqAI API")

# Verify audio utils are loadable at startup (so voice interview works)
import logging as _logging
_log = _logging.getLogger("uvicorn.error")
try:
    import interview.interview_session as _interview_session
    _audio_utils_ok = getattr(_interview_session, "transcribe_audio_file", None) is not None
    if _audio_utils_ok:
        _log.info("Audio utils loaded OK for voice interview (transcription available).")
    else:
        _log.warning("Audio utils not available (transcribe_audio_file is None). Set PYTHONPATH to the folder containing 'utils' or install dependencies. Voice answer will return 400.")
except Exception as _e:
    _log.warning("Audio utils not available: %s. Voice answer transcription will fail with 400.", _e)
    _audio_utils_ok = False

# Dynamically load FKA web backend (engine, models) so we can reuse its logic
fka_engine = None
fka_module = None
try:
    # FKA imports from core.*; ensure its directory is on the path
    _fka_dir = str(FKA_DIR)
    if _fka_dir not in sys.path:
        sys.path.insert(0, _fka_dir)
    fka_spec = importlib.util.spec_from_file_location(
        "fka_web_app", FKA_DIR / "web_app.py"
    )
    if fka_spec and fka_spec.loader:
        fka_module = importlib.util.module_from_spec(fka_spec)
        fka_spec.loader.exec_module(fka_module)  # type: ignore[arg-type]
        fka_engine = fka_module.engine
        # Mount the original FKA FastAPI app under /fka
        app.mount("/fka", fka_module.app, name="fka")  # type: ignore[attr-defined]
except Exception as _e:
    # We'll raise a clear HTTP error if FKA endpoints are called without this loaded.
    import logging
    logging.getLogger("uvicorn.error").warning("FKA module failed to load: %s", _e)
    fka_engine = None


# Serve new GUI (IntiqAI_GUI) and route HTML pages
def _html(path: Path) -> HTMLResponse:
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page not found.")
    return HTMLResponse(path.read_text(encoding="utf-8"))

app.mount("/static/gui", StaticFiles(directory=str(GUI_DIR), html=True), name="gui_static")


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Landing page."""
    return _html(GUI_DIR / "Main_Pages" / "Landing_Page")


@app.get("/hr/login", include_in_schema=False, response_class=HTMLResponse)
async def hr_login_page() -> HTMLResponse:
    return _html(GUI_DIR / "Main_Pages" / "HR_Login")


@app.get("/hr/signup", include_in_schema=False, response_class=HTMLResponse)
async def hr_signup_page() -> HTMLResponse:
    return _html(GUI_DIR / "Main_Pages" / "HR_Signup")


@app.get("/candidate/login", include_in_schema=False, response_class=HTMLResponse)
async def candidate_login_page() -> HTMLResponse:
    return _html(GUI_DIR / "Main_Pages" / "Candidate_Login")


@app.get("/hr/overview", include_in_schema=False, response_class=HTMLResponse)
async def hr_overview_page() -> HTMLResponse:
    return _html(GUI_DIR / "HR" / "Overview")


@app.get("/hr/admin", include_in_schema=False, response_class=HTMLResponse)
async def hr_admin_page() -> HTMLResponse:
    return _html(GUI_DIR / "HR" / "Admin_Management")


@app.get("/hr/upload", include_in_schema=False, response_class=HTMLResponse)
async def hr_upload_page() -> HTMLResponse:
    return _html(GUI_DIR / "HR" / "Upload")


@app.get("/candidate/portal", include_in_schema=False, response_class=HTMLResponse)
async def candidate_portal_page() -> HTMLResponse:
    return _html(GUI_DIR / "Candidate" / "Portal")


@app.get("/candidate/fka/result", include_in_schema=False, response_class=HTMLResponse)
async def candidate_fka_result_page() -> HTMLResponse:
    return _html(GUI_DIR / "Candidate" / "FKA_Result")


@app.get("/candidate/interview", include_in_schema=False, response_class=HTMLResponse)
async def candidate_interview_page() -> HTMLResponse:
    return _html(GUI_DIR / "Candidate" / "Interview")


@app.get("/candidate/fka", include_in_schema=False, response_class=RedirectResponse)
async def fka_landing() -> RedirectResponse:
    """Redirect to the mounted FKA web app."""
    return RedirectResponse(url="/fka/")


@app.get("/candidate/fka/stage", include_in_schema=False, response_class=RedirectResponse)
async def fka_stage() -> RedirectResponse:
    """Backward-compatible route pointing at FKA assessment UI."""
    return RedirectResponse(url="/fka/assessment")


def _hr_authenticated(request: Request) -> bool:
    # HR access is granted if they have the hr_token OR they are an admin
    return request.cookies.get("hr_token") == "ok" or request.cookies.get("admin_token") == "ok"

def _admin_authenticated(request: Request) -> bool:
    return request.cookies.get("admin_token") == "ok"

def _get_hr_role(request: Request) -> str:
    if _admin_authenticated(request):
        return "admin"
    return "hr"

def _get_candidate_id(request: Request) -> Optional[str]:
    return request.cookies.get("candidate_id") or None


class HRLoginPayload(BaseModel):
    email: Optional[str] = None
    password: str

class HRSignupPayload(BaseModel):
    email: str
    password: str

class CandidateLoginPayload(BaseModel):
    email: str
    password: str

class CredentialItem(BaseModel):
    candidate_id: str
    email: str
    password: str

class SetCredentialsPayload(BaseModel):
    run_id: str
    credentials: list[CredentialItem]


@app.post("/api/auth/hr_signup", response_class=JSONResponse)
async def api_hr_signup(payload: HRSignupPayload) -> JSONResponse:
    from db.store import create_hr_user
    from shared.credentials_automation import send_admin_new_signup_notification
    
    if not payload.email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required.")
    
    success = create_hr_user(payload.email, payload.password)
    if not success:
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    # Notify admin of the new request
    try:
        send_admin_new_signup_notification(payload.email)
    except Exception as e:
        _log.warning(f"Admin notification failed for signup {payload.email}: {e}")
        
    return JSONResponse({"ok": True, "message": "Signup request submitted and awaiting admin approval."})


@app.post("/api/auth/hr_login", response_class=JSONResponse)
async def api_hr_login(payload: HRLoginPayload, response: Response) -> JSONResponse:
    from db.store import hr_login
    user = hr_login(payload.email or "", payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password, or account pending approval.")
        
    role = user.get("role", "hr")
    resp = JSONResponse({"ok": True, "role": role})
    
    # Set cookies based on successful auth
    if role == "admin":
        resp.set_cookie(key="admin_token", value="ok", path="/", max_age=86400 * 7)
    
    resp.set_cookie(key="hr_token", value="ok", path="/", max_age=86400 * 7)
    return resp


@app.post("/api/auth/hr_logout", response_class=JSONResponse)
async def api_hr_logout(response: Response) -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key="hr_token", path="/")
    resp.delete_cookie(key="admin_token", path="/")
    return resp


# ----- Admin Management Endpoints -----

@app.get("/api/admin/pending_users", response_class=JSONResponse)
async def api_admin_pending_users(request: Request) -> JSONResponse:
    if not _admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin access required.")
    from db.store import get_pending_hr_users
    return JSONResponse({"ok": True, "users": get_pending_hr_users()})


class AdminUserAction(BaseModel):
    email: str


@app.post("/api/admin/approve_user", response_class=JSONResponse)
async def api_admin_approve_user(request: Request, payload: AdminUserAction) -> JSONResponse:
    if not _admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin access required.")
    from db.store import approve_hr_user
    if approve_hr_user(payload.email):
        return JSONResponse({"ok": True})
    raise HTTPException(status_code=404, detail="User not found.")


@app.post("/api/admin/reject_user", response_class=JSONResponse)
async def api_admin_reject_user(request: Request, payload: AdminUserAction) -> JSONResponse:
    if not _admin_authenticated(request):
        raise HTTPException(status_code=403, detail="Admin access required.")
    from db.store import reject_hr_user
    if reject_hr_user(payload.email):
        return JSONResponse({"ok": True})
    raise HTTPException(status_code=404, detail="User not found.")


@app.get("/api/auth/hr_me", response_class=JSONResponse)
async def api_hr_me(request: Request) -> JSONResponse:
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return JSONResponse({"ok": True, "role": _get_hr_role(request)})


@app.post("/api/auth/candidate_login", response_class=JSONResponse)
async def api_candidate_login(payload: CandidateLoginPayload, response: Response) -> JSONResponse:
    from db.store import candidate_login
    info = candidate_login(payload.email or "", payload.password or "")
    if not info:
        raise HTTPException(status_code=401, detail="Invalid email or password, or account disabled.")
    resp = JSONResponse({
        "ok": True,
        "candidate_id": info["candidate_id"],
        "run_id": info["run_id"],
        "status": info["status"],
        "first_name": info.get("first_name", ""),
        "last_name": info.get("last_name", ""),
    })
    resp.set_cookie(key="candidate_id", value=info["candidate_id"], path="/", max_age=86400 * 30)
    return resp


@app.post("/api/auth/candidate_logout", response_class=JSONResponse)
async def api_candidate_logout(response: Response) -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key="candidate_id", path="/")
    return resp


@app.get("/candidate/set-password", include_in_schema=False, response_class=HTMLResponse)
async def candidate_set_password_page() -> HTMLResponse:
    return _html(GUI_DIR / "Candidate" / "Set_Password")


class SetPasswordPayload(BaseModel):
    token: str
    password: str


@app.post("/api/candidate/set-password", response_class=JSONResponse)
async def api_candidate_set_password(payload: SetPasswordPayload) -> JSONResponse:
    from db.store import get_candidate_by_token, set_candidate_password
    
    candidate = get_candidate_by_token(payload.token)
    if not candidate:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
        
    success = set_candidate_password(candidate["candidate_id"], payload.password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set password.")
        
    return JSONResponse({"ok": True})



@app.get("/api/hr/overview", response_class=JSONResponse)
async def api_hr_overview(request: Request) -> JSONResponse:
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import get_overview
    data = get_overview()
    data["role"] = _get_hr_role(request)
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


@app.post("/api/hr/candidates/credentials", response_class=JSONResponse)
async def api_set_credentials(request: Request, payload: SetCredentialsPayload) -> JSONResponse:
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import set_candidate_credentials
    try:
        set_candidate_credentials(
            payload.run_id,
            [{"candidate_id": c.candidate_id, "email": c.email, "password": c.password} for c in payload.credentials],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"ok": True})


class AutoCreateCredentialsPayload(BaseModel):
    run_id: str
    action: Optional[str] = None  # "delete_run" to delete the run instead of sending credentials


@app.post("/api/hr/credentials/auto-create", response_class=JSONResponse)
async def api_auto_create_credentials(request: Request, payload: AutoCreateCredentialsPayload) -> JSONResponse:
    """
    If action is "delete_run": remove the run and all its candidates.
    Otherwise: extract emails, generate passwords, save credentials, and send SMTP emails.
    """
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    run_id = (payload.run_id or "").strip()
    if payload.action == "delete_run":
        from db.store import delete_run
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required.")
        ok = delete_run(run_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Run not found.")
        return JSONResponse({"ok": True})
    try:
        from shared.credentials_automation import auto_create_and_send
        base_url = str(request.base_url).rstrip("/")  # e.g. http://127.0.0.1:8001
        result = auto_create_and_send(run_id, base_url=base_url)
        return JSONResponse({
            "ok": True,
            "created": result["created"],
            "skipped_no_email": result["skipped_no_email"],
            "errors": result.get("errors", []),
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": str(e), "created": 0, "skipped_no_email": 0, "errors": [str(e)]},
        )


# Question Pool Management Endpoints
class QuestionPoolsPayload(BaseModel):
    fka_pool: dict
    interview_pool: dict

@app.get("/api/hr/run/{run_id}/questions", response_class=JSONResponse)
async def get_run_questions(run_id: str, request: Request) -> JSONResponse:
    """Fetch FKA and Interview question pools for a run."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import get_run
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse({
        "fka_pool": run.get("fka_questions_pool", {}),
        "interview_pool": run.get("interview_questions_pool", {})
    })

@app.post("/api/hr/run/{run_id}/questions", response_class=JSONResponse)
async def update_run_questions_endpoint(run_id: str, payload: QuestionPoolsPayload, request: Request) -> JSONResponse:
    """Update FKA and Interview question pools for a run."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import update_run_questions
    success = update_run_questions(run_id, payload.fka_pool, payload.interview_pool)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse({"ok": True})

@app.post("/api/hr/run/{run_id}/confirm", response_class=JSONResponse)
async def confirm_run_and_send_credentials(run_id: str, request: Request) -> JSONResponse:
    """Finalize the run (set status to 'confirmed') and send credentials to shortlisted candidates."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import set_run_status
    
    # Set run status to confirmed
    success = set_run_status(run_id, "confirmed")
    if not success:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Send credentials using existing auto_create_and_send logic
    try:
        from shared.credentials_automation import auto_create_and_send
        base_url = str(request.base_url).rstrip("/")
        result = auto_create_and_send(run_id, base_url=base_url)
        return JSONResponse({
            "ok": True,
            "created": result["created"],
            "skipped_no_email": result["skipped_no_email"],
            "errors": result.get("errors", []),
        })
    except Exception as e:
        import traceback
        detail = f"{type(e).__name__}: {str(e)}"
        print(f"ERROR in confirm_run_and_send_credentials: {detail}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": detail, "created": 0, "skipped_no_email": 0, "errors": [str(e)]},
        )


def _select_questions_from_pool(pool: dict, num_questions: int = 5) -> list:
    """Select questions from FKA pool, prioritizing must_ask questions and distributing across categories."""
    import random
    
    # 1. Start with MUST ASK questions (capped at num_questions)
    all_questions = []
    for qs in pool.values():
        if isinstance(qs, list):
            all_questions.extend(qs)
    
    must_ask = [q for q in all_questions if q.get("must_ask", False)]
    selected = must_ask[:num_questions]
    
    # 2. If we need more, try to hit a distribution: 1 Coding/Practical, 3 Concept, 1 Scenario
    # (Assuming the Order in pool keys or searching by name)
    if len(selected) < num_questions:
        remaining = num_questions - len(selected)
        
        # Identify categories (lowercase keys for easier matching)
        cats = {k.lower(): k for k in pool.keys()}
        
        # Target counts for categories
        # Category map: 'coding'/'practical' -> first cat, 'concept' -> second, 'scenario' -> third
        sorted_keys = sorted(pool.keys()) # Stable order
        
        # Helper to get available questions excluding already selected
        def get_available(cat_key):
            selected_ids = [s.get("id") for s in selected]
            return [q for q in pool.get(cat_key, []) if q.get("id") not in selected_ids]

        # Try to pick 1 from each category first to ensure diversity
        for cat in sorted_keys:
            if len(selected) >= num_questions: break
            avail = get_available(cat)
            if avail:
                random.shuffle(avail)
                selected.append(avail.pop(0))
        
        # Then fill remaining slots from ANY category (randomized)
        while len(selected) < num_questions:
            remaining_avail = []
            for cat in sorted_keys:
                remaining_avail.extend(get_available(cat))
            
            if not remaining_avail: break
            random.shuffle(remaining_avail)
            selected.append(remaining_avail.pop(0))
            
    # Final shuffle to ensure candidates don't get the same order
    random.shuffle(selected)
    return [q for q in selected if q.get("text")]


class DeleteCandidatePayload(BaseModel):
    candidate_id: str


class DeleteRunPayload(BaseModel):
    run_id: str


@app.delete("/api/hr/candidates/delete", response_class=JSONResponse)
@app.post("/api/hr/candidates/delete", response_class=JSONResponse)
async def api_hr_delete_candidate(request: Request, payload: DeleteCandidatePayload) -> JSONResponse:
    """Remove a candidate from the run. They will no longer appear in the dashboard or be able to log in."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import delete_candidate
    ok = delete_candidate(payload.candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return JSONResponse({"ok": True})


def _api_hr_delete_run_impl(payload: DeleteRunPayload) -> JSONResponse:
    from db.store import delete_run
    run_id = (payload.run_id or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required.")
    ok = delete_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found.")
    return JSONResponse({"ok": True})


@app.delete("/api/hr/runs/delete", response_class=JSONResponse)
@app.post("/api/hr/runs/delete", response_class=JSONResponse)
async def api_hr_delete_run(request: Request, payload: DeleteRunPayload) -> JSONResponse:
    """Remove a run and all its candidates. They will no longer appear in the dashboard."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    return _api_hr_delete_run_impl(payload)


@app.post("/api/hr/run/delete", response_class=JSONResponse)
async def api_hr_delete_run_alt(request: Request, payload: DeleteRunPayload) -> JSONResponse:
    """Alternate path for deleting a run (same as POST /api/hr/runs/delete)."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    return _api_hr_delete_run_impl(payload)


def _get_candidate_cv_row(candidate: dict, run: dict) -> Optional[dict]:
    """Load this candidate's row from run's high_scoring_excel or all_results_excel (Justification, Overall Fit, etc.)."""
    first = (candidate.get("first_name") or "").strip()
    last = (candidate.get("last_name") or "").strip()
    resume_link = (candidate.get("resume_link") or "").strip()

    def _row_matches(row) -> bool:
        rfirst = (str(row.get("First Name", "") or "")).strip()
        rlast = (str(row.get("Last Name", "") or "")).strip()
        if rfirst == first and rlast == last:
            return True
        rlink = (str(row.get("Resume Link", "") or "")).strip()
        if resume_link and rlink and (resume_link in rlink or rlink in resume_link or resume_link == rlink):
            return True
        if not first and not last and resume_link and rlink and resume_link == rlink:
            return True
        return False

    def _read_row(row, df) -> dict:
        out = {}
        if "Justification" in df.columns:
            j = row.get("Justification", "")
            out["justification"] = str(j).strip() if j is not None and str(j) != "nan" else ""
        if "Strengths" in df.columns:
            s = row.get("Strengths", "")
            out["strengths"] = str(s).strip() if s is not None and str(s) != "nan" else ""
        if "Weaknesses" in df.columns:
            w = row.get("Weaknesses", "")
            out["weaknesses"] = str(w).strip() if w is not None and str(w) != "nan" else ""
        if "Overall Fit" in df.columns:
            out["overall_fit"] = row.get("Overall Fit")
        if "Resume Link" in df.columns:
            out["resume_link"] = str(row.get("Resume Link", "") or "")
        return out

    for excel_key in ("high_scoring_excel", "all_results_excel"):
        excel_path = run.get(excel_key) or ""
        if not excel_path:
            continue
        path = Path(excel_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            continue
        try:
            import pandas as pd
            df = pd.read_excel(path)
            if "First Name" not in df.columns or "Last Name" not in df.columns:
                continue
            for _, row in df.iterrows():
                if _row_matches(row):
                    out = _read_row(row, df)
                    if out:
                        return out
        except Exception:
            pass
    return None


@app.get("/api/hr/candidate/{candidate_id}", response_class=JSONResponse)
async def api_hr_candidate_detail(request: Request, candidate_id: str) -> JSONResponse:
    """Return full candidate detail for HR dashboard: profile, run, CV justification, FKA score, status."""
    if not _hr_authenticated(request):
        raise HTTPException(status_code=401, detail="HR login required.")
    from db.store import get_overview
    data = get_overview()
    c, run = None, None
    for r in data.get("runs", []):
        for cand in r.get("candidates", []):
            if cand.get("id") == candidate_id:
                c, run = cand, r
                break
        if c is not None:
            break
    if not c or not run:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    cv_row = _get_candidate_cv_row(c, run)
    payload = {
        "candidate": {
            "id": c.get("id"),
            "first_name": c.get("first_name", ""),
            "last_name": c.get("last_name", ""),
            "email": c.get("email", ""),
            "status": c.get("status", "shortlisted"),
            "overall_fit": c.get("overall_fit"),
            "fka_score": c.get("fka_score"),
            "fka_strengths": c.get("fka_strengths"),
            "fka_weaknesses": c.get("fka_weaknesses"),
            "fka_justification": c.get("fka_justification"),
            "interview_report": c.get("interview_report"),
            "interview_evaluation_result": c.get("interview_evaluation_result"),
            "resume_link": c.get("resume_link", ""),
        },
        "run": {
            "run_id": run.get("run_id"),
            "jd_title": run.get("jd_title", ""),
            "timestamp": run.get("timestamp", ""),
            "total_resumes": run.get("total_resumes", 0),
        },
        "cv_stage": cv_row or {},
    }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/candidate/me", response_class=JSONResponse)
async def api_candidate_me(request: Request) -> JSONResponse:
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate
    info = get_candidate(cid)
    if not info:
        raise HTTPException(status_code=401, detail="Candidate not found.")
    return JSONResponse(info)


@app.post("/api/candidate/start_fka", response_class=JSONResponse)
async def api_candidate_start_fka(request: Request) -> JSONResponse:
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate, get_run, set_candidate_fka_session
    info = get_candidate(cid)
    if not info:
        raise HTTPException(status_code=401, detail="Candidate not found.")
    if fka_engine is None or fka_module is None:
        raise HTTPException(status_code=503, detail="FKA service not available.")

    # Try to get questions from the run's FKA pool
    selected_questions = None
    run = get_run(info.get("run_id", ""))
    if run:
        fka_pool = run.get("fka_questions_pool", {})
        if fka_pool:
            selected_questions = _select_questions_from_pool(fka_pool, num_questions=5)

    # Use JD from latest CV run, or fallback to FKA default path
    jd_filename = None
    jd_bytes = None
    for path in [
        CV_FILTER_LATEST_DIR / "Improved_Job_Description.pdf",
        ROOT_DIR / "cv_filtering" / "Job Descriptions" / "Front_End_Developer_General_JD.pdf",
    ]:
        if path.exists():
            try:
                jd_bytes = path.read_bytes()
                jd_filename = path.name
                break
            except Exception:
                continue
    if not jd_bytes and not selected_questions:
        raise HTTPException(
            status_code=400,
            detail="No job description available. Add a PDF to FKA_Web_Package/Job Descriptions/Front_End_Developer_General_JD.pdf or run HR Upload & Run first.",
        )
    try:
        session_id, session = fka_engine.init_session(
            jd_filename=jd_filename,
            jd_bytes=jd_bytes,
            candidate_name=f"{info.get('first_name', '')} {info.get('last_name', '')}".strip() or "Candidate",
            candidate_email=info.get("email"),
            questions=selected_questions,  # Pass pool questions (None falls back to generation)
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail="No job description available for FKA. HR should run CV filtering (Upload & Run) first so the improved JD is saved.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to init FKA session: {e}")
    set_candidate_fka_session(cid, session_id)
    return JSONResponse({
        "ok": True,
        "session_id": session_id,
        "fka_url": f"/fka/assessment?session_id={session_id}",
    })


@app.post("/api/candidate/fka_done", response_class=JSONResponse)
async def api_candidate_fka_done(request: Request) -> JSONResponse:
    """Deprecated: FKA result must be recorded with score via POST /api/candidate/fka_complete (pass/fail from threshold)."""
    raise HTTPException(
        status_code=400,
        detail="Use POST /api/candidate/fka_complete with JSON body { \"score\": <0-100> } to record FKA result. Pass/fail is determined by the configured threshold.",
    )


class FkaCompletePayload(BaseModel):
    score: int
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    justification: Optional[str] = None


@app.post("/api/candidate/fka_complete", response_class=JSONResponse)
async def api_candidate_fka_complete(request: Request, body: FkaCompletePayload) -> JSONResponse:
    """Record FKA completion with score: pass (fka_done) or fail (fka_failed) based on threshold. Optional: strengths, weaknesses, justification."""
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate, set_candidate_fka_complete, FKA_PASS_THRESHOLD
    from db.store import STATUS_SHORTLISTED, STATUS_FKA_STARTED
    me = get_candidate(cid)
    if not me:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    status = me.get("status", "")
    if status not in (STATUS_SHORTLISTED, STATUS_FKA_STARTED):
        raise HTTPException(
            status_code=400,
            detail="FKA can only be completed from shortlisted or fka_started. Current status: " + status,
        )
    score = max(0, min(100, getattr(body, "score", 0)))
    ok = set_candidate_fka_complete(
        cid,
        score,
        strengths=getattr(body, "strengths", None),
        weaknesses=getattr(body, "weaknesses", None),
        justification=getattr(body, "justification", None),
    )
    
    # Send email notification
    print(f"DEBUG: Attempting to send FKA result email to {me.get('email')}...")
    try:
        from shared.credentials_automation import send_fka_result_email
        email = me.get("email")
        if email:
            err = send_fka_result_email(
                to_email=email,
                first_name=me.get("first_name", ""),
                passed=score >= FKA_PASS_THRESHOLD,
                score=score
            )
            if err:
                print(f"DEBUG: Email send failed: {err}")
            else:
                print(f"DEBUG: Email sent successfully to {email}")
        else:
            print("DEBUG: No email found for candidate.")
    except Exception as e:
        import logging
        print(f"DEBUG: Exception sending email: {e}")
        logging.getLogger("uvicorn.error").warning(f"Failed to send FKA result email: {e}")

    return JSONResponse({"ok": ok, "passed": score >= FKA_PASS_THRESHOLD})


@app.post("/api/candidate/interview_started", response_class=JSONResponse)
async def api_candidate_interview_started(request: Request) -> JSONResponse:
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate, set_candidate_status
    from db.store import STATUS_FKA_DONE, STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE
    me = get_candidate(cid)
    if not me:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    status = me.get("status", "")
    if status not in (STATUS_FKA_DONE, STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE):
        raise HTTPException(
            status_code=403,
            detail="Complete the FKA and pass before starting the interview. Current status: " + status,
        )
    set_candidate_status(cid, STATUS_INTERVIEW_STARTED)
    return JSONResponse({"ok": True})


@app.post("/api/candidate/interview_done", response_class=JSONResponse)
async def api_candidate_interview_done(request: Request) -> JSONResponse:
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate, set_candidate_status
    from db.store import STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE
    me = get_candidate(cid)
    if not me:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    status = me.get("status", "")
    if status not in (STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE):
        raise HTTPException(
            status_code=400,
            detail="Start the interview before marking it done. Current status: " + status,
        )
    set_candidate_status(cid, STATUS_INTERVIEW_DONE)
    return JSONResponse({"ok": True})


# ----- Voice interview (real AI workflow) -----
_voice_interview_sessions: dict = {}  # candidate_id -> AgentState (in-memory)
_voice_workflow = None


def _get_voice_workflow():
    global _voice_workflow
    if _voice_workflow is None:
        from shared.src.dynamic_workflow import build_workflow
        _voice_workflow = build_workflow()
    return _voice_workflow


def _get_candidate_resume_text(candidate_id: str) -> str:
    """Load Full Resume from run's high_scoring_excel or all_results_excel. Fallback placeholder if not found."""
    from db.store import get_candidate, get_overview
    import pandas as pd
    me = get_candidate(candidate_id)
    if not me:
        return "This candidate has not provided a detailed resume."
    first = (me.get("first_name") or "").strip()
    last = (me.get("last_name") or "").strip()
    resume_link = (me.get("resume_link") or "").strip()
    run_id = me.get("run_id")
    overview = get_overview()
    for run in overview.get("runs", []):
        if run.get("run_id") != run_id:
            continue
        for excel_key in ("high_scoring_excel", "all_results_excel"):
            excel_path = run.get(excel_key) or ""
            if not excel_path:
                continue
            path = Path(excel_path)
            if not path.is_absolute():
                path = ROOT_DIR / path
            if not path.exists():
                continue
            try:
                df = pd.read_excel(path)
                if "First Name" not in df.columns or "Last Name" not in df.columns:
                    continue
                for _, row in df.iterrows():
                    rfirst = (str(row.get("First Name", "") or "").strip())
                    rlast = (str(row.get("Last Name", "") or "").strip())
                    rlink = (str(row.get("Resume Link", "") or "").strip())
                    match = (rfirst == first and rlast == last) or (resume_link and rlink and (resume_link == rlink or resume_link in rlink or rlink in resume_link))
                    if match:
                        full_resume = row.get("Full Resume", "") or ""
                        if full_resume and len(str(full_resume).strip()) >= 50:
                            return str(full_resume).strip()
                        break
            except Exception:
                pass
        break
    return "This candidate has not provided a detailed resume. Assume a general technical background."


@app.post("/api/interview/voice/start", response_class=JSONResponse)
async def api_interview_voice_start(request: Request) -> JSONResponse:
    """Start the voice interview: select questions from pool, init state, invoke workflow."""
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import get_candidate, get_run, set_candidate_status, STATUS_FKA_DONE, STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE
    me = get_candidate(cid)
    if not me:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    status = me.get("status", "")
    if status not in (STATUS_FKA_DONE, STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE):
        raise HTTPException(status_code=403, detail="Complete the FKA before the interview.")
    
    set_candidate_status(cid, STATUS_INTERVIEW_STARTED)
    resume_text = _get_candidate_resume_text(cid)
    position = me.get("jd_title") or "Technical Role"
    candidate_name = f"{me.get('first_name', '')} {me.get('last_name', '')}".strip() or "Candidate"
    
    # Select interview questions from pool
    run = get_run(me.get("run_id", ""))
    q_texts = []
    if run:
        pool = run.get("interview_questions_pool", {})
        if pool:
            selected_qs = _select_questions_from_pool(pool, num_questions=5)
            q_texts = [q.get("text", "") for q in selected_qs if q.get("text")]
    
    if not q_texts:
        # Fallback if no pool (though shouldn't happen with new flow)
        q_texts = ["What are your core strengths?", "Tell me about a difficult technical challenge you solved."]

    from langchain_core.messages import HumanMessage, AIMessage
    from shared.src.dynamic_workflow import AgentState
    
    workflow = _get_voice_workflow()
    state: AgentState = {
        "mode": "friendly",
        "num_of_q": len(q_texts),
        "num_of_follow_up": 1,
        "position": position,
        "company_name": "IntiqAI",
        "messages": [HumanMessage(content="[Interview Started]")],
        "evaluation_result": "",
        "report": "",
        "pdf_path": None,
        "resume_path": None,
        "questions_path": None,
        "resume_text": resume_text,
        "candidate_name": candidate_name,
        "interviewer_name": "Optimus Prime",
        "interview_questions": q_texts,
        "question_index": 0
    }
    try:
        result = workflow.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview start failed: {str(e)}")
    for k, v in result.items():
        state[k] = v
    _voice_interview_sessions[cid] = state
    if state.get("messages") and state["messages"][0].content == "[Interview Started]":
        state["messages"].pop(0)
    ai_text = ""
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage) and m.content:
            ai_text = (m.content if isinstance(m.content, str) else str(m.content)).strip()
            break
    if not ai_text:
        raise HTTPException(status_code=500, detail="No initial question from interview.")
    question_audio_b64 = None
    try:
        from interview_session import generate_tts
        audio_path, tts_err = generate_tts(ai_text, use_cache=True)
        if not tts_err and audio_path and Path(audio_path).exists():
            with open(audio_path, "rb") as f:
                question_audio_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pass
    return JSONResponse({
        "ok": True,
        "question_text": ai_text,
        "question_audio_base64": question_audio_b64,
        "done": False,
    })


@app.post("/api/interview/voice/answer", response_class=JSONResponse)
async def api_interview_voice_answer(request: Request, audio: UploadFile = File(None)) -> JSONResponse:
    """Submit voice answer: transcribe audio (or accept text), run workflow, return next question or done."""
    try:
        cid = _get_candidate_id(request)
        if not cid:
            return JSONResponse(status_code=401, content={"ok": False, "detail": "Candidate login required."})
        state = _voice_interview_sessions.get(cid)
        if not state:
            return JSONResponse(status_code=400, content={"ok": False, "detail": "Start the interview first."})
        from langchain_core.messages import HumanMessage, AIMessage
        from db.store import set_candidate_status, STATUS_INTERVIEW_DONE
        user_text = None
        if audio and audio.filename:
            ext = os.path.splitext(audio.filename or "")[1] or ".webm"
            if ext.lower() not in (".wav", ".webm", ".mp3", ".m4a", ".ogg"):
                ext = ".webm"
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            try:
                tmp.write(await audio.read())
                tmp.close()
                from interview_session import transcribe_audio
                user_text, err = transcribe_audio(tmp.name, max_wait=180)
                if err or not user_text or len(user_text.strip()) < 2:
                    detail = err or "Could not transcribe audio. Try again."
                    if not user_text and not err:
                        detail = "Recording too short or no speech detected. Try again."
                    return JSONResponse(status_code=400, content={"ok": False, "detail": detail})
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
        else:
            body = await request.body()
            if body:
                try:
                    import json as _json
                    data = _json.loads(body)
                    user_text = (data.get("text") or data.get("answer") or "").strip()
                except Exception:
                    pass
            if not user_text:
                return JSONResponse(status_code=400, content={"ok": False, "detail": "Provide an audio file or JSON body with 'text'."})
        state["messages"].append(HumanMessage(content=user_text.strip()))
        workflow = _get_voice_workflow()
        try:
            result = workflow.invoke(state)
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "detail": f"Interview step failed: {str(e)}"})
        for k, v in result.items():
            state[k] = v
        _voice_interview_sessions[cid] = state
        done = False
        end_phrases = ("that's it for today", "thank you, that's it", "we're done", "interview is complete", "that concludes the interview")
        for m in reversed(state.get("messages", [])):
            if isinstance(m, AIMessage) and m.content:
                s = (m.content if isinstance(m.content, str) else str(m.content)).lower()
                for phrase in end_phrases:
                    if phrase in s:
                        done = True
                        break
                break
        ai_text = ""
        for m in reversed(state.get("messages", [])):
            if isinstance(m, AIMessage) and m.content:
                ai_text = (m.content if isinstance(m.content, str) else str(m.content)).strip()
                break
        question_audio_b64 = None
        if ai_text and not done:
            try:
                from interview_session import generate_tts
                audio_path, _ = generate_tts(ai_text, use_cache=True)
                if audio_path and Path(audio_path).exists():
                    with open(audio_path, "rb") as f:
                        question_audio_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        if done:
            set_candidate_status(cid, STATUS_INTERVIEW_DONE)
            try:
                from db.store import set_candidate_interview_report
                from shared.src.dynamic_workflow import evaluator, report_writer
                eval_out = evaluator(state)
                if eval_out:
                    for k, v in eval_out.items():
                        state[k] = v
                report_out = report_writer(state) if state.get("evaluation_result") else {}
                if report_out:
                    for k, v in report_out.items():
                        state[k] = v
                set_candidate_interview_report(
                    cid,
                    report=state.get("report") or "",
                    evaluation_result=state.get("evaluation_result") or "",
                )
            except Exception as e:
                pass
        return JSONResponse({
            "ok": True,
            "question_text": ai_text,
            "question_audio_base64": question_audio_b64,
            "done": done,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})


@app.get("/api/interview/questions", response_class=JSONResponse)
async def api_interview_questions() -> JSONResponse:
    """Return the list of interview questions for the candidate GUI."""
    from db.store import get_interview_questions
    return JSONResponse({"questions": get_interview_questions()})


class InterviewSubmitPayload(BaseModel):
    answers: list


@app.post("/api/interview/submit", response_class=JSONResponse)
async def api_interview_submit(request: Request, body: InterviewSubmitPayload) -> JSONResponse:
    """Submit interview answers; marks candidate as interview_done and stores answers."""
    cid = _get_candidate_id(request)
    if not cid:
        raise HTTPException(status_code=401, detail="Candidate login required.")
    from db.store import (
        get_interview_questions,
        set_candidate_interview_complete,
        STATUS_FKA_DONE,
        STATUS_INTERVIEW_STARTED,
        STATUS_INTERVIEW_DONE,
    )
    from db.store import get_candidate
    me = get_candidate(cid)
    if not me:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    status = me.get("status", "")
    if status not in (STATUS_FKA_DONE, STATUS_INTERVIEW_STARTED, STATUS_INTERVIEW_DONE):
        raise HTTPException(status_code=403, detail="You must complete the FKA before the interview.")
    questions_by_id = {q["id"]: q["text"] for q in get_interview_questions()}
    normalized = []
    for item in body.answers or []:
        qid = item.get("question_id") if isinstance(item, dict) else getattr(item, "question_id", None)
        ans = item.get("answer") if isinstance(item, dict) else getattr(item, "answer", "") or ""
        if not qid:
            continue
        text = questions_by_id.get(qid, "")
        normalized.append({"question_id": qid, "question_text": text, "answer": str(ans).strip()})
    ok = set_candidate_interview_complete(cid, normalized)
    return JSONResponse({"ok": ok})


class CVFilterRequest(BaseModel):
    resumes_dir: str
    jd_path: str
    model: Optional[str] = "llama-3.1-8b-instant"
    temperature: Optional[float] = 0.2


@app.post("/api/cv_filter/run")
async def run_cv_filter(req: CVFilterRequest) -> JSONResponse:
    """
    Run the CV filtering pipeline using the same logic as the Streamlit app.
    """
    # Late imports to avoid slow startup if not used
    from cv_filtering import (  # type: ignore
        Config,
        HIGH_SCORE_THRESHOLD_DEFAULT,
        JD_FIX_PROMPT,
        evaluate_single_resume,
        llm_json,
        make_llm,
        normalize_improved_jd,
        read_pdf_text_from_path,
        clean_whitespace,
        ensure_dir,
        results_to_dataframe,
        save_excels,
        save_jd_pdf,
        extract_position_from_jd,
    )

    resumes_dir = os.path.expandvars(os.path.expanduser(req.resumes_dir))
    jd_path = os.path.expandvars(os.path.expanduser(req.jd_path))

    if not os.path.isdir(resumes_dir):
        raise HTTPException(status_code=400, detail=f"Resumes directory not found: {resumes_dir}")
    if not os.path.isfile(jd_path):
        raise HTTPException(status_code=400, detail=f"JD file not found: {jd_path}")

    # Read and clean JD text
    try:
        jd_text_raw = read_pdf_text_from_path(jd_path)
        jd_text = clean_whitespace(jd_text_raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read JD PDF: {e}")

    out_dir = os.path.join(os.getcwd(), "Filtered Resumes")
    improved_jd_dir = os.path.join(os.getcwd(), "Improved Job Descriptions")
    ensure_dir(out_dir)
    ensure_dir(improved_jd_dir)

    cfg = Config(
        jd_text=jd_text,
        resumes_dir=resumes_dir,
        out_dir=out_dir,
        Improved_JD_dir=improved_jd_dir,
        model=req.model or "llama-3.1-8b-instant",
        temperature=req.temperature or 0.2,
        high_score_threshold=HIGH_SCORE_THRESHOLD_DEFAULT,
    )

    try:
        llm = make_llm(cfg)

        # Improve JD
        jd_fix_result = llm_json(llm, JD_FIX_PROMPT, jd_text=cfg.jd_text)
        raw_improved = jd_fix_result.get("improved_job_description", "")
        fixed_jd = normalize_improved_jd(raw_improved)

        must_haves = jd_fix_result.get("must_have_requirements", []) or []
        nice_haves = jd_fix_result.get("nice_to_have_requirements", []) or []
        if isinstance(must_haves, str):
            must_haves = [x.strip("-• \t") for x in must_haves.splitlines() if x.strip()]
        if isinstance(nice_haves, str):
            nice_haves = [x.strip("-• \t") for x in nice_haves.splitlines() if x.strip()]

        # Extract position (not currently returned)
        _ = extract_position_from_jd(llm, fixed_jd)

        # Save improved JD PDF
        improved_jd_pdf_path = save_jd_pdf(fixed_jd, must_haves, nice_haves, cfg.Improved_JD_dir)

        # Load resumes (search recursively to handle nested folders from webkitdirectory)
        pdf_paths = []
        for root, _, files in os.walk(cfg.resumes_dir):
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    pdf_paths.append(os.path.join(root, fname))

        if not pdf_paths:
            raise HTTPException(status_code=400, detail=f"No PDF files found in {cfg.resumes_dir}")

        resumes = []
        for path in sorted(pdf_paths):
            fname = os.path.basename(path)
            text = clean_whitespace(read_pdf_text_from_path(path))
            resumes.append({"name": fname, "path": path, "text": text})

        uploaded_resumes = [{"name": r["name"], "text": r["text"], "link": r["name"]} for r in resumes]

        # Evaluate resumes
        results = []

        def process_item(item):
            return evaluate_single_resume(llm, fixed_jd, must_haves, nice_haves, item["text"], item["link"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(process_item, item): item for item in uploaded_resumes}
            for f in as_completed(futures):
                results.append(f.result())

        # Save Excel results
        df = results_to_dataframe(results)
        all_path, high_path = save_excels(df, cfg.out_dir, cfg.high_score_threshold)

        return JSONResponse(
            {
                "status": "ok",
                "resumes_dir": resumes_dir,
                "jd_path": jd_path,
                "total_resumes": len(resumes),
                "improved_jd_pdf": improved_jd_pdf_path,
                "all_results_excel": all_path,
                "high_scoring_excel": high_path,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV filtering failed: {e}")


from fastapi import UploadFile, File
from tempfile import mkdtemp
import shutil


@app.post("/api/cv_filter/upload-run")
async def run_cv_filter_from_upload(
    cvs: list[UploadFile] = File(...),
    jd: UploadFile = File(...),
) -> JSONResponse:
    """
    Accept uploaded CV PDFs and a JD PDF, then run CV filtering WITHOUT relying
    on any directory scanning. We work directly from the uploaded files.
    """
    if not cvs:
        raise HTTPException(status_code=400, detail="No CV files received in upload.")

    # Late-import heavy deps
    from cv_filtering.cv_filtering import (  # type: ignore
        Config,
        HIGH_SCORE_THRESHOLD_DEFAULT,
        JD_FIX_PROMPT,
        evaluate_single_resume,
        llm_json,
        make_llm,
        normalize_improved_jd,
        read_pdf_text_from_path,
        clean_whitespace,
        ensure_dir,
        results_to_dataframe,
        save_excels,
        save_jd_pdf,
        extract_position_from_jd,
    )

    # Temp workspace for this run
    tmp_dir = mkdtemp(prefix="cv_upload_")
    out_dir = os.path.join(tmp_dir, "Filtered Resumes")
    improved_jd_dir = os.path.join(tmp_dir, "Improved Job Descriptions")
    ensure_dir(out_dir)
    ensure_dir(improved_jd_dir)

    # Save JD to a temp file
    jd_path = os.path.join(tmp_dir, jd.filename or "job_description.pdf")
    with open(jd_path, "wb") as f_jd:
        shutil.copyfileobj(jd.file, f_jd)

    # Save each uploaded CV to its own temp file
    cv_paths: list[str] = []
    for idx, cv in enumerate(cvs):
        if not (cv.filename or "").lower().endswith(".pdf"):
            continue
        safe_name = cv.filename or f"resume_{idx}.pdf"
        cv_path = os.path.join(tmp_dir, safe_name)
        # Handle webkitdirectory-style names like "Folder/file.pdf"
        os.makedirs(os.path.dirname(cv_path), exist_ok=True)
        with open(cv_path, "wb") as f_cv:
            shutil.copyfileobj(cv.file, f_cv)
        cv_paths.append(cv_path)

    if not cv_paths:
        raise HTTPException(
            status_code=400,
            detail="No PDF files were saved from the uploaded CVs.",
        )

    # ----- Run the same pipeline logic as the Streamlit app -----
    try:
        # Read and clean JD
        jd_text_raw = read_pdf_text_from_path(jd_path)
        jd_text = clean_whitespace(jd_text_raw)

        cfg = Config(
            jd_text=jd_text,
            resumes_dir=tmp_dir,  # not used for scanning in this variant
            out_dir=out_dir,
            Improved_JD_dir=improved_jd_dir,
            model="llama-3.1-8b-instant",
            temperature=0.2,
            high_score_threshold=HIGH_SCORE_THRESHOLD_DEFAULT,
        )

        llm = make_llm(cfg)

        # Improve JD
        jd_fix_result = llm_json(llm, JD_FIX_PROMPT, jd_text=cfg.jd_text)
        raw_improved = jd_fix_result.get("improved_job_description", "")
        fixed_jd = normalize_improved_jd(raw_improved)

        must_haves = jd_fix_result.get("must_have_requirements", []) or []
        nice_haves = jd_fix_result.get("nice_to_have_requirements", []) or []
        if isinstance(must_haves, str):
            must_haves = [x.strip("-• \t") for x in must_haves.splitlines() if x.strip()]
        if isinstance(nice_haves, str):
            nice_haves = [x.strip("-• \t") for x in nice_haves.splitlines() if x.strip()]

        _ = extract_position_from_jd(llm, fixed_jd)

        improved_jd_pdf_path = save_jd_pdf(
            fixed_jd, must_haves, nice_haves, cfg.Improved_JD_dir
        )

        # Read each uploaded CV and build resume objects
        resumes = []
        for path in cv_paths:
            fname = os.path.basename(path)
            text = clean_whitespace(read_pdf_text_from_path(path))
            resumes.append({"name": fname, "path": path, "text": text})

        uploaded_resumes = [
            {"name": r["name"], "text": r["text"], "link": r["name"]} for r in resumes
        ]

        # Evaluate resumes
        results = []

        def process_item(item):
            return evaluate_single_resume(
                llm, fixed_jd, must_haves, nice_haves, item["text"], item["link"]
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(process_item, item): item for item in uploaded_resumes}
            for f in as_completed(futures):
                results.append(f.result())

        df = results_to_dataframe(results)
        all_path, high_path = save_excels(df, cfg.out_dir, cfg.high_score_threshold)

        # Copy results to a stable directory so the dashboard can always load them
        # (temp dir may be cleaned up; dashboard reads from latest_cv_run.json paths)
        CV_FILTER_LATEST_DIR.mkdir(parents=True, exist_ok=True)
        stable_all = CV_FILTER_LATEST_DIR / "Resume_Screening_Results.xlsx"
        stable_high = CV_FILTER_LATEST_DIR / "High_Scoring_Candidates.xlsx"
        stable_jd = CV_FILTER_LATEST_DIR / "Improved_Job_Description.pdf"
        shutil.copy2(all_path, stable_all)
        shutil.copy2(high_path, stable_high)
        if improved_jd_pdf_path and os.path.isfile(improved_jd_pdf_path):
            shutil.copy2(improved_jd_pdf_path, stable_jd)

        # Persist latest run metadata with stable paths so the dashboard can hydrate
        jd_title = extract_position_from_jd(llm, fixed_jd)
        meta = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_resumes": len(resumes),
            "jd_title": jd_title,
            "jd_preview": fixed_jd[:500],
            "all_results_excel": str(stable_all),
            "high_scoring_excel": str(stable_high),
        }
        try:
            LATEST_RUN_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass

        # Generate Question Pools for the Run
        fka_pool = {}
        interview_pool = {}
        if fka_engine and fka_engine.question_generator:
            try:
                # print(f"Generating question pools for {jd_title}...")
                fka_pool = fka_engine.question_generator.generate_fka_pool(jd_title, fixed_jd)
                interview_pool = fka_engine.question_generator.generate_interview_pool(jd_title, fixed_jd)
            except Exception as e:
                print(f"Error generating pools: {e}")

        # Register run and candidates in store: ALL candidates from full results,
        # with status shortlisted (in high-scoring file) or disqualified (below CV threshold)
        try:
            from cv_filtering.cv_filtering import load_candidates_from_excel, sort_candidates
            from db.store import create_run, STATUS_SHORTLISTED, STATUS_DISQUALIFIED
            df_all = load_candidates_from_excel(str(stable_all))
            if df_all is not None and len(df_all) > 0:
                shortlisted_links = set()
                if stable_high.exists():
                    df_high = load_candidates_from_excel(str(stable_high))
                    if df_high is not None and len(df_high) > 0 and "Resume Link" in df_high.columns:
                        shortlisted_links = set(df_high["Resume Link"].fillna("").astype(str).str.strip())
                df_all = sort_candidates(df_all)
                rows = df_all.to_dict(orient="records")
                for r in rows:
                    link = str(r.get("Resume Link") or "").strip()
                    r["status"] = STATUS_SHORTLISTED if link in shortlisted_links else STATUS_DISQUALIFIED
                
                # Create run with question pools
                run_id = create_run(meta, rows, fka_questions_pool=fka_pool, interview_questions_pool=interview_pool)
                meta["run_id"] = run_id
        except Exception:
            pass

        return JSONResponse(meta)
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        # Rate limit or quota (Groq; legacy Gemini wording may appear in wrapped errors)
        if (
            "ResourceExhausted" in err_msg or "RetryError" in err_msg
            or "rate" in err_msg.lower() or "quota" in err_msg.lower()
            or "Gemini" in err_msg or "rate limit" in err_msg.lower()
        ):
            raise HTTPException(
                status_code=429,
                detail=(
                    "LLM rate limit or quota exceeded (Groq). "
                    "Try again in a few minutes, or use fewer CVs in one run."
                ),
            )
        raise HTTPException(status_code=500, detail=f"CV filtering failed: {e}")


@app.get("/api/cv_filter/latest")
async def latest_cv_run() -> JSONResponse:
    """Return metadata about the latest CV filtering run for the HR dashboard."""
    if not LATEST_RUN_PATH.exists():
        raise HTTPException(status_code=404, detail="No CV filtering run found.")
    try:
        data = json.loads(LATEST_RUN_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read latest run: {e}")
    return JSONResponse(
        data,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/api/cv_filter/candidates")
async def latest_candidates(limit: int = 5) -> JSONResponse:
    """Return top candidates from the latest run (high-scoring first, else all results)."""
    if not LATEST_RUN_PATH.exists():
        raise HTTPException(status_code=404, detail="No CV filtering run found.")
    meta = json.loads(LATEST_RUN_PATH.read_text(encoding="utf-8"))

    from cv_filtering import load_candidates_from_excel, sort_candidates  # type: ignore

    # Prefer high-scoring file; if missing or empty, fall back to all results so dashboard always shows something
    high_excel = meta.get("high_scoring_excel")
    all_excel = meta.get("all_results_excel")
    df = None
    if high_excel and os.path.isfile(high_excel):
        df = load_candidates_from_excel(high_excel)
    if df is None or len(df) == 0:
        if all_excel and os.path.isfile(all_excel):
            df = load_candidates_from_excel(all_excel)
    if df is None:
        raise HTTPException(status_code=404, detail="No candidate data found for latest run.")
    if len(df) == 0:
        return JSONResponse({"candidates": []})

    df = sort_candidates(df)
    rows = df.head(limit).to_dict(orient="records")
    # Sanitize NaN/Inf floats and numpy/datetime so JSON serialization never fails
    rows = _json_safe(rows)
    return JSONResponse(
        {"candidates": rows},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/api/cv_filter/download/{filename}")
async def download_cv_file(filename: str):
    """
    Download Excel or PDF files from the latest CV filtering run.
    Allowed filenames:
      - Resume_Screening_Results.xlsx
      - High_Scoring_Candidates.xlsx
      - Improved_Job_Description.pdf
    """
    allowed_files = {
        "Resume_Screening_Results.xlsx",
        "High_Scoring_Candidates.xlsx",
        "Improved_Job_Description.pdf",
    }
    if filename not in allowed_files:
        raise HTTPException(status_code=400, detail="Invalid filename requested.")

    # Files are stored in CV_FILTER_LATEST_DIR
    file_path = CV_FILTER_LATEST_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found. Run a CV filtering job first.")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )





@app.post("/api/cv_filter/jd_preview")
async def jd_preview(jd: UploadFile = File(...)) -> JSONResponse:
    """Return a short text preview of the uploaded JD PDF."""
    from cv_filtering import read_pdf_text_from_path, clean_whitespace  # type: ignore
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(jd.file, tmp)
        tmp_path = tmp.name

    try:
        raw = read_pdf_text_from_path(tmp_path)
        text = clean_whitespace(raw)
        preview = text[:500]
        return JSONResponse({"preview": preview})
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


class CVFilterRequest(BaseModel):
    resumes_dir: str
    jd_path: str
    model: Optional[str] = "llama-3.1-8b-instant"
    temperature: Optional[float] = 0.2


@app.post("/api/cv_filter/run")
async def run_cv_filter(req: CVFilterRequest) -> JSONResponse:
    """
    Run the CV filtering pipeline using the same logic as the Streamlit app.
    """
    # Late imports to avoid slow startup if not used
    from cv_filtering import (  # type: ignore
        Config,
        HIGH_SCORE_THRESHOLD_DEFAULT,
        JD_FIX_PROMPT,
        evaluate_single_resume,
        llm_json,
        make_llm,
        normalize_improved_jd,
        read_pdf_text_from_path,
        clean_whitespace,
        ensure_dir,
        results_to_dataframe,
        save_excels,
        save_jd_pdf,
        extract_position_from_jd,
    )

    resumes_dir = os.path.expandvars(os.path.expanduser(req.resumes_dir))
    jd_path = os.path.expandvars(os.path.expanduser(req.jd_path))

    if not os.path.isdir(resumes_dir):
        raise HTTPException(status_code=400, detail=f"Resumes directory not found: {resumes_dir}")
    if not os.path.isfile(jd_path):
        raise HTTPException(status_code=400, detail=f"JD file not found: {jd_path}")

    # Read and clean JD text
    try:
        jd_text_raw = read_pdf_text_from_path(jd_path)
        jd_text = clean_whitespace(jd_text_raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read JD PDF: {e}")

    out_dir = os.path.join(os.getcwd(), "Filtered Resumes")
    improved_jd_dir = os.path.join(os.getcwd(), "Improved Job Descriptions")
    ensure_dir(out_dir)
    ensure_dir(improved_jd_dir)

    cfg = Config(
        jd_text=jd_text,
        resumes_dir=resumes_dir,
        out_dir=out_dir,
        Improved_JD_dir=improved_jd_dir,
        model=req.model or "llama-3.1-8b-instant",
        temperature=req.temperature or 0.2,
        high_score_threshold=HIGH_SCORE_THRESHOLD_DEFAULT,
    )

    try:
        llm = make_llm(cfg)

        # Improve JD
        jd_fix_result = llm_json(llm, JD_FIX_PROMPT, jd_text=cfg.jd_text)
        raw_improved = jd_fix_result.get("improved_job_description", "")
        fixed_jd = normalize_improved_jd(raw_improved)

        must_haves = jd_fix_result.get("must_have_requirements", []) or []
        nice_haves = jd_fix_result.get("nice_to_have_requirements", []) or []
        if isinstance(must_haves, str):
            must_haves = [x.strip("-• \t") for x in must_haves.splitlines() if x.strip()]
        if isinstance(nice_haves, str):
            nice_haves = [x.strip("-• \t") for x in nice_haves.splitlines() if x.strip()]

        # Extract position (not currently returned)
        _ = extract_position_from_jd(llm, fixed_jd)

        # Save improved JD PDF
        improved_jd_pdf_path = save_jd_pdf(fixed_jd, must_haves, nice_haves, cfg.Improved_JD_dir)

        # Load resumes
        pdf_files = [f for f in os.listdir(cfg.resumes_dir) if f.lower().endswith(".pdf")]
        if not pdf_files:
            raise HTTPException(status_code=400, detail=f"No PDF files found in {cfg.resumes_dir}")

        resumes = []
        for fname in sorted(pdf_files):
            path = os.path.join(cfg.resumes_dir, fname)
            text = clean_whitespace(read_pdf_text_from_path(path))
            resumes.append({"name": fname, "path": path, "text": text})

        uploaded_resumes = [{"name": r["name"], "text": r["text"], "link": r["name"]} for r in resumes]

        # Evaluate resumes
        results = []

        def process_item(item):
            return evaluate_single_resume(llm, fixed_jd, must_haves, nice_haves, item["text"], item["link"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(process_item, item): item for item in uploaded_resumes}
            for f in as_completed(futures):
                results.append(f.result())

        # Save Excel results
        df = results_to_dataframe(results)
        all_path, high_path = save_excels(df, cfg.out_dir, cfg.high_score_threshold)

        return JSONResponse(
            {
                "status": "ok",
                "resumes_dir": resumes_dir,
                "jd_path": jd_path,
                "total_resumes": len(resumes),
                "improved_jd_pdf": improved_jd_pdf_path,
                "all_results_excel": all_path,
                "high_scoring_excel": high_path,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV filtering failed: {e}")

