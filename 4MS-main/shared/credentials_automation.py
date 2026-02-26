"""
Automate candidate credentials: extract emails from Excel/CVs, generate passwords,
save to store, and send SMTP emails to qualified candidates with FKA login link.
"""
import os
import re
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Same base as api.py; .env is at repo root (parent of this folder) when running via run_all.py
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
_ENV_LOADED = False


def _ensure_env_loaded():
    """Load .env from repo root or this folder so SMTP_* are available in the API subprocess."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
        for path in (PROJECT_ROOT / ".env", BASE_DIR / ".env", Path.cwd() / ".env"):
            if path.resolve().exists():
                load_dotenv(path.resolve(), override=True)
                break
        _ENV_LOADED = True
    except Exception:
        _ENV_LOADED = True


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _email_from_resume_text(text: str) -> str:
    """Extract first valid email from resume text using regex."""
    if not text or not isinstance(text, str):
        return ""
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return (emails[0].strip() if emails else "") or ""


def generate_password(length: int = 12) -> str:
    """Generate a URL-safe password (no ambiguous chars for readability)."""
    return secrets.token_urlsafe(length)[:length]


def load_emails_for_run(run_id: str) -> List[Dict[str, Any]]:
    """
    Load run from store and Excel; return list of { candidate_id, email, first_name, last_name }
    (one per store candidate) with email from store, or from Excel column Email/Email Address,
    or extracted from Full Resume.
    """
    from db.store import _load, _find_run

    data = _load()
    run = _find_run(data, run_id)
    if not run:
        return []

    candidates = run.get("candidates", [])
    if not candidates:
        return []

    # Build map from Excel: (first_name_normalized, last_name_normalized) -> { email, first_name, last_name }
    excel_by_name: Dict[Tuple[str, str], Dict[str, str]] = {}
    high_path = run.get("high_scoring_excel") or ""
    all_path = run.get("all_results_excel") or ""
    excel_path = high_path or all_path
    if excel_path:
        path = Path(excel_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            try:
                import pandas as pd
                df = pd.read_excel(str(path))
                first_col = "First Name" if "First Name" in df.columns else None
                last_col = "Last Name" if "Last Name" in df.columns else None
                email_col = "Email" if "Email" in df.columns else ("Email Address" if "Email Address" in df.columns else None)
                full_resume_col = "Full Resume" if "Full Resume" in df.columns else None
                for idx, row in df.iterrows():
                    raw_first = row.get(first_col, "") if first_col else ""
                    raw_last = row.get(last_col, "") if last_col else ""
                    raw_email = row.get(email_col, "") if email_col else ""
                    first = str(raw_first or "").strip()
                    last = str(raw_last or "").strip()
                    email = str(raw_email or "").strip()
                    if not email and full_resume_col:
                        email = _email_from_resume_text(str(row.get(full_resume_col, "") or ""))
                    key = (_normalize(first), _normalize(last))
                    if key not in excel_by_name:
                        excel_by_name[key] = {"email": email.strip(), "first_name": first, "last_name": last}
            except Exception:
                pass

    out: List[Dict[str, Any]] = []
    for c in candidates:
        first = (c.get("first_name") or "").strip()
        last = (c.get("last_name") or "").strip()
        key = (_normalize(first), _normalize(last))
        row_data = excel_by_name.get(key, {})
        email = (row_data.get("email") or "").strip() or ((c.get("email") or "").strip())
        out.append({
            "candidate_id": c["id"],
            "email": email,
            "first_name": first or row_data.get("first_name", ""),
            "last_name": last or row_data.get("last_name", ""),
        })
    return out


def send_credentials_email(
    to_email: str,
    first_name: str,
    reset_link: str,
    *,
    subject: Optional[str] = None,
) -> Optional[str]:

    _ensure_env_loaded()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@intiqai.local").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes")

    if not smtp_host or not smtp_user or not smtp_password:
        return "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env."

    name = (first_name or "Candidate").strip()
    subj = subject or "IntiqAI – Action Required: Set Your Password"

    # Plain-text fallback
    text_body = f"""
Hello {name},

