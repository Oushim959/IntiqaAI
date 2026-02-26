# src/pdf_utils_time_analysis.py
import os
from typing import List
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from shared.src.timing_instrumentation import StepTiming, TIME_REPORT_DIR

def generate_time_analysis_pdf(candidate_name: str,
                               position: str,
                               timings: List[StepTiming],
                               dt_display_local: str,
                               tz_label: str = "UTC+3") -> str:
    os.makedirs(TIME_REPORT_DIR, exist_ok=True)
    safe = f"{candidate_name} - {dt_display_local}".replace(":", "-").replace("/", "-")
    pdf_path = os.path.join(TIME_REPORT_DIR, f"{safe}.pdf")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#2c3e50'))
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#667eea'))
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=10, leading=14)

    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    story.append(Paragraph("IntiqAI – Time Analysis Report", h1))
    story.append(Paragraph(f"Candidate: {candidate_name}", body))
    story.append(Paragraph(f"Position: {position}", body))
    story.append(Paragraph(f"Interview Timestamp: {dt_display_local} ({tz_label})", body))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#667eea')))
    story.append(Spacer(1, 10))

    import statistics
    def pick(step): return [t.duration_s for t in timings if t.step == step]
    labels = ["stt_transcribe", "ai_generation", "tts_generate", "playback_wait"]
    rows = [["Step", "Count", "Min (s)", "Avg (s)", "Max (s)", "Total (s)"]]
    total_all = 0.0
    for lb in labels:
        ds = pick(lb)
        if ds:
            rows.append([lb, len(ds), f"{min(ds):.3f}", f"{statistics.mean(ds):.3f}", f"{max(ds):.3f}", f"{sum(ds):.3f}"])
            total_all += sum(ds)
        else:
            rows.append([lb, 0, "-", "-", "-", "0.000"])

    tbl = Table(rows, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f0f3ff')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#d0d7ff')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
    ]))
    story.append(Paragraph("Summary by category", h2))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # Detailed timeline
    rows2 = [["Turn", "Step", "Duration (s)", "Meta"]]
    for t in timings:
        rows2.append([t.turn, t.step, f"{t.duration_s:.3f}", str(t.meta)])
    tbl2 = Table(rows2, hAlign="LEFT", colWidths=[50, 140, 80, 260])
    tbl2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f7f7f7')),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#dddddd')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ]))
    story.append(Paragraph("Detailed timeline", h2))
    story.append(tbl2)
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
    story.append(Paragraph(f"Total timed seconds (approx.): {total_all:.3f}", body))
    story.append(Paragraph("Prepared by: IntiqAI – AI Recruitment System", body))
    doc.build(story)
    return pdf_path
