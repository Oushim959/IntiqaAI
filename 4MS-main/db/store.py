"""
Simple JSON file store for IntiqAI: runs, candidates, and HR auth.
All state is persisted to a single file so HR overview and candidate login stay in sync.
"""
import json
import os
import secrets
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = BASE_DIR / "intiqai_store.json"

# Admin credentials
ADMIN_EMAIL = "intiqaia4@gmail.com"
ADMIN_PASSWORD = "IntiqAI2026"

# -----------------------------------------------------------------------------
# Phase flow and thresholds (applied consistently in API and CV filtering)
# -----------------------------------------------------------------------------
# 1) CV screening: Overall Fit (1-10) >= HIGH_SCORE_THRESHOLD (in cv_filtering;
#    default 8) and no missing MUST-HAVEs -> shortlisted and added to run.
# 2) FKA: score (0-100) >= FKA_PASS_THRESHOLD (60) -> fka_done; else fka_failed.
# 3) Interview: only allowed after fka_done.
# -----------------------------------------------------------------------------
# Candidate status flow: shortlisted -> fka_started -> fka_done | fka_failed -> interview_started -> interview_done
# Or: disqualified at any time
STATUS_SHORTLISTED = "shortlisted"
STATUS_FKA_STARTED = "fka_started"
STATUS_FKA_DONE = "fka_done"
STATUS_FKA_FAILED = "fka_failed"
STATUS_INTERVIEW_STARTED = "interview_started"
STATUS_INTERVIEW_DONE = "interview_done"
STATUS_DISQUALIFIED = "disqualified"

# Minimum FKA score (0-100) to allow interview; below this candidate gets fka_failed
FKA_PASS_THRESHOLD = 60


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"runs": [], "hr_sessions": {}}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Migrate legacy "qualified" -> "shortlisted"
        for run in data.get("runs", []):
            for c in run.get("candidates", []):
                if c.get("status") == "qualified":
                    c["status"] = "shortlisted"
        return data
    except Exception:
        return {"runs": [], "hr_sessions": {}}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _find_run(data: dict, run_id: str) -> Optional[dict]:
    for r in data.get("runs", []):
        if r.get("run_id") == run_id:
            return r
    return None


def _find_candidate_in_runs(data: dict, candidate_id: str) -> tuple[Optional[dict], Optional[dict]]:
    for run in data.get("runs", []):
        for c in run.get("candidates", []):
            if c.get("id") == candidate_id:
                return c, run
    return None, None


def create_run(meta: dict, candidate_rows: List[dict], fka_questions_pool: dict = None, interview_questions_pool: dict = None) -> str:
    """Create a new run and candidates from CV filter results. Returns run_id.
    Each row may include 'status' (shortlisted | disqualified) for CV screening; default shortlisted."""
    data = _load()
    run_id = uuid.uuid4().hex[:12]
    candidates = []
    for i, row in enumerate(candidate_rows):
        first = (row.get("First Name") or "") if isinstance(row.get("First Name"), str) else ""
        last = (row.get("Last Name") or "") if isinstance(row.get("Last Name"), str) else ""
        if not first and not last:
            # Fallback for UI if name extraction failed: use "Candidate X" instead of raw filename
            first = f"Candidate {i+1}"
            last = ""
        name = f"{first} {last}".strip()
        email_raw = row.get("Email") or row.get("Email Address") or ""
        email = (email_raw.strip() if isinstance(email_raw, str) else "") or ""
        status = row.get("status")
        if status not in (STATUS_SHORTLISTED, STATUS_DISQUALIFIED):
            status = STATUS_SHORTLISTED
        candidates.append({
            "id": uuid.uuid4().hex[:10],
            "resume_link": row.get("Resume Link") or "",
            "first_name": first,
            "last_name": last,
            "overall_fit": row.get("Overall Fit"),
            "email": email,
            "password": "",
            "status": status,
            "fka_questions": [], 
            "interview_questions": [],
            "fka_session_id": None,
            "fka_score": None,
            "interview_feedback": None
        })

    new_run = {
        "run_id": run_id,
        "timestamp": meta.get("timestamp"),
        "jd_title": meta.get("jd_title"),
        "total_resumes": meta.get("total_resumes"),
        "improved_jd_pdf": meta.get("improved_jd_pdf"),
        "all_results_excel": meta.get("all_results_excel"),
        "high_scoring_excel": meta.get("high_scoring_excel"),
        "fka_questions_pool": fka_questions_pool or {},
        "interview_questions_pool": interview_questions_pool or {},
        "status": "pending_review", # New status for HR review
        "candidates": candidates
    }
    data["runs"].insert(0, new_run)
    _save(data)
    return run_id



def get_overview() -> dict:
    """Return all runs with candidates for HR overview."""
    data = _load()
    return {"runs": data.get("runs", [])}

