"""
CV Filtering Module for IntiqAI

This module provides CV/resume filtering, evaluation, and export functionality.
No Streamlit dependencies - pure Python logic.
"""

import os
import re
import json
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd
from PyPDF2 import PdfReader
from pydantic import BaseModel, field_validator
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# LangChain for CV filtering (using Groq for testing; set GROQ_API_KEY in .env)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq
from tenacity import retry, stop_after_attempt, wait_exponential

# Google Drive (optional)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# ============================================================================
# CONSTANTS
# ============================================================================

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CACHE_FILE = "drive_upload_cache.json"

# CV screening: minimum Overall Fit (1-10) to be shortlisted. Candidates with Overall Fit >= this
# and no missing MUST-HAVEs go to High_Scoring_Candidates.xlsx and into the run.
HIGH_SCORE_THRESHOLD_DEFAULT = 8


# ============================================================================
# PROMPTS
# ============================================================================

JD_FIX_PROMPT = ChatPromptTemplate.from_template("""
You are an experienced HR and talent acquisition specialist.

Goal: Clean and structure this job description so it is optimized for **internal screening and CV evaluation**, not for job advertising.

Do the following:
- Keep the same job role and core requirements.
- Organize the description into clear, structured sections useful for recruiters, such as:
  - Job Title
  - Location (if provided)
  - Employment Type (if provided)
  - Summary / Purpose of the Role
  - Key Responsibilities
  - Must-Have Requirements (hard screening criteria)
  - Nice-to-Have / Preferred Requirements
  - Technical Skills
  - Soft Skills
- Make the language clear, neutral, and ATS-friendly.
- Remove marketing language, fluff, and employer-branding content that is not relevant for screening.
- Do NOT add sections like "About Us", "Benefits", "Perks", or "Why Join Us" unless they already exist and are essential.
- Remove bias or gender-coded language.
- Clarify any ambiguous requirements where possible.

IMPORTANT:
- Explicitly extract two lists from the job description:
  1) must_have_requirements: hard screening criteria (e.g., required degree/cert, years, core skills, mandatory domain).
  2) nice_to_have_requirements: preferences (helpful but not mandatory).
- Keep each requirement short and atomic (one idea per bullet).
- Do NOT invent requirements that are not supported by the text.

Return JSON ONLY in exactly this format (no extra text):

{{
  "improved_job_description": "",
  "high_level_summary": "",
  "detailed_changes": [""],
  "must_have_requirements": [""],
  "nice_to_have_requirements": [""]
}}

Raw Job Description:
{jd_text}
""")

