## IntiqAI – Voice‑Based Technical Interview & CV Screening

IntiqAI is a full-stack web application (FastAPI backend + custom HTML/JS frontend) that:
- **Filters CVs** against a Job Description using Google Gemini and LangChain
- **Conducts Fundamental Knowledge Assessment** to evaluate essential technical knowledge (text-based, using Groq)
- **Runs voice‑based technical interviews** with candidates, including STT (Whisper / AssemblyAI) and TTS (Edge)
- **Generates HR reports and timing analysis PDFs** for each interview

**Complete Workflow:**
```
CV Filtering → Fundamental Knowledge Assessment → Voice Interview → Reports
```

This README explains how any team member can **set up, run, and use** the project step‑by‑step.

---

## 1. Prerequisites

- **Python**: 3.10 or 3.11 (recommended; Whisper/AI tooling can be fragile on other versions)
- **Git**
- A GitHub account (for pulling/pushing code)
- Recommended OS: Windows 10/11, macOS, or Linux

Required:
- **Google AI Studio / Google Cloud** account for a **Gemini API key** (required for CV filtering and voice interviews)
- **Groq** account for a **Groq API key** (required for Fundamental Knowledge Assessment)

Optional but recommended:
- **AssemblyAI** account for cloud speech‑to‑text (if you want best STT quality)

---

## 2. Clone the Repository

On each team member's machine:

```bash
git clone https://github.com/MohX3/4MS.git
cd 4MS
```

If you're already in the project folder (because you copied it manually), just make sure your terminal path is the project root (where `app.py` and `requirements.txt` live).

---

## 3. Create and Activate a Virtual Environment

### Windows (PowerShell)

```powershell
cd 4MS
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
cd 4MS
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt after activation.

---

## 4. Install Python Dependencies

With the virtual environment **activated**:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs:
- `fastapi`, `uvicorn` – web framework and server
- `langchain`, `langgraph`, `google-genai`, `langchain_google_genai` – LLM orchestration & Gemini
- `groq` – Groq API for Fundamental Knowledge Assessment
- `openai-whisper`, `assemblyai`, `audio-recorder-streamlit`, `pydub` – audio/STT
- `reportlab`, `fpdf` – PDF report generation
- `pandas`, `openpyxl` – Excel file handling
- `python-docx`, `plotly` – Document processing and visualization
and other utilities listed in `requirements.txt`.

---

## 5. Environment Variables (.env Setup)

The app loads environment variables via `python-dotenv` at the top of `app.py`:

### 5.1 Create `.env`

In the project root (`4MS`), create a file named `.env`:

```text
GOOGLE_API_KEY=your_google_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

**Required API Keys:**
- `GOOGLE_API_KEY` **must** be set; otherwise the app raises an error on startup.
  - Get your key from: https://makersuite.google.com/app/apikey
- `GROQ_API_KEY` **must** be set for Fundamental Knowledge Assessment to work.
  - Get your key from: https://console.groq.com/keys

**Optional Environment Variables:**
- `GROQ_MODEL` – Groq model to use (default: `llama-3.1-8b-instant`)
- `FUNDAMENTAL_QUESTIONS_COUNT` – Number of fundamental questions to generate (default: 5, range: 1-10)
- `ASSEMBLYAI_API_KEY` – For cloud-based speech-to-text (optional)

**SMTP (for automatic credentials email to qualified candidates):**  
When using the GUI + API (`python run_all.py`), HR can click “Send credentials to qualified candidates” to auto-create passwords and email candidates. Set these in `.env` at the repo root (parent of `4MS-main`):
- `SMTP_HOST` – SMTP server (e.g. `smtp.gmail.com`)
- `SMTP_PORT` – Port (e.g. `587` for TLS)
- `SMTP_USER` – SMTP username / email
- `SMTP_PASSWORD` – SMTP password or app password
- `SMTP_FROM` – (optional) From address; defaults to `SMTP_USER`
- `SMTP_USE_TLS` – (optional) `true` or `false`; default `true`
- `CANDIDATE_PORTAL_URL` – (optional) Base URL for login link; default `http://127.0.0.1:8001`

If you have an `.env.example` file, you can copy it:

```bash
cp .env.example .env   # macOS/Linux
copy .env.example .env # Windows PowerShell
```

Then fill in your own keys.

---

## 6. Running the App

From the project root, with the virtual environment **activated** and `.env` configured:

```bash
python run_all.py
```

The terminal will print the local URLs for the two services.

```text
- IntiqAI GUI (HR & General): http://127.0.0.1:8001
- FKA Web App (Candidate Assessment): http://127.0.0.1:8500
```

Open `http://127.0.0.1:8001` in your browser to use the IntiqAI HR dashboard.

---

## 7. Using the App – CV Filtering Workflow

When you open the app (`http://127.0.0.1:8001`):

### 7.1 CV Filtering Setup Page

- **Directory Path with CV PDF Files**
  - Choose or type the folder path that contains **candidate CVs in PDF format**.
  - On Windows this might look like:
    - `C:\Users\YOUR_NAME\Desktop\4MS\uploaded_resumes`
  - You can click **"📂 Browse"** in the UI to select the folder.

- **Job Description (PDF File)**
  - Upload a **Job Description PDF** (e.g. `Job Descriptions/Front_End_Developer_General_JD.pdf`).
  - The app extracts text, cleans it, and uses it for AI‑based screening.

Then click:

- **"🚀 Start CV Filtering Process"**

The app will:
- Improve/structure the Job Description (Gemini)
- Scan all CV PDFs in the directory
- Score candidates and generate:
  - `Filtered Resumes/Resume Screening Results/Resume_Screening_Results.xlsx`
  - `Filtered Resumes/High Scoring Candidates/High_Scoring_Candidates.xlsx`
  - An improved JD PDF in `Improved Job Descriptions/`