def get_run(run_id: str) -> Optional[dict]:
    """Get a specific run by ID."""
    data = _load()
    return _find_run(data, run_id)

def update_run_questions(run_id: str, fka_pool: dict, interview_pool: dict) -> bool:
    """Update question pools for a run."""
    data = _load()
    run = _find_run(data, run_id)
    if not run:
        return False
    run["fka_questions_pool"] = fka_pool
    run["interview_questions_pool"] = interview_pool
    _save(data)
    return True

def set_run_status(run_id: str, status: str) -> bool:
    """Update status of a run."""
    data = _load()
    run = _find_run(data, run_id)
    if not run:
        return False
    run["status"] = status
    _save(data)
    return True


def set_candidate_credentials(run_id: str, credentials: List[dict]) -> None:
    """Set email and password for candidates. credentials: [{ candidate_id, email, password }, ...]"""
    data = _load()
    run = _find_run(data, run_id)
    if not run:
        raise ValueError("Run not found")
    by_id = {c["id"]: c for c in run.get("candidates", [])}
    for item in credentials:
        cid = item.get("candidate_id")
        if not cid or cid not in by_id:
            continue
        if item.get("email"):
            by_id[cid]["email"] = str(item["email"]).strip()
        if item.get("password"):
            by_id[cid]["password"] = str(item["password"])
    _save(data)


def delete_run(run_id: str) -> bool:
    """Remove a run and all its candidates. They will no longer appear in the dashboard. Returns True if removed."""
    data = _load()
    runs = data.get("runs", [])
    for i, r in enumerate(runs):
        if r.get("run_id") == run_id:
            runs.pop(i)
            _save(data)
            return True
    return False


def delete_candidate(candidate_id: str) -> bool:
    """Remove a candidate from their run. They will no longer appear in the dashboard or be able to log in. Returns True if removed."""
    data = _load()
    for run in data.get("runs", []):
        candidates = run.get("candidates", [])
        for i, c in enumerate(candidates):
            if c.get("id") == candidate_id:
                candidates.pop(i)
                _save(data)
                return True
    return False


def candidate_login(email: str, password: str) -> Optional[dict]:
    """Validate candidate email/password; return candidate + run info or None."""
    data = _load()
    email = (email or "").strip().lower()
    password = (password or "").strip()
    for run in data.get("runs", []):
        for c in run.get("candidates", []):
            if c.get("email", "").strip().lower() == email:
                # Found email match, check password and status
                stored_pass = c.get("password", "").strip()
                status = c.get("status")
                print(f"DEBUG: Login attempt for {email}. Status: {status}")
                
                if stored_pass != password:
                    print(f"DEBUG: Password mismatch for {email}")
                    continue
                
                if status == STATUS_DISQUALIFIED:
                    print(f"DEBUG: Candidate {email} is disqualified.")
                    continue
                    
                return {
                    "candidate_id": c["id"],
                    "run_id": run["run_id"],
                    "status": c.get("status", STATUS_SHORTLISTED),
                    "first_name": c.get("first_name", ""),
                    "last_name": c.get("last_name", ""),
                }
    print(f"DEBUG: Login failed - email {email} not found.")
    return None


def get_candidate(candidate_id: str) -> Optional[dict]:
    """Get candidate by id with run info."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c or not run:
        return None
    return {
        **c,
        "run_id": run.get("run_id"),
        "jd_title": run.get("jd_title", ""),
    }


def set_candidate_status(candidate_id: str, status: str, fka_session_id: Optional[str] = None) -> bool:
    """Update candidate status. Returns True if updated."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        return False
    c["status"] = status
    if fka_session_id is not None:
        c["fka_session_id"] = fka_session_id
    _save(data)
    return True


def set_candidate_fka_session(candidate_id: str, fka_session_id: str) -> bool:
    """Store FKA session id for candidate."""
    return set_candidate_status(candidate_id, STATUS_FKA_STARTED, fka_session_id)


def set_candidate_fka_complete(
    candidate_id: str,
    score: int,
    strengths: Optional[List[str]] = None,
    weaknesses: Optional[List[str]] = None,
    justification: Optional[str] = None,
) -> bool:
    """Set FKA complete: fka_done if score >= threshold, else fka_failed. Stores fka_score and optional evaluation details."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        return False
    status = STATUS_FKA_DONE if score >= FKA_PASS_THRESHOLD else STATUS_FKA_FAILED
    c["status"] = status
    c["fka_score"] = max(0, min(100, score))
    if strengths is not None:
        c["fka_strengths"] = list(strengths) if isinstance(strengths, (list, tuple)) else []
    if weaknesses is not None:
        c["fka_weaknesses"] = list(weaknesses) if isinstance(weaknesses, (list, tuple)) else []
    if justification is not None:
        c["fka_justification"] = str(justification).strip() if justification else ""
    _save(data)
    return True


# Default interview questions (id, text)
INTERVIEW_QUESTIONS = [
    {"id": "q1", "text": "Tell us about a technical challenge you solved recently. What was your approach and outcome?"},
    {"id": "q2", "text": "How do you prioritize tasks when working under a tight deadline?"},
    {"id": "q3", "text": "Describe a time you had to learn something new quickly. How did you go about it?"},
    {"id": "q4", "text": "What interests you most about this role and our company?"},
    {"id": "q5", "text": "Is there anything you would like to add or any question for us?"},
]


def get_interview_questions() -> List[dict]:
    """Return the list of interview questions for the GUI."""
    return list(INTERVIEW_QUESTIONS)


def set_candidate_interview_complete(candidate_id: str, answers: List[dict]) -> bool:
    """Store interview answers and set status to interview_done. answers: [{ question_id, question_text?, answer }, ...]."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        return False
    c["status"] = STATUS_INTERVIEW_DONE
    c["interview_answers"] = answers
    _save(data)
    return True