Congratulations! You have qualified for the next stage of our hiring process: the Fundamental Knowledge Assessment (FKA).

Please set your password to access the candidate portal:

{reset_link}

Best regards,
The IntiqAI Team
"""

    # HTML version
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:40px;">
  <div style="max-width:600px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">

    <h2 style="color:#1a73e8; margin-top:0;">
      🎉 Congratulations {name}!
    </h2>

    <p style="font-size:16px; color:#333;">
      You have qualified for the next stage of our hiring process:
      <strong>Fundamental Knowledge Assessment (FKA)</strong>.
    </p>

    <p style="font-size:16px; color:#333;">
      Please set your password to access the candidate portal:
    </p>

    <div style="text-align:center; margin:30px 0;">
      <a href="{reset_link}"
         style="background-color:#1a73e8;
                color:white;
                padding:14px 28px;
                text-decoration:none;
                font-size:16px;
                border-radius:6px;
                display:inline-block;
                font-weight:bold;">
        Set Password & Login
      </a>
    </div>

    <p style="font-size:12px; color:#999;">
      Or copy this link: {reset_link}
    </p>
    
    <hr style="border:none; border-top:1px solid #eee; margin:25px 0;">

    <p style="font-size:13px; color:#999;">
      © {Path(__file__).resolve().parent.name} – IntiqAI Team
    </p>

  </div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = smtp_from
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if use_tls:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        return None
    except Exception as e:
        return str(e)


def auto_create_and_send(
    run_id: str,
    *,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    In-file helper: load_emails_for_run is defined above in this file.
    """
    from db.store import set_candidate_password_reset_token
    
    login_base = (base_url or os.getenv("CANDIDATE_PORTAL_URL", "http://127.0.0.1:8001")).rstrip("/")
    # Endpoint we made: /candidate/set-password?token=...
    
    # load_emails_for_run is defined in this module, so just call it directly
    entries = load_emails_for_run(run_id)
    created = 0
    skipped_no_email = 0
    errors: List[str] = []

    to_send: List[Dict[str, Any]] = []

    for e in entries:
        # Check status from store to avoid inviting disqualified candidates
        # We need to look up the candidate in the store again or trust load_emails_for_run (which comes from store)
        # load_emails_for_run returns dict with candidate_id.
        # We didn't fetch status in load_emails_for_run.
        # Let's peek at store or just rely on 'load_emails_for_run' not filtering.
        # Ideally, load_emails_for_run should filter.
        # But let's filter here for safety.
        # We need to read status.
        # Let's import get_candidate.
        from db.store import get_candidate, STATUS_DISQUALIFIED
        cand = get_candidate(e["candidate_id"])
        if not cand or cand.get("status") == STATUS_DISQUALIFIED:
            continue
            
        email = (e.get("email") or "").strip()
        if not email or "@" not in email:
            skipped_no_email += 1
            continue
            
        # Generate token
        try:
            token = set_candidate_password_reset_token(e["candidate_id"])
            reset_link = f"{login_base}/candidate/set-password?token={token}"
            
            to_send.append({
                "email": email,
                "first_name": e.get("first_name") or "Candidate",
                "reset_link": reset_link,
            })
        except Exception as ex:
            errors.append(f"Failed to set token for {email}: {ex}")

    for item in to_send:
        err = send_credentials_email(
            item["email"],
            item["first_name"],
            item["reset_link"],
        )
        if err:
            errors.append(f"{item['email']}: {err}")
        else:
            created += 1

    return {
        "created": created,
        "skipped_no_email": skipped_no_email,
        "errors": errors,
    }


