import json
from groq import Groq

class QuestionGenerator:
    def __init__(self, api_key, model=None):
        self.client = Groq(api_key=api_key)
        # Use the provided model or default to llama-3.1-8b-instant
        self.model = model if model else "llama-3.1-8b-instant"
    
    def _detect_categories(self, role: str, job_description: str) -> list:
        """Ask the LLM to choose 3 relevant question categories based on the job."""
        prompt = f"""Given this job role and description, choose exactly 3 question categories that best assess a candidate's fitness.

Role: {role}
Job Description (excerpt): {job_description[:1000]}

Rules:
- If the role involves writing code (developer, engineer, programmer), one category MUST be "Coding" (hands-on code-writing).
- If the role does NOT involve writing code, do NOT include "Coding". Use practical skill categories instead.
- Always include "Concept" for domain knowledge.
- The third category should be "Scenario" (situational/problem-solving).
- For non-technical roles, replace "Coding" with a relevant practical category (e.g. "Data Analysis", "Design Thinking", "Communication", "Project Management", etc.).

Return JSON:
{{
  "categories": ["category1", "category2", "category3"]
}}"""
        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You select assessment categories for job interviews."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            data = json.loads(completion.choices[0].message.content)
            cats = data.get("categories", [])
            if isinstance(cats, list) and len(cats) >= 2:
                return cats[:3]
        except Exception as e:
            print(f"Error detecting categories: {e}")
        
        # Fallback: detect from role name
        role_lower = role.lower()
        if any(kw in role_lower for kw in ['developer', 'engineer', 'programmer', 'software', 'backend', 'frontend', 'fullstack']):
            return ["Coding", "Concept", "Scenario"]
        elif any(kw in role_lower for kw in ['data', 'analyst', 'scientist', 'ml', 'ai']):
            return ["Data Analysis", "Concept", "Scenario"]
        elif any(kw in role_lower for kw in ['design', 'ui', 'ux']):
            return ["Design Thinking", "Concept", "Scenario"]
        elif any(kw in role_lower for kw in ['manager', 'lead', 'director']):
            return ["Leadership", "Concept", "Scenario"]
        else:
            return ["Practical Skills", "Concept", "Scenario"]

    def generate_fka_pool(self, role: str, job_description: str) -> dict:
        """
        Generate a pool of FKA questions for the run.
        Categories are dynamically determined based on the job.
        """
        import uuid
        categories = self._detect_categories(role, job_description)
        pool = {}
        
        for cat in categories:
            # Use different prompts based on category type
            if cat.lower() == "coding":
                prompt = f"""Generate 5 coding questions for a {role} position.
                
Job Description: {job_description[:1500]}

IMPORTANT: Each question MUST require the candidate to write actual code (Python, JavaScript, SQL, etc.).

RULES for questions:
1. Every question MUST be self-contained. 
2. Do NOT refer to "the following code snippet" or "this code" unless you fully include the code inside the question text itself.
3. Do NOT refer to external databases or schemas unless you describe a simple schema within the question text.
4. Stick to "Write a function that...", "Implement an algorithm to...", "Write a SQL query to..." style questions.

Return JSON format:
{{
  "questions": [
    {{
      "text": "Write a Python function that takes a list of integers and returns the second largest element. Handle edge cases like duplicates and lists with fewer than 2 elements.",
      "category": "Coding",
      "type": "coding",
      "difficulty": "intermediate"
    }}
  ]
}}"""
            else:
                prompt = f"""Generate 5 {cat} questions for a {role} position.
                
Job Description: {job_description[:1500]}

Focus on fundamental knowledge suitable for a written assessment.
Questions should be specific to the role and job description.
Keep questions concise but thoughtful.

RULES:
1. Every question MUST be self-contained.
2. ONLY generate open-ended or explanatory questions. 
3. NEVER generate multiple-choice questions (e.g., do NOT use "Which of the following...").
4. NEVER refer to non-existent diagrams, schemas, or data.

Return JSON format:
{{
  "questions": [
    {{
      "text": "Explain the difference between a process and a thread in the context of a high-concurrency web application.",
      "category": "{cat}",
      "type": "text",
      "difficulty": "intermediate"
    }}
  ]
}}"""
            try:
                completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a technical recruiter generating assessment questions."},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.model,
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                data = json.loads(completion.choices[0].message.content)
                qs = data.get("questions", [])
                for q in qs:
                    q["id"] = uuid.uuid4().hex[:8]
                    q["must_ask"] = False
                    q["category"] = cat
                pool[cat] = qs
            except Exception as e:
                print(f"Error generating {cat} pool: {e}")
                pool[cat] = []
        
        return pool

    def generate_interview_pool(self, role: str, job_description: str) -> dict:
        """
        Generate a pool of Interview questions for the run.
        Categories are dynamically determined based on the job.
        """
        import uuid
        categories = self._detect_categories(role, job_description)
        pool = {}
        
        for cat in categories:
            if cat.lower() == "coding":
                prompt = f"""Generate 5 coding-related interview discussion questions for a {role} position.
                
Job Description: {job_description[:1500]}

These are verbal interview questions about coding practices, architecture decisions, and technical problem-solving.
Ask about their approach, not to write code on the spot.

RULES:
1. Every question MUST be self-contained.
2. NEVER refer to "the code above", "this snippet", or any non-existent context.
3. Questions should spark deep technical discussion.

Return JSON format:
{{
  "questions": [
    {{
      "text": "How would you design a scalable microservices architecture for a real-time chat application using WebSockets?",
      "category": "Coding",
      "type": "verbal",
      "difficulty": "intermediate"
    }}
  ]
}}"""
            else:
                prompt = f"""Generate 5 {cat} interview questions for a {role} position.
                
Job Description: {job_description[:1500]}

Focus on verbal interview questions that spark discussion.
Keep questions open-ended but specific to the role.

RULES:
1. Every question MUST be self-contained.
2. NEVER generate multiple-choice style questions.
3. NEVER refer to non-existent schemas, diagrams, or lists.

Return JSON format:
{{
  "questions": [
    {{
      "text": "Tell me about a time you had to optimize a slow database query. What was your process and what tools did you use?",
      "category": "{cat}",
      "type": "verbal",
      "difficulty": "intermediate"
    }}
  ]
}}"""
            try:
                completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a technical interviewer generating interview questions."},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.model,
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                data = json.loads(completion.choices[0].message.content)
                qs = data.get("questions", [])
                for q in qs:
                    q["id"] = uuid.uuid4().hex[:8]
                    q["must_ask"] = False
                    q["category"] = cat
                pool[cat] = qs
            except Exception as e:
                print(f"Error generating {cat} interview pool: {e}")
                pool[cat] = []
        
        return pool

    
    def _get_fallback_questions(self, role):
        """Fallback fundamental questions"""
        role_lower = role.lower()
        
        if any(keyword in role_lower for keyword in ['engineer', 'developer', 'programmer', 'software']):
            return [
                {
                    "question": "Write a function to find the maximum value in a list/array.",
                    "type": "coding",
                    "difficulty": "basic",
                    "expected_keywords": ["function", "loop", "max", "array", "iterate"]
                },
                {
                    "question": "What is the difference between a list and a tuple in Python?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["mutable", "immutable", "modifiable", "fixed"]
                },
                {
                    "question": "Explain what a REST API is and give an example HTTP method.",
                    "type": "concept",
                    "difficulty": "intermediate",
                    "expected_keywords": ["representational", "state", "transfer", "http", "get", "post"]
                },
                {
                    "question": "What is SQL injection and how can it be prevented?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["parameterized", "queries", "input", "validation", "sanitize"]
                },
                {
                    "question": "Name three HTTP status codes and their meanings.",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["200", "404", "500", "ok", "not found", "error"]
                }
            ]
        elif any(keyword in role_lower for keyword in ['data', 'analyst', 'scientist', 'ml', 'ai']):
            return [
                {
                    "question": "What is the difference between supervised and unsupervised learning?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["labeled", "unlabeled", "classification", "clustering"]
                },
                {
                    "question": "Explain what overfitting is and one way to prevent it.",
                    "type": "concept",
                    "difficulty": "intermediate",
                    "expected_keywords": ["regularization", "cross-validation", "training", "test"]
                },
                {
                    "question": "What is a JOIN in SQL and explain INNER JOIN vs LEFT JOIN.",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["combine", "tables", "matching", "all rows"]
                },
                {
                    "question": "What is the difference between classification and regression?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["categorical", "continuous", "discrete", "predict"]
                },
                {
                    "question": "Why is feature scaling important in machine learning?",
                    "type": "concept",
                    "difficulty": "intermediate",
                    "expected_keywords": ["normalization", "standardization", "scale", "algorithms"]
                }
            ]
        elif any(keyword in role_lower for keyword in ['frontend', 'ui', 'ux', 'web']):
            return [
                {
                    "question": "What is the difference between HTML and HTML5?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["semantic", "elements", "audio", "video", "canvas"]
                },
                {
                    "question": "Explain the CSS box model.",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["margin", "border", "padding", "content"]
                },
                {
                    "question": "What is the difference between == and === in JavaScript?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["equality", "strict", "type", "coercion"]
                },
                {
                    "question": "What is React and why is it popular?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["components", "virtual dom", "state", "props"]
                },
                {
                    "question": "What are CSS media queries used for?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["responsive", "design", "breakpoints", "screen size"]
                }
            ]
        else:
            return [
                {
                    "question": "Based on the job description, what are the most important skills for this role?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": []
                },
                {
                    "question": "What tools or technologies mentioned are you familiar with?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": []
                },
                {
                    "question": "Describe a time you had to learn a new technology quickly.",
                    "type": "concept",
                    "difficulty": "intermediate",
                    "expected_keywords": ["learning", "adaptation", "project", "research"]
                },
                {
                    "question": "How do you stay updated with industry trends?",
                    "type": "concept",
                    "difficulty": "basic",
                    "expected_keywords": ["blogs", "courses", "conferences", "networking"]
                },
                {
                    "question": "What is your approach to debugging or problem-solving?",
                    "type": "concept",
                    "difficulty": "intermediate",
                    "expected_keywords": ["methodical", "testing", "isolate", "document"]
                }
            ]
