"""
Simulates the CV Filtering Dashboard's loadDashboard() logic.
Calls the same APIs the GUI uses and verifies the response shape and values
that would be rendered (validatedCount, jdPreviewTitle, candidates list, etc.).
Run with the app on http://127.0.0.1:8001 (python run_all.py).
"""
import urllib.request
import json
import sys

BASE = "http://127.0.0.1:8001"
FAIL = False

def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read().decode())
    except Exception as e:
        return None, str(e)

def main():
    global FAIL
    print("Checking dashboard APIs (same as GUI loadDashboard())...\n")

    # 1) GET /api/cv_filter/latest -> validatedCount, jdPreviewTitle, jdPreviewBody, lastUpdateTime
    code, data = get("/api/cv_filter/latest?_t=1")
    if code != 200:
        print(f"FAIL: /api/cv_filter/latest returned {code} or error: {data}")
        FAIL = True
    else:
        count = data.get("total_resumes")
        jd_title = data.get("jd_title")
        jd_preview = data.get("jd_preview")
        ts = data.get("timestamp")
        print(f"[latest] validatedCount would show: {count}")
        print(f"[latest] jdPreviewTitle would show: {jd_title!r}")
        print(f"[latest] jdPreviewBody length: {len(jd_preview or '')} chars")
        print(f"[latest] lastUpdateTime would use timestamp: {ts}")
        if count is None:
            print("  WARN: total_resumes missing")
            FAIL = True
        print()

    # 2) GET /api/cv_filter/candidates?limit=5 -> candidateList items (First Name, Last Name, Overall Fit)
    code, data = get("/api/cv_filter/candidates?limit=5")
    if code != 200:
        print(f"FAIL: /api/cv_filter/candidates returned {code} or error: {data}")
        FAIL = True
    else:
        candidates = data.get("candidates") or []
        print(f"[candidates] candidateList would have {len(candidates)} item(s)")
        for i, c in enumerate(candidates):
            name = ((c.get("First Name") or "") + " " + (c.get("Last Name") or "")).strip() or "Unnamed"
            score = c.get("Overall Fit") if c.get("Overall Fit") is not None else "N/A"
            print(f"  [{i+1}] name={name!r}, Overall Fit={score}")
        if not candidates:
            print("  WARN: no candidates (list empty or key missing)")
        print()

    if FAIL:
        print("Result: GUI would NOT update correctly (see FAILs above).")
        sys.exit(1)
    print("Result: GUI would update correctly (validatedCount, JD preview, last update time, candidate list).")
    sys.exit(0)

if __name__ == "__main__":
    main()
