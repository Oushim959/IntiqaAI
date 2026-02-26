import json
import time
from groq import Groq

class EvaluationEngine:
    def __init__(self, api_key, model=None):
        self.client = Groq(api_key=api_key)
        # Use the provided model or default to llama-3.1-8b-instant
        self.model = model if model else "llama-3.1-8b-instant"
    
    def evaluate_fundamental_responses(self, role: str, job_description: str, questions: list, responses: list):
        """Evaluate fundamental knowledge responses"""
        
        # First calculate question scores
        question_scores = self._calculate_question_scores(questions, responses)
        calculated_overall = question_scores.get('OVERALL', 70)
        
        # Build the evaluation prompt
        prompt = self._build_evaluation_prompt(role, job_description, questions, responses, calculated_overall)
        
        try:
            print(f"Evaluating responses using {self.model}...")
            start_time = time.time()
            
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a technical interviewer evaluating fundamental knowledge. The calculated score is {calculated_overall}/100. Be fair, specific, and constructive."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            evaluation_time = time.time() - start_time
            
            response_text = chat_completion.choices[0].message.content
            evaluation = self._parse_evaluation_response(response_text)
            
            # Override overall_score with calculated score
            evaluation['overall_score'] = calculated_overall
            
            # Ensure recommendation matches calculated score
            if calculated_overall >= 85:
                evaluation['recommendation'] = 'Strong Yes'
            elif calculated_overall >= 70:
                evaluation['recommendation'] = 'Yes'
            elif calculated_overall >= 60:
                evaluation['recommendation'] = 'No'
            else:
                evaluation['recommendation'] = 'Strong No'
            
            evaluation['evaluation_time_seconds'] = evaluation_time
            evaluation['interviewer_used'] = "Fundamental Knowledge Evaluator"
            
            # Add question scores (remove OVERALL from display)
            display_scores = {k: v for k, v in question_scores.items() if k != 'OVERALL'}
            evaluation['question_scores'] = display_scores
            
            return evaluation
            
        except Exception as e:
            print(f"Evaluation error: {e}")
            return self._fallback_evaluation(questions, responses, e)
    
    def _build_evaluation_prompt(self, role: str, job_description: str, questions: list, responses: list, calculated_score: int):
        """Build prompt for evaluating fundamental knowledge"""
        
        # Create a summary of questions and responses
        qa_summary = ""
        for i, (q, r) in enumerate(zip(questions, responses)):
            qa_summary += f"Question {i+1} ({q['type']}, {q['difficulty']}):\n{q.get('text', '')}\n\n"
            qa_summary += f"Answer:\n{r['response']}\n\n"
            qa_summary += "-" * 40 + "\n\n"
        
        return f"""Evaluate candidate for: {role}

Job Description Summary:
{job_description[:800]}

Candidate's Responses:
{qa_summary}

Evaluation Criteria:
1. Technical Accuracy (0-100)
2. Completeness (0-100)
3. Relevance to Role (0-100)
4. Practical Knowledge (0-100)

The calculated score based on keyword matching is: {calculated_score}/100

Provide specific feedback based on their actual answers.
Reference their responses in your evaluation.
Focus on the quality and depth of their answers.

Return ONLY valid JSON:
{{
  "criterion_scores": {{
    "technical_accuracy": 85,
    "completeness": 80,
    "relevance": 90,
    "practicality": 85
  }},
  "strengths": [
    "Specific strength mentioned in their response",
    "Another concrete strength"
  ],
  "weaknesses": [
    "Specific area needing improvement with suggestion",
    "Another actionable weakness"
  ],
  "qualitative_feedback": "Detailed analysis of their fundamental knowledge. Reference their answers. Be constructive."
}}"""
    
    def _calculate_question_scores(self, questions: list, responses: list):
        """Calculate scores for each question based on keyword matching and answer quality"""
        question_scores = {}
        total_score = 0
        
        for i, (q, r) in enumerate(zip(questions, responses)):
            response_text = r['response'].strip()
            response_lower = response_text.lower()
            expected_keywords = [k.lower() for k in q.get('expected_keywords', [])]
            
            # Base scoring
            if not response_text:  # Empty response
                score = 0
            elif not expected_keywords:
                # No keywords specified, score based on length and quality
                score = self._score_by_length_and_quality(response_text, q['difficulty'])
            else:
                # Calculate keyword score
                found_keywords = sum(1 for keyword in expected_keywords if keyword in response_lower)
                if found_keywords == 0:
                    keyword_score = 40  # Penalty for no keywords found
                else:
                    keyword_score = (found_keywords / len(expected_keywords)) * 100
                
                # Adjust based on answer quality
                quality_multiplier = self._calculate_quality_multiplier(response_text, q['type'], q['difficulty'])
                score = min(100, keyword_score * quality_multiplier)
            
            # Apply difficulty weighting
            if q['difficulty'] == 'intermediate':
                score = min(100, score * 1.1)  # 10% bonus for intermediate
            elif q['difficulty'] == 'advanced':
                score = min(100, score * 1.2)  # 20% bonus for advanced
            
            question_scores[f"Q{i+1}: {q.get('text', '')[:30]}..."] = int(score)
            total_score += score
        
        # Calculate overall average
        if question_scores:
            average_score = total_score / len(question_scores)
            question_scores['OVERALL'] = int(average_score)
        
        return question_scores
    
    def _score_by_length_and_quality(self, response_text: str, difficulty: str) -> float:
        """Score responses without expected keywords"""
        word_count = len(response_text.split())
        
        # Base score based on length
        if word_count == 0:
            return 0
        elif word_count < 10:
            base_score = 30  # Very short answer
        elif word_count < 30:
            base_score = 50  # Short answer
        elif word_count < 100:
            base_score = 70  # Moderate answer
        else:
            base_score = 85  # Detailed answer
        
        # Adjust for difficulty
        if difficulty == 'intermediate':
            return min(100, base_score * 1.1)
        elif difficulty == 'advanced':
            return min(100, base_score * 1.2)
        return base_score
    
    def _calculate_quality_multiplier(self, response_text: str, question_type: str, difficulty: str) -> float:
        """Calculate quality multiplier based on answer characteristics"""
        word_count = len(response_text.split())
        lines = response_text.count('\n') + 1
        multiplier = 1.0
        
        # Length multiplier
        if word_count > 100:
            multiplier *= 1.2  # 20% bonus for detailed answers
        elif word_count > 50:
            multiplier *= 1.1  # 10% bonus for thorough answers
        elif word_count < 20:
            multiplier *= 0.7  # 30% penalty for very short answers
        
        # Formatting bonus
        if question_type == 'coding' and ('function ' in response_text.lower() or 'def ' in response_text.lower() or 'class ' in response_text.lower() or 'return ' in response_text.lower()):
            multiplier *= 1.15  # 15% bonus for actual code
        
        if 'example' in response_text.lower() or 'e.g.' in response_text.lower() or 'for example' in response_text.lower():
            multiplier *= 1.1  # 10% bonus for providing examples
        
        if lines > 5:  # Well-structured answer with multiple lines
            multiplier *= 1.05
        
        # Code formatting bonus
        if '```' in response_text or 'code' in response_text.lower():
            multiplier *= 1.05
        
        return multiplier
    
    def _parse_evaluation_response(self, response_text):
        """Parse LLM response into JSON"""
        response_text = response_text.strip()
        
        # Clean markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        try:
            evaluation = json.loads(response_text)
            
            # Ensure all required fields exist
            required_fields = ['criterion_scores', 'strengths', 'weaknesses', 'qualitative_feedback']
            for field in required_fields:
                if field not in evaluation:
                    if field == 'criterion_scores':
                        evaluation[field] = {"technical_accuracy": 75, "completeness": 75, "relevance": 75, "practicality": 75}
                    elif field in ['strengths', 'weaknesses']:
                        evaluation[field] = []
                    elif field == 'qualitative_feedback':
                        evaluation[field] = "Evaluation completed successfully."
            
            return evaluation
            
        except json.JSONDecodeError:
            print(f"JSON parsing error. Response text: {response_text[:200]}")
            return self._create_basic_evaluation()
    
    def _create_basic_evaluation(self):
        """Create a basic evaluation when parsing fails"""
        return {
            "criterion_scores": {
                "technical_accuracy": 75,
                "completeness": 75,
                "relevance": 75,
                "practicality": 75
            },
            "strengths": ["Shows understanding of basic concepts."],
            "weaknesses": ["Could benefit from more detailed explanations."],
            "qualitative_feedback": "Evaluation based on keyword analysis. Candidate demonstrates foundational knowledge suitable for further consideration."
        }
    
    def _fallback_evaluation(self, questions, responses, error):
        """Fallback evaluation if LLM fails"""
        # Calculate scores
        question_scores = self._calculate_question_scores(questions, responses)
        calculated_overall = question_scores.get('OVERALL', 70)
        
        # Determine recommendation
        if calculated_overall >= 85:
            recommendation = 'Strong Yes'
        elif calculated_overall >= 70:
            recommendation = 'Yes'
        elif calculated_overall >= 60:
            recommendation = 'No'
        else:
            recommendation = 'Strong No'
        
        # Remove OVERALL from display scores
        display_scores = {k: v for k, v in question_scores.items() if k != 'OVERALL'}
        
        return {
            "overall_score": calculated_overall,
            "criterion_scores": {
                "technical_accuracy": calculated_overall,
                "completeness": calculated_overall,
                "relevance": calculated_overall,
                "practicality": calculated_overall
            },
            "strengths": ["Responses show relevant knowledge based on keyword matching."],
            "weaknesses": ["Detailed evaluation unavailable due to system limitations."],
            "qualitative_feedback": f"Preliminary assessment based on keyword analysis. Score: {calculated_overall}/100. For accurate evaluation, please try again later.",
            "recommendation": recommendation,
            "interviewer_used": "Keyword-Based Evaluator",
            "evaluation_time_seconds": 0.0,
            "question_scores": display_scores
        }
