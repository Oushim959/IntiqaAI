import PyPDF2
import docx
import re
from typing import Dict, Any
import io

class JDParser:
    """Parse Job Description files from various formats"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.docx', '.txt']
    
    def parse_uploaded_file(self, file) -> str:
        """Parse uploaded file based on file type"""
        file_type = self._get_file_type(file.name)
        
        try:
            if file_type == '.pdf':
                return self.parse_pdf(file)
            elif file_type == '.docx':
                return self.parse_docx(file)
            elif file_type == '.txt':
                return self.parse_text(file)
            else:
                raise ValueError(f"Unsupported file format: {file_type}")
        except Exception as e:
            raise Exception(f"Error parsing file: {str(e)}")
    
    def _get_file_type(self, filename: str) -> str:
        """Extract file extension"""
        return '.' + filename.split('.')[-1].lower()
    
    def parse_pdf(self, file) -> str:
        """Extract text from PDF file"""
        try:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return self.clean_jd_text(text)
        except Exception as e:
            raise Exception(f"PDF parsing failed: {str(e)}")
    
    def parse_docx(self, file) -> str:
        """Extract text from Word document"""
        try:
            doc = docx.Document(io.BytesIO(file.getvalue()))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return self.clean_jd_text(text)
        except Exception as e:
            raise Exception(f"DOCX parsing failed: {str(e)}")
    
    def parse_text(self, file) -> str:
        """Read text file"""
        try:
            text = file.getvalue().decode('utf-8')
            return self.clean_jd_text(text)
        except Exception as e:
            raise Exception(f"Text file reading failed: {str(e)}")
    
    def clean_jd_text(self, raw_text: str) -> str:
        """Clean and normalize JD text"""
        # Remove excessive whitespace
        cleaned = re.sub(r'\n\s*\n', '\n\n', raw_text)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        # Remove common PDF artifacts
        cleaned = re.sub(r'\x0c', '', cleaned)  # Form feeds
        cleaned = re.sub(r'\s+$', '', cleaned, flags=re.MULTILINE)  # Trailing whitespace
        
        return cleaned.strip()
    
    def detect_job_role(self, jd_text: str) -> str:
        """
        Detect and extract the job role from JD text.
        Returns the most specific job title found.
        """
        if not jd_text:
            return "Software Engineer"
        
        # Common job title patterns
        title_patterns = [
            r'(?:Senior|Lead|Principal|Staff)\s+([A-Za-z\s]+?(?:Engineer|Developer|Architect|Data Scientist|Analyst))',
            r'([A-Za-z\s]+?(?:Engineer|Developer|Architect|Data Scientist|Analyst))\s+(?:\(?(?:Senior|Lead|Principal|Staff)\)?)',
            r'Job Title:\s*([^\n]+)',
            r'Position:\s*([^\n]+)',
            r'Role:\s*([^\n]+)',
            r'([A-Z][a-z]+\s+(?:Software|Data|ML|AI|Backend|Frontend|Full.?Stack)\s+(?:Engineer|Developer))',
            r'(?:We are looking for|Seeking|Hiring)\s+a\s+([A-Za-z\s]+?(?:Engineer|Developer|Architect))',
        ]
        
        # Look for the most specific match
        best_match = "Software Engineer"  # Default fallback
        
        for pattern in title_patterns:
            matches = re.findall(pattern, jd_text, re.IGNORECASE | re.MULTILINE)
            if matches:
                # Take the first match and clean it up
                candidate = matches[0].strip()
                if self._is_valid_job_title(candidate):
                    best_match = candidate
                    break
        
        # If no specific match found, try to extract from the first few lines
        if best_match == "Software Engineer":
            first_lines = jd_text[:500]  # Look at first 500 characters
            words = first_lines.split()
            title_keywords = []
            
            for i, word in enumerate(words):
                if word.lower() in ['engineer', 'developer', 'architect', 'scientist', 'analyst']:
                    # Get 2-3 words before the title keyword
                    start = max(0, i - 3)
                    end = min(len(words), i + 1)
                    potential_title = ' '.join(words[start:end])
                    if self._is_valid_job_title(potential_title):
                        title_keywords.append(potential_title)
            
            if title_keywords:
                best_match = title_keywords[0]
        
        return self._normalize_job_title(best_match)
    
    def _is_valid_job_title(self, title: str) -> bool:
        """Check if the extracted title seems like a valid job title"""
        if len(title) < 3 or len(title) > 60:
            return False
        
        # Should contain at least one professional keyword
        professional_keywords = [
            'engineer', 'developer', 'architect', 'scientist', 'analyst',
            'manager', 'specialist', 'consultant', 'lead', 'principal', 'staff'
        ]
        
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in professional_keywords)
    
    def _normalize_job_title(self, title: str) -> str:
        """Normalize job title formatting"""
        # Remove extra spaces and weird characters
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Capitalize properly (Title Case for job titles)
        words = title.split()
        if len(words) > 1:
            # Keep common acronyms uppercase
            acronyms = {'AI', 'ML', 'API', 'SDK', 'UI', 'UX', 'QA', 'SRE', 'DevOps'}
            title = ' '.join(
                word.upper() if word.upper() in acronyms else word.title() 
                for word in words
            )
        else:
            title = title.title()
        
        return title
    
    def validate_jd_quality(self, jd_text: str) -> Dict[str, Any]:
        """Validate if JD has sufficient technical detail"""
        word_count = len(jd_text.split())
        
        # Check for key sections
        has_requirements = any(keyword in jd_text.lower() for keyword in 
                             ['requirement', 'qualification', 'skill', 'experience'])
        has_responsibilities = any(keyword in jd_text.lower() for keyword in 
                                 ['responsibilit', 'duties', 'role'])
        
        # Technical keywords check
        technical_keywords = ['develop', 'engineer', 'design', 'system', 'software', 
                            'code', 'technical', 'architecture', 'framework']
        tech_word_count = sum(1 for word in technical_keywords if word in jd_text.lower())
        
        quality_score = min(100, (word_count / 3) + (tech_word_count * 5))
        
        suggestions = []
        if word_count < 100:
            suggestions.append("JD seems quite brief - consider adding more detail")
        if not has_requirements:
            suggestions.append("Consider adding a 'Requirements' or 'Qualifications' section")
        if not has_responsibilities:
            suggestions.append("Consider adding a 'Responsibilities' section")
        
        # Detect job role
        detected_role = self.detect_job_role(jd_text)
        
        return {
            "word_count": word_count,
            "quality_score": quality_score,
            "has_requirements": has_requirements,
            "has_responsibilities": has_responsibilities,
            "technical_keywords_found": tech_word_count,
            "is_sufficient": quality_score > 40,
            "suggestions": suggestions,
            "detected_role": detected_role
        }
