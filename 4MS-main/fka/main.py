import os
import time
from groq import Groq
from dotenv import load_dotenv

# Import core components
from core.evaluator import EvaluationEngine
from core.question_generator import QuestionGenerator
from core.analytics import AnalyticsEngine
from core.jd_parser import JDParser
from utils.file_handler import FileHandler
from utils.timer import ResponseTimer

load_dotenv()

class FundamentalKnowledgeInterviewer:
    def __init__(self):
        # Check for API key
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found. Please create a .env file and add your key.")
        
        # Get model from env or use default
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        
        self.client = Groq(api_key=api_key)
        self.jd_parser = JDParser()
        self.evaluator = EvaluationEngine(api_key, model)
        self.question_generator = QuestionGenerator(api_key, model)
        self.analytics = AnalyticsEngine()
        self.file_handler = FileHandler()
        self.timer = ResponseTimer()
    
    def display_welcome(self):
        """Display welcome message"""
        print("🎯 Fundamental Knowledge Interviewer (Groq)")
        print("=" * 50)
        print("Testing essential skills and knowledge for the role")
        print(f"Model: {os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')}")

    def get_job_description(self) -> tuple:
        """Get JD from file upload only"""
        print("\n📄 JOB DESCRIPTION UPLOAD:")
        print("=" * 60)
        print("Upload a JD file (PDF, DOCX, TXT) to generate role-specific questions")
        print("=" * 60)
        
        while True:
            file_path = input("\nEnter the full path to your JD file: ").strip()
            
            if not os.path.exists(file_path):
                print("File not found. Please check the path and try again.")
                continue
                
            try:
                with open(file_path, 'rb') as f:
                    class MockFile:
                        def __init__(self, content, filename):
                            self.name = filename
                            self.content = content
                        
                        def getvalue(self):
                            return self.content
                    
                    filename = os.path.basename(file_path)
                    file_content = f.read()
                    mock_file = MockFile(file_content, filename)
                    
                    # Parse the file
                    jd_text = self.jd_parser.parse_uploaded_file(mock_file)
                    
                    # Detect role from JD
                    detected_role = self.jd_parser.detect_job_role(jd_text)
                    
                    print(f"✅ JD parsed successfully!")
                    print(f"🎯 Detected role: {detected_role}")
                    
                    return jd_text, detected_role
                    
            except Exception as e:
                print(f"Error parsing file: {str(e)}")
                retry = input("Try another file? (y/n): ").lower()
                if not retry.startswith('y'):
                    return "", "Software Engineer"

    def conduct_interview(self, questions: list):
        """Conduct the interview with fundamental questions"""
        print("\n\n--- INTERVIEW STARTED ---")
        print("Answer each fundamental question concisely.")
        print("Press Enter twice after each answer.\n")
        
        all_responses = []
        total_time = 0.0
        
        for i, question in enumerate(questions, 1):
            print(f"\n{'='*60}")
            print(f"QUESTION {i}/{len(questions)}")
            print(f"Type: {question['type'].upper()}")
            print(f"Difficulty: {question['difficulty'].upper()}")
            print(f"\n{question['question']}")
            print(f"\n{'-'*40}")
            
            # Start timer for this question
            self.timer.start()
            
            # Get response
            response_lines = []
            print("\nYour Answer (press Enter twice when finished):")
            while True:
                try:
                    line = input()
                    if line == "" and response_lines and response_lines[-1] == "":
                        break
                    elif line == "" and not response_lines:
                        continue
                    else:
                        response_lines.append(line)
                except KeyboardInterrupt:
                    print("\n\nResponse submission cancelled.")
                    return None, 0.0
            
            response_time = self.timer.stop()
            total_time += response_time
            
            response = "\n".join(response_lines).strip()
            all_responses.append({
                "question": question['question'],
                "type": question['type'],
                "difficulty": question['difficulty'],
                "expected_keywords": question.get('expected_keywords', []),
                "response": response,
                "response_time": response_time
            })
            
            print(f"Answered in {response_time:.2f} minutes")
        
        print(f"\nTotal interview time: {total_time:.2f} minutes")
        return all_responses, total_time
        
    def display_results(self, evaluation: dict):
        """Display the evaluation results"""
        print("\n\n--- EVALUATION RESULTS ---")
        print("=" * 50)
        print(f"🤵 Interviewer: {evaluation['interviewer_used']}")
        print(f"⏱️ Evaluation Time: {evaluation.get('evaluation_time_seconds', 0.0):.1f} seconds")
        print(f"**🌟 FUNDAMENTAL KNOWLEDGE SCORE: {evaluation['overall_score']}/100**")
        print(f"**✅ RECOMMENDATION: {evaluation['recommendation']}**")
        print("-" * 50)

        print("\n**Qualitative Feedback:**")
        print(evaluation['qualitative_feedback'])

        print("\n**Question-wise Scores:**")
        for q, score in evaluation.get('question_scores', {}).items():
            print(f"- {q}: {score}/100")
            
        print("\n**Strengths:**")
        for s in evaluation['strengths']:
            print(f"• {s}")
            
        print("\n**Weaknesses:**")
        for w in evaluation['weaknesses']:
            print(f"• {w}")
        print("=" * 50)

    def run_interview(self):
        """Main interview flow"""
        self.display_welcome()
        
        # Get JD and role
        job_description, role = self.get_job_description()
        if not job_description:
            print("No job description provided. Exiting.")
            return
        
        # Generate fundamental questions
        print(f"\n🎯 Generating fundamental questions for {role}...")
        questions = self.question_generator.generate_fundamental_questions(role, job_description)
        
        if not questions:
            print("Failed to generate questions. Exiting.")
            return
        
        print(f"\nGenerated {len(questions)} questions:")
        for i, q in enumerate(questions, 1):
            print(f"{i}. {q['question']}")
        
        # Conduct interview
        responses, total_time = self.conduct_interview(questions)
        if not responses:
            print("No responses provided. Exiting.")
            return
        
        # Evaluate responses
        print(f"\n📊 Evaluating responses...")
        evaluation = self.evaluator.evaluate_fundamental_responses(role, job_description, questions, responses)
        
        # Display results
        self.display_results(evaluation)
        
        # Save interview
        interview_data = {
            "role": role,
            "job_description": job_description[:1000],
            "questions": questions,
            "responses": responses,
            "total_time": total_time,
            "evaluation": evaluation,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        filename = self.file_handler.save_interview(interview_data)
        print(f"\n💾 Interview saved to: {filename}")
        
        # Show analytics if previous interviews exist
        previous_interviews = self.analytics.load_all_interviews()
        self.analytics.generate_comparative_analytics(previous_interviews)

if __name__ == "__main__":
    interviewer = FundamentalKnowledgeInterviewer()
    interviewer.run_interview()
