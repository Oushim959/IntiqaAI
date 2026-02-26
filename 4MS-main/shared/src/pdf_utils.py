# pdf_utils_FIXED_HTML_PARSING.py - FIX HTML PARSING ERROR IN PDF

import os
from datetime import datetime, timedelta
import pytz
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, KeepTogether, Preformatted, HRFlowable
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY


def get_current_date_4ms():
    """Get current date in UTC+3 timezone"""
    try:
        tz = pytz.timezone('Asia/Kuwait')  # UTC+3
        current = datetime.now(tz)
        return current.strftime("%d %B %Y")
    except:
        utc_now = datetime.utcnow()
        local_time = utc_now + timedelta(hours=3)
        return local_time.strftime("%d %B %Y")


def get_current_datetime_4ms():
    """Get current date and time in UTC+3"""
    try:
        tz = pytz.timezone('Asia/Kuwait')  # UTC+3
        current = datetime.now(tz)
        return current.strftime("%d %B %Y, %H:%M")
    except:
        utc_now = datetime.utcnow()
        local_time = utc_now + timedelta(hours=3)
        return local_time.strftime("%d %B %Y, %H:%M")


def sanitize_html_text(text):
    """
    Sanitize text for safe HTML parsing in ReportLab
    Fixes mismatched tags and escapes special characters
    """
    if not text:
        return ""
    
    # Escape special HTML characters (but preserve markdown markers)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Replace markdown bold with HTML (use regex for proper pairing)
    # This handles **text** → <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Replace markdown italic with HTML (use regex for proper pairing)
    # This handles *text* → <i>text</i>
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # Unescape HTML tags we just created
    text = text.replace("&lt;b&gt;", "<b>")
    text = text.replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>")
    text = text.replace("&lt;/i&gt;", "</i>")
    text = text.replace("&lt;br/&gt;", "<br/>")
    text = text.replace("&lt;br &gt;", "<br/>")
    
    return text


def validate_html_tags(text):
    """
    Validate that HTML tags are properly closed
    Returns fixed text or original if validation fails
    """
    # Count opening and closing tags
    open_b = text.count("<b>")
    close_b = text.count("</b>")
    open_i = text.count("<i>")
    close_i = text.count("</i>")
    
    # If unmatched, remove problematic tags
    if open_b != close_b:
        text = re.sub(r'</?b>', '', text)
    if open_i != close_i:
        text = re.sub(r'</?i>', '', text)
    
    return text


class MarkdownToPDF:
    """Convert markdown-style text to professional PDF format"""
    
    @staticmethod
    def format_content(content, styles):
        """Format content with proper markdown handling"""
        story = []
        
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                story.append(Spacer(1, 0.1*inch))
                i += 1
                continue
            
            try:
                # Heading 1: #
                if line.startswith('# '):
                    text = line[2:].strip()
                    text = sanitize_html_text(text)
                    story.append(Paragraph(f"<b>{text}</b>", styles['heading1']))
                    story.append(Spacer(1, 0.15*inch))
                
                # Heading 2: ##
                elif line.startswith('## '):
                    text = line[3:].strip()
                    text = sanitize_html_text(text)
                    story.append(Paragraph(f"<font color='#667eea'><b>{text}</b></font>", styles['heading2']))
                    story.append(Spacer(1, 0.1*inch))
                
                # Heading 3: ###
                elif line.startswith('### '):
                    text = line[4:].strip()
                    text = sanitize_html_text(text)
                    story.append(Paragraph(f"<b>{text}</b>", styles['heading3']))
                    story.append(Spacer(1, 0.08*inch))
                
                # Bullet point: -
                elif line.startswith('- '):
                    text = line[2:].strip()
                    text = sanitize_html_text(text)
                    bullet_text = f"• {text}"
                    story.append(Paragraph(bullet_text, styles['bullet']))
                    story.append(Spacer(1, 0.06*inch))
                
                # Numbered list: 1.
                elif line and line[0].isdigit() and '. ' in line:
                    text = sanitize_html_text(line)
                    story.append(Paragraph(text, styles['bullet']))
                    story.append(Spacer(1, 0.06*inch))
                
                # Regular paragraph
                else:
                    text = sanitize_html_text(line)
                    text = validate_html_tags(text)
                    if text:  # Only add if not empty after validation
                        story.append(Paragraph(text, styles['body']))
                        story.append(Spacer(1, 0.06*inch))
            
            except Exception as e:
                # If line fails to parse, try as plain text
                try:
                    text = sanitize_html_text(line)
                    text = validate_html_tags(text)
                    story.append(Paragraph(text, styles['body']))
                    story.append(Spacer(1, 0.06*inch))
                except:
                    # Skip problematic lines
                    pass
            
            i += 1
        
        return story


def create_professional_styles():
    """Create professional styles for PDF"""
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=18,
        spaceBefore=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Heading 1
    heading1_style = ParagraphStyle(
        'CustomHeading1',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # Heading 2
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    # Heading 3
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=8,
        spaceBefore=8,
        fontName='Helvetica-Bold'
    )
    
    # Body text (justified)
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=8,
        spaceBefore=2,
        alignment=TA_JUSTIFY,
        fontName='Helvetica',
        textColor=colors.HexColor('#333333'),
        leading=16
    )
    
    # Bullet points
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6,
        spaceBefore=2,
        alignment=TA_LEFT,
        fontName='Helvetica',
        textColor=colors.HexColor('#333333'),
        leftIndent=20,
        leading=14
    )
    
    # Footer text
    footer_style = ParagraphStyle(
        'CustomFooter',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceAfter=3,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    return {
        'title': title_style,
        'heading1': heading1_style,
        'heading2': heading2_style,
        'heading3': heading3_style,
        'body': body_style,
        'bullet': bullet_style,
        'footer': footer_style
    }


def generate_pdf(content, filename="HR_Report.pdf"):
    """Generate professional PDF report with proper HTML parsing"""
    
    # Create generated_reports directory if it doesn't exist
    reports_dir = "shared/generated_reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    # Save PDF in generated_reports directory
    pdf_path = os.path.join(reports_dir, filename)
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    story = []
    styles = create_professional_styles()
    
    # Header
    story.append(Paragraph("HR INTERVIEW REPORT", styles['title']))
    story.append(Spacer(1, 0.2*inch))
    
    # Add horizontal line
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#667eea')))
    story.append(Spacer(1, 0.2*inch))
    
    # Parse and format content with proper HTML sanitization
    formatter = MarkdownToPDF()
    formatted_content = formatter.format_content(content, styles)
    story.extend(formatted_content)
    
    # Footer separator
    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 0.15*inch))
    
    # Footer with IntiqAI branding
    footer_content = f"""
    <b>Report Prepared By:</b><br/>
    IntiqAI - AI Recruitment System<br/>
    <br/>
    <b>Report Generated:</b> {get_current_datetime_4ms()}<br/>
    <b>Timezone:</b> UTC+3 (Gulf Standard Time)<br/>
    <b>System:</b> IntiqAI v1.0
    """
    
    story.append(Paragraph(footer_content, styles['footer']))
    
    # Build PDF
    doc.build(story)
    return pdf_path