def set_candidate_interview_report(
    candidate_id: str, report: Optional[str] = None, evaluation_result: Optional[str] = None
) -> bool:
    """Store interview HR report and/or evaluation result (strengths, weaknesses, etc.). Returns True if updated."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        return False
    if evaluation_result is not None:
        c["interview_evaluation_result"] = str(evaluation_result).strip() if evaluation_result else ""
    _save(data)
    return True


# -----------------------------------------------------------------------------
# HR User Management
# -----------------------------------------------------------------------------

def create_hr_user(email: str, password: str) -> bool:
    """Create a new HR user. Returns True if created, False if email already exists."""
    data = _load()
    hr_users = data.get("hr_users", [])
    email = (email or "").strip().lower()
    for u in hr_users:
        if u.get("email") == email:
            return False
    
    # In a real app, hash this password! Per user request, saved as plain text.
    # New users are marked as NOT approved until the admin confirms.
    hr_users.append({
        "id": uuid.uuid4().hex,
        "email": email,
        "password": password,
        "approved": False
    })
    data["hr_users"] = hr_users
    _save(data)
    return True


def hr_login(email: str, password: str) -> Optional[dict]:
    """Check HR credentials against admin, env var, or store. Returns user dict on success."""
    email = (email or "").strip().lower()
    
    # 1. Admin login
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        return {"id": "admin", "email": ADMIN_EMAIL, "role": "admin", "approved": True}

    # 2. Check env var fallback (legacy)
    env_pass = os.getenv("HR_PASSWORD", "")
    if env_pass and password == env_pass:
        return {"id": "legacy_admin", "email": email, "role": "hr", "approved": True}

    # 3. Check stored users
    data = _load()
    for u in data.get("hr_users", []):
        if u.get("email") == email and u.get("password") == password:
            if u.get("approved"):
                return {"id": u["id"], "email": u["email"], "role": "hr", "approved": True}
            else:
                # Not approved yet
                return None
            
    return None


def get_pending_hr_users() -> List[dict]:
    """List HR accounts awaiting approval."""
    data = _load()
    return [u for u in data.get("hr_users", []) if not u.get("approved")]


def approve_hr_user(email: str) -> bool:
    """Approve a pending HR user."""
    data = _load()
    email = email.lower().strip()
    for u in data.get("hr_users", []):
        if u.get("email") == email:
            u["approved"] = True
            _save(data)
            return True
    return False


def reject_hr_user(email: str) -> bool:
    """Reject and remove a pending HR user signup."""
    data = _load()
    email = email.lower().strip()
    users = data.get("hr_users", [])
    for i, u in enumerate(users):
        if u.get("email") == email:
            users.pop(i)
            _save(data)
            return True
    return False


# -----------------------------------------------------------------------------
# Candidate Password Reset / Token Flow
# -----------------------------------------------------------------------------

def set_candidate_password_reset_token(candidate_id: str) -> str:
    """Generate and save a password reset token for a candidate. Returns the token."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        raise ValueError("Candidate not found")
        
    token = secrets.token_urlsafe(32)
    # Store token with timestamp if we wanted expiration, but for now just token
    c["password_reset_token"] = token
    _save(data)
    return token


def get_candidate_by_token(token: str) -> Optional[dict]:
    """Find candidate by password reset token."""
    data = _load()
    for run in data.get("runs", []):
        for c in run.get("candidates", []):
            if c.get("password_reset_token") == token:
                return {
                    "candidate_id": c["id"],
                    "email": c.get("email"),
                    "first_name": c.get("first_name"),
                    "last_name": c.get("last_name"),
                    "run_id": run["run_id"]
                }
    return None


def set_candidate_password(candidate_id: str, password: str) -> bool:
    """Set candidate password and clear the reset token."""
    data = _load()
    c, run = _find_candidate_in_runs(data, candidate_id)
    if not c:
        return False
        
    c["password"] = password
    c["password_reset_token"] = None  # Clear token after use
    _save(data)
    return True