After processing, it navigates to the **Candidate List** page.

---

## 8. Candidate List & Fundamental Knowledge Assessment

On the **Candidate List** page:

- You'll see a card per candidate showing:
  - Name and CV filtering score (from step 7)
  - Fundamental Knowledge Assessment score (if completed)
- For any candidate, click **"Begin Assessment"** to start the Fundamental Knowledge Assessment.

### 8.1 Fundamental Knowledge Assessment

The Fundamental Knowledge Assessment is a **mandatory step** before proceeding to the voice interview. It evaluates essential technical knowledge through text-based questions.

**Assessment Process:**

1. **Question Generation**
   - Questions are automatically generated based on the Job Description and role
   - Default: 5 questions (configurable via sidebar: 1-10 questions)
   - Questions are tailored to the specific role (e.g., Frontend Developer, Data Scientist)

2. **Answering Questions**
   - Candidate answers each question in text format
   - Questions cover coding, concepts, and tools/libraries relevant to the role
   - Each question shows type (coding/concept/library) and difficulty level

3. **Evaluation**
   - Answers are evaluated using Groq LLM
   - Scoring criteria:
     - Technical Accuracy (0-100)
     - Completeness (0-100)
     - Relevance to Role (0-100)
     - Practical Knowledge (0-100)
   - Overall score: Average of all criteria (0-100)

4. **Results & Next Steps**
   - **If score ≥ 80**: Candidate can proceed to voice interview
   - **If score < 80**: Candidate receives feedback and cannot proceed
   - Results are automatically saved to the Excel file with columns:
     - `Fundamental Knowledge Score`
     - `Fundamental Recommendation`
     - `Fundamental Assessment Date`
     - `Fundamental Question Scores`

**Important:** Candidates must achieve a minimum score of **80/100** to proceed to the voice interview stage.

---

## 9. Voice Interview Page – Voice‑Based Technical Interview

**Prerequisite:** Candidate must have completed Fundamental Knowledge Assessment with a score ≥ 80/100.

After successfully completing the Fundamental Knowledge Assessment, candidates can proceed to the voice interview stage.

### 9.1 Sidebar Settings

- **Interviewer Mode**: `friendly`, `formal`, or `technical`
- **Number of Technical Questions** and **Follow‑up Questions**
- **Speech‑to‑Text Engine**:
  - Whisper Tiny/Base/Small/Medium/Large (local, via `openai-whisper`)
  - AssemblyAI (cloud; requires `ASSEMBLYAI_API_KEY`)
- **Optional Questions PDF**:
  - Upload a PDF with custom interview questions if desired.

### 9.2 Interview Flow

- The AI recruiter introduces the interview (audio + text).
- At the bottom, use the **microphone widget** to record your spoken answers.
- The app:
  - Records audio
  - Transcribes it using the selected STT model
  - Sends it to the LLM workflow
  - Plays back the recruiter's next question/response via TTS

The app automatically logs **timings** (generation, TTS, playback, STT) and creates **time analysis PDFs** under `Time Ananlysis Reports/`.

When the interview ends (the AI says something like "that's it for today"), you'll see an option to **generate evaluation and HR report**.

---

## 10. Evaluation, Reports, and Exports

After the interview finishes:

- Click **"📊 Generate Evaluation and Report"**.
- The workflow will:
  - Analyze the candidate's performance
  - Generate a detailed **evaluation text**
  - Create an **HR report PDF** saved in `generated_reports/`
- If available, a **Download PDF Report** button will appear in the UI.
- Time analysis PDFs are created automatically in `Time Ananlysis Reports/` (for before/after or per‑interview timing).

---

## 11. Team Git Workflow (Collaboration)

For collaboration on GitHub, see `GITHUB_SETUP.md` in this repo. In summary:

- **Get the latest changes** on your existing clone:
  - `git checkout main`                # switch to main branch
  - `git pull origin main`             # pull latest from GitHub


- **Make changes and push**:
  - `git add .`
  - `git commit -m "Clear description of your changes"`
  - `git push -u origin feature/your-feature-name`

---

## 12. Quick Troubleshooting

- **`GOOGLE_API_KEY environment variable is not set`**
  - Check that `.env` exists in the project root and contains `GOOGLE_API_KEY=...`.
  - Get your key from: https://makersuite.google.com/app/apikey
  - Restart the terminal after editing `.env` if necessary.

- **`GROQ_API_KEY not found`**
  - Check that `.env` exists and contains `GROQ_API_KEY=...`.
  - Get your key from: https://console.groq.com/keys
  - Fundamental Knowledge Assessment will not work without this key.

- **App doesn't open**
  - Confirm virtual env is active.
  - Run `python run_all.py` from the project root.

- **No CVs found**
  - Check that the directory path is correct and contains `.pdf` files.

- **Fundamental Assessment questions not generating**
  - Verify `GROQ_API_KEY` is set correctly in `.env`
  - Check your Groq API quota/limits at https://console.groq.com
  - The system will use fallback questions if generation fails

- **Cannot proceed to interview after assessment**
  - Ensure the candidate scored ≥ 80/100 in Fundamental Knowledge Assessment
  - Check the assessment results page for the exact score
  - Candidates with scores below 80 cannot proceed (by design)

- **Whisper / audio errors**
  - Make sure `ffmpeg` is installed on your system if Whisper or `pydub` complain.
  - On Windows, you may need to add `ffmpeg` to your PATH.

If your team runs into any other setup issues, capture the exact error message and command you ran, and you can update this README with additional hints as needed.

