# IntiqAI GUI

Unified web interface for HR and candidates.

## Flow

- **Landing** (`/`) — Choose HR or Candidate portal.
- **HR** — Sign in with `HR_PASSWORD` (default `hr2024`; set in `.env`). Overview auto-updates every 10s. Upload JD + CVs, run filtering, then assign email/password per candidate. Overview shows each candidate’s status (shortlisted → fka_started → fka_done → interview_started → interview_done). “Shortlisted” means they passed CV screening and are selected for the next phase.
- **Candidate** — Sign in with the email and password provided by HR. Portal shows: Start FKA → View FKA results → Start Interview. FKA and interview progress are reflected on the HR overview.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing |
| `/hr/login` | HR login |
| `/hr/overview` | HR dashboard (runs + candidates, auto-refresh) |
| `/hr/upload` | Upload JD & CVs, run filter, assign credentials |
| `/candidate/login` | Candidate login |
| `/candidate/portal` | Candidate dashboard (FKA + Interview links) |
| `/candidate/fka/result` | FKA results (and marks FKA done) |

## Run

Start the app with `python run_all.py` from the project root. Open **http://127.0.0.1:8001** for the GUI. Interview app runs on **http://127.0.0.1:8500** (opened from the candidate portal).
