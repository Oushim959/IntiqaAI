import os
import json
from typing import List, Dict

class AnalyticsEngine:
    def __init__(self, data_dir="interviews"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def load_all_interviews(self) -> List[Dict]:
        """Load all previous interviews"""
        interviews = []
        for file in os.listdir(self.data_dir):
            if file.startswith('interview_') and file.endswith('.json'):
                try:
                    with open(os.path.join(self.data_dir, file), 'r', encoding='utf-8') as f:
                        interviews.append(json.load(f))
                except Exception:
                    continue
        return interviews
    
    def generate_comparative_analytics(self, interviews: List[Dict]):
        """Generate comparative analytics across interviews"""
        if len(interviews) < 2:
            print("\n📈 Collect more interviews to enable comparative analytics")
            return
        
        print(f"\n{'='*50}")
        print("COMPARATIVE ANALYTICS")
        print(f"{'='*50}")
        
        print(f"\nTotal Interviews Conducted: {len(interviews)}")
        
        # Calculate statistics
        avg_scores = [interview['evaluation']['overall_score'] for interview in interviews]
        
        print(f"Average Fundamental Score: {sum(avg_scores)/len(avg_scores):.1f}/100")
        print(f"Best Score: {max(avg_scores)}/100")
        print(f"Lowest Score: {min(avg_scores)}/100")
        
        # Score distribution
        print(f"\nScore Distribution:")
        for score_range in ["90-100", "80-89", "70-79", "60-69", "0-59"]:
            count = sum(1 for s in avg_scores if self._in_score_range(s, score_range))
            print(f"  {score_range}: {count} interviews")
        
        # Role analysis
        self._analyze_role_performance(interviews)
    
    def _analyze_role_performance(self, interviews: List[Dict]):
        """Analyze performance by role"""
        print(f"\nPerformance by Role:")
        role_scores = {}
        
        for interview in interviews:
            role = interview['role']
            if role not in role_scores:
                role_scores[role] = []
            role_scores[role].append(interview['evaluation']['overall_score'])
        
        for role, scores in role_scores.items():
            avg = sum(scores) / len(scores)
            print(f"  {role}: {avg:.1f} average score ({len(scores)} interviews)")
    
    def _in_score_range(self, score, score_range_str):
        """Helper to check if score is in range string (e.g., '80-89')"""
        low, high = map(int, score_range_str.split('-'))
        return low <= score <= high
