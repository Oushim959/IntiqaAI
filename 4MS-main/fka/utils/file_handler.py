import json
import os
from datetime import datetime
from typing import Dict

class FileHandler:
    def __init__(self, data_dir="interviews"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def save_interview(self, interview_data: Dict) -> str:
        """Save interview results to file"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Use a sanitized role string for the filename
        role_raw = interview_data.get('role', 'unknown').lower()
        role_safe = "".join(c for c in role_raw if c.isalnum() or c in (' ', '_')).replace(' ', '_')
        
        filename = f"interview_{role_safe}_{timestamp}.json"
        filepath = os.path.join(self.data_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(interview_data, f, indent=2, ensure_ascii=False)
        
        return filename
    
    def load_interview(self, filename: str) -> Dict:
        """Load specific interview file"""
        filepath = os.path.join(self.data_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