def send_fka_result_email(
    to_email: str,
    first_name: str,
    passed: bool,
    score: int,
    *,
    subject: Optional[str] = None,
) -> Optional[str]:
    """
    Send an email notifying the candidate of their FKA result.
    If passed: Congratulations + next steps.
    If failed: Thank you + rejection.
    """
    _ensure_env_loaded()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        smtp_port = 587
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@intiqai.local").strip()
    use_tls_val = os.getenv("SMTP_USE_TLS", "true").strip().lower()
    use_tls = use_tls_val in ("1", "true", "yes")

    if not smtp_host or not smtp_user or not smtp_password:
        return "SMTP not configured."

    name = (first_name or "Candidate").strip()
    
    if passed:
        subj = subject or "IntiqAI – Assessment Result: Passed"
        text_body = f"""
Hello {name},

Congratulations! You have successfully passed the Fundamental Knowledge Assessment (FKA) with a score of {score}/100.

We are reviewing your results and will be in touch shortly regarding the next stage of the interview process.

Best regards,
The IntiqAI Team
"""
        html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:40px;">
  <div style="max-width:600px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">
    <h2 style="color:#059669; margin-top:0;">🎉 Assessment Passed</h2>
    <p style="font-size:16px; color:#333;">
      Hello <strong>{name}</strong>,
    </p>
    <p style="font-size:16px; color:#333;">
      Congratulations! You have successfully passed the Fundamental Knowledge Assessment (FKA) with a score of <strong>{score}/100</strong>.
    </p>
    <p style="font-size:16px; color:#333;">
      We are reviewing your results and will be in touch shortly regarding the next stage of the interview process.
    </p>
    <div style="margin-top:30px; padding-top:20px; border-top:1px solid #eee;">
      <p style="font-size:14px; color:#666;">Best regards,<br>The IntiqAI Team</p>
    </div>
  </div>
</body>
</html>
"""
    else:
        subj = subject or "IntiqAI – Assessment Result Update"
        text_body = f"""
Hello {name},

Thank you for completing the Fundamental Knowledge Assessment (FKA).

Unfortunately, your score of {score}/100 did not meet our threshold for this position. We appreciate your interest in IntiqAI and wish you the best in your future endeavors.

Best regards,
The IntiqAI Team
"""
        html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:40px;">
  <div style="max-width:600px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">
    <h2 style="color:#333; margin-top:0;">Assessment Update</h2>
    <p style="font-size:16px; color:#333;">
      Hello <strong>{name}</strong>,
    </p>
    <p style="font-size:16px; color:#333;">
      Thank you for completing the Fundamental Knowledge Assessment (FKA).
    </p>
    <p style="font-size:16px; color:#333;">
      Unfortunately, your score of <strong>{score}/100</strong> did not meet our threshold for this position. We appreciate your interest in IntiqAI and wish you the best in your future endeavors.
    </p>
    <div style="margin-top:30px; padding-top:20px; border-top:1px solid #eee;">
      <p style="font-size:14px; color:#666;">Best regards,<br>The IntiqAI Team</p>
    </div>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = smtp_from
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if use_tls:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [to_email], msg.as_string())
        return None
    except Exception as e:
        return str(e)


def send_admin_new_signup_notification(pending_email: str) -> Optional[str]:
    """Send an email to the admin notifying them of a new HR signup request."""
    _ensure_env_loaded()
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    use_tls = os.getenv("SMTP_USE_TLS", "True").lower() == "true"

    from db.store import ADMIN_EMAIL

    if not all([smtp_host, smtp_user, smtp_password]):
        return "SMTP credentials not configured."

    subj = "New HR Account Request - IntiqAI"
    text_body = f"A new HR user has registered and is awaiting approval: {pending_email}"
    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; background-color:#f4f6f8; padding:40px;">
  <div style="max-width:600px; margin:auto; background:white; padding:30px; border-radius:10px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">
    <h2 style="color:#333; margin-top:0;">New Signup Request</h2>
    <p style="font-size:16px; color:#333;">
      A new HR user has registered with the email: <strong>{pending_email}</strong>
    </p>
    <p style="font-size:16px; color:#333;">
      Please log in to the admin portal to approve or reject this request.
    </p>
    <div style="margin-top:30px; padding-top:20px; border-top:1px solid #eee;">
      <p style="font-size:14px; color:#666;">This is an automated notification from IntiqAI.</p>
    </div>
  </div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = smtp_from
    msg["To"] = ADMIN_EMAIL

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if use_tls:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [ADMIN_EMAIL], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [ADMIN_EMAIL], msg.as_string())
        return None
    except Exception as e:
        return str(e)