RECRUITER_PROMPT = ChatPromptTemplate.from_template("""

You are a recruiter evaluating a candidate's resume against a structured internal job description.

You are given:
- A detailed job description optimized for screening.
- A list of MUST-HAVE requirements.
- A list of NICE-TO-HAVE requirements.
- The candidate's resume.

Your evaluation must be fair, realistic, recruiter-like, and NOT overly strict or keyword-dependent.

====================================================================
INTERPRETING MUST-HAVES (FAIR, REALISTIC, HUMAN-LIKE)
====================================================================
A MUST-HAVE requirement may be counted as **satisfied** if ANY of the following are true:

1. **Explicitly satisfied**
   The resume directly states the required skill, tool, qualification, or experience.

2. **Implicitly or likely satisfied**
   Very closely related experience strongly implies the requirement.
   Examples:
   - "Next.js" → implies React
   - "REST APIs" → implies HTTP/API fundamentals
   - "GitHub collaboration" → implies Git
   - "Statistical modeling" → implies analytical skills

3. **Partially satisfied**
   Some relevant evidence appears, even if not exact.

4. **UNIVERSAL HIERARCHY RULE (GLOBAL SKILL LOGIC)**
   If the candidate demonstrates a **higher-level, more advanced, more senior, or more specialized version** of a requirement,
   then the lower-level requirement is automatically considered satisfied.

   Examples:
   - Master's degree → satisfies Bachelor's requirement
   - Senior-level duties → satisfy junior/mid-level requirements
   - Advanced Excel/Power BI → satisfies basic Excel
   - Leading teams → satisfies teamwork/collaboration
   - Full-stack engineering → satisfies backend or frontend basics
   - Advanced ML models → satisfies basic ML fundamentals

   This applies to **education, skills, experience, and tools**.

A MUST-HAVE should be marked **missing** ONLY IF:
- No explicit match,
- No implied/related evidence,
- No partial match,
- No higher-level equivalent.

Do NOT penalize candidates for:
- Different terminology,
- Summarized resumes,
- Not repeating keywords word-for-word.

====================================================================
SCORING FRAMEWORK (HUMAN-LIKE)
====================================================================




Detailed scoring:
10: ALL must-haves satisfied + strong alignment + ALL nice-to-haves + strong reward factor
9: ALL must-haves satisfied + MANY nice-to-haves + low/medium risk
7–8: ALL must-haves satisfied + SOME nice-to-haves + moderate alignment (7 = moderate risk or weaker depth, 8 = solid alignment and lower risk)
6: ALL must-haves satisfied but noticeable risk or limited relevance
5: ONE must-have missing but otherwise strong candidate
3–4: MORE THAN ONE must-have missing, partial relevance
1–2: MANY must-haves missing, low relevance

Nice-to-have guardrail:
- Scores 7–8 require at least ONE nice-to-have to be satisfied.
- If ZERO nice-to-haves are satisfied → the score must NOT exceed 6.


====================================================================
RISK & REWARD FACTORS
====================================================================
Risk factor examples:
- Skill gaps
- Limited experience
- Job hopping
- Lack of clarity
- Weak technical grounding

Reward factor examples:
- Strong foundation
- High-quality experience
- Leadership
- Strong technical achievement

Risk and reward scores must be:
- "Low", "Medium", or "High"
Each with a short explanation.

Risk can reduce the score (within allowed ranges).
Reward can increase the score (within allowed ranges).
Reward **cannot** override missing must-haves.

====================================================================
REQUIRED OUTPUT FIELDS
====================================================================
You MUST explicitly list:

- satisfied_must_haves
- missing_must_haves
- satisfied_nice_to_haves
- missing_nice_to_haves

Return JSON ONLY in this structure:

{{
  "candidate_strengths": [],
  "candidate_weaknesses": [],
  "risk_factor": {{
    "score": "",
    "explanation": ""
  }},
  "reward_factor": {{
    "score": "",
    "explanation": ""
  }},
  "satisfied_must_haves": [],
  "missing_must_haves": [],
  "satisfied_nice_to_haves": [],
  "missing_nice_to_haves": [],
  "overall_fit_rating": 0,
  "justification_for_rating": ""
}}

Job Description: {job_description}
Explicit MUST-HAVEs: {must_have_requirements}
Explicit NICE-TO-HAVEs: {nice_to_have_requirements}
Candidate Resume: {resume_text}
""")

CONTACT_PROMPT = ChatPromptTemplate.from_template("""
Extract:
{{
 "First Name": "",
 "Last Name": "",
 "Email Address": ""
}}
Resume:
{resume_text}
""")

POSITION_EXTRACT_PROMPT = ChatPromptTemplate.from_template("""
Extract the job title/position from this job description. Return only the job title, nothing else.

Job Description:
{jd_text}
""")


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Config:
    """Configuration for CV filtering process."""
    jd_text: str
    resumes_dir: str
    out_dir: str
    Improved_JD_dir: str
    model: str = "llama-3.1-8b-instant"  # Groq model (use GROQ_MODEL in .env to override)
    temperature: float = 0.2
    high_score_threshold: int = HIGH_SCORE_THRESHOLD_DEFAULT


class RiskReward(BaseModel):
    """Risk or Reward factor with score and explanation."""
    score: str
    explanation: str

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, v):
        v = str(v).title()
        if "Low" in v:
            return "Low"
        if "High" in v:
            return "High"
        return "Medium"


