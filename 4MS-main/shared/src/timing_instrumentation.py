# timing_instrumentation.py
import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

# Use a project-relative directory for time analysis reports so it works on any machine.
TIME_REPORT_DIR = os.path.join(os.getcwd(), "Time Ananlysis Reports")
os.makedirs(TIME_REPORT_DIR, exist_ok=True)

@dataclass
class StepTiming:
    turn: int
    step: str
    start: float
    end: float
    duration_s: float
    meta: Dict[str, Any]

def now_perf() -> float:
    return time.perf_counter()

def timing_start(step: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"step": step, "t0": now_perf(), "meta": (meta or {})}

def timing_end(token: Dict[str, Any], turn: int) -> StepTiming:
    t1 = now_perf()
    return StepTiming(
        turn=turn,
        step=token["step"],
        start=token["t0"],
        end=t1,
        duration_s=round(t1 - token["t0"], 4),
        meta=token["meta"],
    )

def ensure_session(scoped_state) -> None:
    if "timings" not in scoped_state:
        scoped_state["timings"] = []  # list[StepTiming]
    if "turn_idx" not in scoped_state:
        scoped_state["turn_idx"] = 0
    if "interview_started_at" not in scoped_state:
        scoped_state["interview_started_at"] = time.time()
