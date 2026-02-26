# IntiqAI — Project Changes & Improvements Log

> **Period Covered:** This document details all changes, additions, cleanups, and feature implementations made to the IntiqAI platform during the current development session.

---

## 🚀 How to Run

```powershell
# 1. Navigate to the project directory
cd d:\4MS-main\4MS-main

# 2. Create the virtual environment (first time only)
python -m venv venv

# 3. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 4. Install dependencies (first time only)
pip install -r requirements.txt

# 5. Start both servers
python run_all.py
```

| Service | URL |
|---|---|
| IntiqAI GUI | http://127.0.0.1:8001 |
| FKA Sub-App | http://127.0.0.1:8500 |

---

## Table of Contents

1. [CV Screening Logic Improvements](#1-cv-screening-logic-improvements)
2. [Admin Approval System](#2-admin-approval-system)
3. [Admin Management UI](#3-admin-management-ui)
4. [Role-Based Authentication & Navigation](#4-role-based-authentication--navigation)
5. [Bug Fixes](#5-bug-fixes)
6. [Project Cleanup — Deleted Files & Assets](#6-project-cleanup--deleted-files--assets)
7. [Database Design Document](#7-database-design-document)
8. [Summary of Modified Files](#8-summary-of-modified-files)

---

## 1. CV Screening Logic Improvements

### What Changed
The CV screening pipeline was updated to be more lenient and practical when shortlisting candidates.

**File:** `cv_filtering/cv_filtering.py`

- **Overall Fit Score Prioritized:** The shortlisting logic now primarily uses the LLM-assigned `Overall Fit` score (threshold: ≥ 8/10). A candidate can be shortlisted even if they don't perfectly satisfy every individual "must-have" criterion, as long as their overall profile is strong.
- **Candidate Name Fallback:** If the LLM fails to extract a candidate's name from a CV, the system now falls back to a human-readable label (`Candidate 1`, `Candidate 2`, etc.) instead of showing the raw PDF filename.

**File:** `db/store.py`

- The name extraction fallback was updated to generate `"Candidate {i+1}"` display labels when both `first_name` and `last_name` are blank after processing.

---

## 2. Admin Approval System

### Overview
A full admin-controlled HR account signup approval workflow was built from scratch. New HR accounts are no longer active immediately after signup — they must be explicitly approved by the super-admin before login is permitted.

### Admin Credentials
The super-admin account is hardcoded for this iteration:

| Field | Value |
|---|---|
| Email | `intiqaia4@gmail.com` |
| Password | `IntiqAI2026` |

> ⚠️ In a production environment, these credentials must be moved to environment variables or a secrets manager, and the password must be hashed.

### How the Approval Flow Works

```
[New HR User] → Signs up at /hr/signup
      ↓
[db/store.py] → Account created with approved: false
      ↓
[credentials_automation.py] → Admin receives notification email
      ↓
[Admin] → Logs in at /hr/login → Redirected to /hr/admin
      ↓
[Admin Management UI] → Views pending list → Clicks Approve or Reject
      ↓
[HR User] → Can now log in at /hr/login → Redirected to /hr/overview
```

### Changes — `db/store.py`

- **Added** `ADMIN_EMAIL` and `ADMIN_PASSWORD` constants at the top of the file.
- **Updated** `create_hr_user()`:
  - New users are created with `"approved": False` by default.
- **Updated** `hr_login()`:
  - Checks admin credentials first (returns `role: "admin"`).
  - Falls back to legacy `HR_PASSWORD` env var (returns `role: "hr"`).
  - Checks stored HR users, verifying both password and `approved` status.
  - Returns `None` (login rejected) if user is not yet approved.
- **Added** `get_pending_hr_users()` — returns all users with `approved: false`.
- **Added** `approve_hr_user(email)` — sets `approved: true` for a given email.
- **Added** `reject_hr_user(email)` — removes the pending user entirely.
- **Updated** existing HR user records in `db/intiqai_store.json` — all pre-existing accounts were set to `"approved": true` so they weren't locked out.

### Changes — `shared/credentials_automation.py`

- **Added** `send_admin_new_signup_notification(email)` — sends an SMTP email to the admin's address when a new HR signup request is submitted, prompting them to log in and review.

### Changes — `gui/api.py`

- **Updated** `api_hr_signup` endpoint — now calls `send_admin_new_signup_notification` after a successful account creation.
- **Updated** `api_hr_login` endpoint:
  - Returns the user's `role` (`"admin"` or `"hr"`) in the JSON response.
  - Sets an `admin_token` cookie (in addition to `hr_token`) when the admin logs in.
- **Added** helper `_admin_authenticated(request)` — returns `True` only if `admin_token` cookie is present.
- **Added** helper `_get_hr_role(request)` — returns `"admin"` or `"hr"` based on the session cookies.
- **Added** `GET /api/admin/pending_users` — lists all HR accounts awaiting approval (admin only).
- **Added** `POST /api/admin/approve_user` — approves a pending account by email (admin only).
- **Added** `POST /api/admin/reject_user` — rejects and deletes a pending account by email (admin only).
- **Updated** `api_hr_logout` — clears both `hr_token` and `admin_token` cookies on logout.
- **Updated** `api_hr_me` — returns the correct `role` based on live session cookies.
- **Updated** `api_hr_overview` — now includes the `role` field in its JSON response so the frontend can adapt the UI.

---

## 3. Admin Management UI

### New Page: `/hr/admin`

**File Created:** `gui/static/HR/Admin_Management`

A dedicated management interface accessible only to the super-admin. Features:
- Displays a real-time table of pending HR signup requests, fetched from `GET /api/admin/pending_users`.
- Each row shows the user's email and ID.
- **Approve** button — calls `POST /api/admin/approve_user` and refreshes the list.
- **Reject** button — calls `POST /api/admin/reject_user` with a confirmation prompt.
- Shows "Access Denied" if accessed without an admin session cookie.
- Shows "No pending requests" when the queue is empty.
- Includes dark mode support and navigation links back to the HR Dashboard.

**File Modified:** `gui/api.py`

- **Added** route `GET /hr/admin` → serves the `Admin_Management` page.

---

## 4. Role-Based Authentication & Navigation

### Login Redirection

**File Modified:** `gui/static/Main_Pages/HR_Login`

- The login form now inspects the `role` field returned by `POST /api/auth/hr_login`.
- **Admin role** → redirects to `/hr/admin`.
- **HR role** → redirects to `/hr/overview` (unchanged).

### Dashboard Navigation

**File Modified:** `gui/static/HR/Overview`

- A **"Manage Users"** link was added to the dashboard header. It links to `/hr/admin`.
- The link is **hidden by default** using CSS (`class="hidden"`).
- On page load, the dashboard fetches `GET /api/hr/overview`, which now returns the user's `role`.
- If `role === "admin"`, the "Manage Users" link is made visible via JavaScript.

---

## 5. Bug Fixes

### `NameError` in `gui/api.py`
- **Issue:** A reference to `FKA_PHASE_DIR` (a deleted variable from an old project structure refactor) caused a `NameError` at runtime on certain endpoints.
- **Fix:** Replaced usages with `ROOT_DIR`, which is always defined.

### Dashboard "Failed to Load" Error
- **Issue:** After adding role-detection code to `gui/static/HR/Overview`, the dashboard showed "Failed to load" for approved HR users.
- **Root Cause:** A JavaScript `ReferenceError` — code referenced a variable `d` (from an earlier draft) instead of `data` (the actual fetch response variable).
- **Additional Issue:** A missing line that calls `dashEl.classList.remove("hidden")` was accidentally removed during an edit, keeping the dashboard container permanently hidden.
- **Fix:** Corrected the variable reference to `data.role` and restored the visibility toggle for the dashboard container.

### `/hr/admin` 404 Not Found
- **Issue:** Navigating to `/hr/admin` after login returned a JSON 404 error.
- **Root Cause:** The `Admin_Management` page was created with a `.html` extension (`Admin_Management.html`), but the project's routing convention (used for `Overview`, `Upload`, etc.) expects files without extensions.
- **Fix:** Renamed the file from `Admin_Management.html` to `Admin_Management`.

---

## 6. Project Cleanup — Deleted Files & Assets

### Old FKA UI (Redundant after FKA became a mounted sub-app)
The FKA system is now served entirely by the `fka/web_app.py` sub-application mounted at `/fka`. The old standalone hand-built FKA pages in `gui/static/FKA/` were self-contained and not reachable via any route in `api.py`.

| Deleted File | Previous Location |
|---|---|
| `FKA_Landing` | `gui/static/FKA/FKA_Landing` |
| `FKA_Stage` | `gui/static/FKA/FKA_Stage` |
| `FKA_STAGE_RESULT` | `gui/static/FKA/FKA_STAGE_RESULT` |

### Orphaned Scripts
| Deleted File | Reason |
|---|---|
| `dump_results.py` | A one-off debug script used to print Excel contents to the terminal. No longer needed. |
| `gui/app.py` | The original 95KB legacy application file (Streamlit/Flask-era). Fully superseded by `gui/api.py`. |

### Large Archive
| Deleted File | Reason |
|---|---|
| `cleanup_backup.zip` | A 1.2 GB backup archive created during a previous cleanup session. Removed to recover disk space. |

**Total space recovered: ~1.2 GB**

---

## 7. Database Design Document

A full database schema design document was created at the project root to guide a future migration from the current flat-file JSON store to a production-grade PostgreSQL database.

**File Created:** `DATABASE_DESIGN.md`

### Covers
- 10 tables across 7 domains: `hr_users`, `hr_sessions`, `runs`, `candidates`, `must_have_criteria`, `fka_question_pools`, `fka_sessions`, `fka_answers`, `interview_sessions`, `interview_answers`, `notifications`, `audit_log`.
- Full column definitions: types, constraints, nullability, foreign keys.
- Entity-Relationship diagram (Mermaid).
- Indexing strategy for performance.
- Key design decisions: password hashing, session tokens, multi-tenancy (owner_id), file storage, soft deletes, audit logging.
- 4-phase migration plan from JSON to PostgreSQL.

---

## 8. Summary of Modified Files

| File | Type | Change |
|---|---|---|
| `db/store.py` | Backend | Added admin credentials, approval system, login role checking |
| `db/intiqai_store.json` | Database | Existing users updated to `approved: true` |
| `gui/api.py` | Backend | New admin routes, role-aware login, fixed NameError, /hr/admin route |
| `shared/credentials_automation.py` | Backend | Added admin notification email function |
| `gui/static/Main_Pages/HR_Login` | Frontend | Role-based post-login redirection |
| `gui/static/HR/Overview` | Frontend | "Manage Users" link, role-aware visibility, bug fixes |
| `gui/static/HR/Admin_Management` | Frontend | **New** — Admin approval management page |
| `cv_filtering/cv_filtering.py` | Backend | Relaxed CV screening logic (Overall Fit priority) |
| `DATABASE_DESIGN.md` | Documentation | **New** — Full database schema design document |
| `gui/static/FKA/FKA_Landing` | Frontend | **Deleted** — Unused old FKA UI |
| `gui/static/FKA/FKA_Stage` | Frontend | **Deleted** — Unused old FKA UI |
| `gui/static/FKA/FKA_STAGE_RESULT` | Frontend | **Deleted** — Unused old FKA UI |
| `dump_results.py` | Script | **Deleted** — Orphaned debug script |
| `gui/app.py` | Backend | **Deleted** — Legacy app replaced by `api.py` |
| `cleanup_backup.zip` | Archive | **Deleted** — 1.2 GB old backup |