class ScreeningResult(BaseModel):
    """Result of screening a single resume."""
    candidate_strengths: List[str]
    candidate_weaknesses: List[str]
    risk_factor: RiskReward
    reward_factor: RiskReward
    overall_fit_rating: int
    justification_for_rating: str
    Date: str
    Resume: str
    First_Name: str = ""
    Last_Name: str = ""
    Email: str = ""
    Full_Resume: str = ""

    Satisfied_Must_Haves: List[str] = []
    Missing_Must_Haves: List[str] = []
    Satisfied_Nice_Haves: List[str] = []
    Missing_Nice_Haves: List[str] = []


# ============================================================================
# GOOGLE DRIVE INTEGRATION (OPTIONAL)
# ============================================================================

def get_credentials() -> Optional[Credentials]:
    """Get Google Drive credentials. Returns None if credentials file not found."""
    creds = None
    possible_paths = [
        "client_secret.json",
        r"C:\Users\96658\Desktop\TalentTalk\client_secret_2_744938258489-91hb253qiop2e8rl8uuj9duhh6fn1dj4.apps.googleusercontent.com.json"
    ]

    client_secrets_file = None
    for path in possible_paths:
        if os.path.exists(path):
            client_secrets_file = path
            break

    if not client_secrets_file:
        return None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_file,
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def load_cache() -> dict:
    """Load the upload cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    """Save the upload cache to disk."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def upload_to_drive(file_path: str, folder_id: str) -> Optional[str]:
    """Upload file to Google Drive with duplicate detection."""
    creds = get_credentials()
    if not creds:
        return None

    filename = os.path.basename(file_path)
    cache = load_cache()
    cache_key = f"{folder_id}/{filename}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        service = build("drive", "v3", credentials=creds)
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            fields="files(id, name, webViewLink)",
            pageSize=1
        ).execute()

        existing_files = results.get('files', [])
        if existing_files:
            drive_link = existing_files[0].get('webViewLink')
            cache[cache_key] = drive_link
            save_cache(cache)
            return drive_link

        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype="application/pdf")
        uploaded = service.files().create(
            body=file_metadata, media_body=media, fields="webViewLink"
        ).execute()
        drive_link = uploaded.get("webViewLink")
        cache[cache_key] = drive_link
        save_cache(cache)
        return drive_link
    except Exception:
        return None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def read_pdf_text_from_path(path: str) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(path)
    return "\n".join([page.extract_text() or "" for page in reader.pages])


def clean_whitespace(s: str) -> str:
    """Normalize whitespace in a string."""
    return re.sub(r"\s+", " ", s.strip())


def make_llm(cfg: Config):
    """Create a LangChain LLM instance (Groq). Requires GROQ_API_KEY in .env."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Add it to your .env file (e.g. GROQ_API_KEY=gsk_...)."
        )
    model = cfg.model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(api_key=api_key, model=model, temperature=cfg.temperature)


# ============================================================================
# LLM INTERACTION
# ============================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def llm_json(llm, prompt, **kwargs) -> dict:
    """Invoke LLM and parse JSON response."""
    raw = (prompt | llm | StrOutputParser()).invoke(kwargs)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("Invalid JSON from LLM:\n" + raw)
    return json.loads(match.group(0))


def llm_text(llm, prompt, **kwargs) -> str:
    """Invoke LLM and return text response."""
    return (prompt | llm | StrOutputParser()).invoke(kwargs).strip()


# ============================================================================
# CORE EVALUATION FUNCTIONS
# ============================================================================

def evaluate_single_resume(
    llm,
    fixed_jd: str,
    must_haves: List[str],
    nice_to_haves: List[str],
    resume_text: str,
    resume_link: str
) -> ScreeningResult:
    """Evaluate one resume against the improved JD + explicit must/nice requirements."""
    must_haves_text = (
        "\n".join([f"- {x}" for x in must_haves]) if isinstance(must_haves, list) else str(must_haves or "")
    )
    nice_to_haves_text = (
        "\n".join([f"- {x}" for x in nice_to_haves]) if isinstance(nice_to_haves, list) else str(nice_to_haves or "")
    )

    data = llm_json(
        llm,
        RECRUITER_PROMPT,
        job_description=fixed_jd,
        must_have_requirements=must_haves_text,
        nice_to_have_requirements=nice_to_haves_text,
        resume_text=resume_text
    )

    sr = ScreeningResult(
        candidate_strengths=data.get("candidate_strengths", []),
        candidate_weaknesses=data.get("candidate_weaknesses", []),
        risk_factor=RiskReward(**data.get("risk_factor", {})),
        reward_factor=RiskReward(**data.get("reward_factor", {})),
        overall_fit_rating=int(data.get("overall_fit_rating", 0)),
        justification_for_rating=data.get("justification_for_rating", ""),
        Date=time.strftime("%Y-%m-%d %I:%M %p"),
        Resume=resume_link,
        Full_Resume=resume_text,
        Satisfied_Must_Haves=data.get("satisfied_must_haves", []),
        Missing_Must_Haves=data.get("missing_must_haves", []),
        Satisfied_Nice_Haves=data.get("satisfied_nice_to_haves", []),
        Missing_Nice_Haves=data.get("missing_nice_to_haves", []),
    )

    # Contact info
    try:
        ci = llm_json(llm, CONTACT_PROMPT, resume_text=resume_text)
        sr.First_Name = ci.get("First Name", "")
        sr.Last_Name = ci.get("Last Name", "")
        sr.Email = ci.get("Email Address", "")
    except Exception:
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z.-]+\.[A-Za-z]{2,}", resume_text)
        sr.Email = emails[0] if emails else ""

    return sr


def normalize_improved_jd(improved) -> str:
    """Convert the improved_job_description field into a readable text string."""
    if isinstance(improved, str):
        return improved
    if isinstance(improved, dict):
        parts = []
        for section, content in improved.items():
            parts.append(str(section).strip().upper())
            if isinstance(content, list):
                for item in content:
                    parts.append(f"- {str(item).strip()}")
            else:
                parts.append(str(content).strip())
            parts.append("")
        return "\n".join(parts).strip()
    return str(improved)


# ============================================================================
# DATA PROCESSING AND EXPORT
# ============================================================================

def results_to_dataframe(results: List[ScreeningResult]) -> pd.DataFrame:
    """Convert screening results to a pandas DataFrame."""
    rows = []
    for r in results:
        rows.append({
            "Date": r.Date,
            "Resume Link": r.Resume,
            "First Name": r.First_Name,
            "Last Name": r.Last_Name,
            "Email": r.Email,
            "Satisfied Must-Haves": "\n\n".join(r.Satisfied_Must_Haves or []),
            "Missing Must-Haves": "\n\n".join(r.Missing_Must_Haves or []),
            "Satisfied Nice-to-Haves": "\n\n".join(r.Satisfied_Nice_Haves or []),
            "Missing Nice-to-Haves": "\n\n".join(r.Missing_Nice_Haves or []),
            "Strengths": "\n\n".join(r.candidate_strengths or []),
            "Weaknesses": "\n\n".join(r.candidate_weaknesses or []),
            "Risk Factor": f"{r.risk_factor.score} - {r.risk_factor.explanation}",
            "Reward Factor": f"{r.reward_factor.score} - {r.reward_factor.explanation}",
            "Overall Fit": r.overall_fit_rating,
            "Justification": r.justification_for_rating,
            "Full Resume": r.Full_Resume,
        })
    return pd.DataFrame(rows)


def save_excels(df: pd.DataFrame, out_dir: str, threshold: int) -> Tuple[str, str]:
    """Save screening results to Excel files."""
    ensure_dir(out_dir)
    all_path = os.path.join(out_dir, "Resume_Screening_Results.xlsx")
    high_path = os.path.join(out_dir, "High_Scoring_Candidates.xlsx")

    df.to_excel(all_path, index=False)

    # Relaxed shortlisted criteria:
    # Primarily use the Overall Fit score. If score is high (>= threshold), they are shortlisted.
    # We no longer strictly disqualify for single missing must-haves if the LLM deemed them Fit 8+.
    high_df = df[df["Overall Fit"] >= threshold].copy()

    high_df.to_excel(high_path, index=False)
    return all_path, high_path


def save_jd_pdf(fixed_jd: str, must_haves: List[str], nice_haves: List[str], improved_jd_dir: str) -> str:
    """Save the improved JD as a readable PDF + extracted Must/Nice requirements."""
    ensure_dir(improved_jd_dir)
    path = os.path.join(improved_jd_dir, "Improved_Job_Description.pdf")

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    x = 50
    y = height - 50

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 50
        c.setFont("Helvetica", 11)

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Improved Job Description")
    y -= 30

    # Body JD
    c.setFont("Helvetica", 11)
    for line in fixed_jd.split("\n"):
        # Wrap long lines crudely by splitting
        chunks = []
        if len(line) <= 110:
            chunks = [line]
        else:
            # Simple wrap at ~110 chars
            buf = line
            while len(buf) > 110:
                chunks.append(buf[:110])
                buf = buf[110:]
            if buf:
                chunks.append(buf)

        for ch in chunks:
            if y < 60:
                new_page()
            c.drawString(x, y, ch)
            y -= 14

    # MUST-HAVES
    y -= 20
    if y < 80:
        new_page()
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x, y, "MUST-HAVE REQUIREMENTS:")
    y -= 18
    c.setFont("Helvetica", 11)

    for req in (must_haves or []):
        if y < 60:
            new_page()
        c.drawString(x, y, f"- {req}")
        y -= 14

    # NICE-HAVES
    y -= 20
    if y < 80:
        new_page()
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x, y, "NICE-TO-HAVE REQUIREMENTS:")
    y -= 18
    c.setFont("Helvetica", 11)

    for req in (nice_haves or []):
        if y < 60:
            new_page()
        c.drawString(x, y, f"- {req}")
        y -= 14

    c.save()
    return path


def extract_position_from_jd(llm, jd_text: str) -> str:
    """Extract the job position/title from the job description."""
    try:
        position = llm_text(llm, POSITION_EXTRACT_PROMPT, jd_text=jd_text)
        return position.strip()
    except:
        # Fallback: try to extract from common patterns
        patterns = [
            r"Job Title[:\s]+([^\n]+)",
            r"Position[:\s]+([^\n]+)",
            r"Role[:\s]+([^\n]+)",
            r"Title[:\s]+([^\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, jd_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "AI Specialist"  # Default fallback


# ============================================================================
# CANDIDATE MANAGEMENT
# ============================================================================

def load_candidates_from_excel(file_path: str, error_callback=None) -> Optional[pd.DataFrame]:
    """
    Load candidates from Excel file (High_Scoring_Candidates.xlsx).

    Args:
        file_path: Path to the Excel file
        error_callback: Optional callback function for error reporting (e.g., st.error)

    Returns:
        DataFrame with candidates or None if loading failed
    """
    try:
        df = pd.read_excel(file_path)
        required_cols = ['First Name', 'Last Name', 'Full Resume']
        if not all(col in df.columns for col in required_cols):
            msg = f"Excel file must contain columns: {', '.join(required_cols)}"
            if error_callback:
                error_callback(msg)
            return None

        # Ensure Full Resume is not empty or NaN
        df['Full Resume'] = df['Full Resume'].fillna('').astype(str)

        return df
    except Exception as e:
        if error_callback:
            error_callback(f"Failed to read Excel: {e}")
        return None


def sort_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Sort candidates by Overall Fit score (descending) and name."""
    if 'Overall Fit' in df.columns:
        df = df.sort_values(
            by=['Overall Fit', 'First Name', 'Last Name'],
            ascending=[False, True, True],
            na_position='last'
        ).reset_index(drop=True)
    else:
        df = df.sort_values(
            by=['First Name', 'Last Name'],
            ascending=[True, True]
        ).reset_index(drop=True)
    return df
