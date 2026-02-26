import streamlit as st
import json
import time
import os
from datetime import datetime
from groq import Groq
import plotly.express as px
import pandas as pd
from dotenv import load_dotenv

# Local imports
from core.evaluator import EvaluationEngine
from core.question_generator import QuestionGenerator
from core.jd_parser import JDParser

load_dotenv()

# --- Helper Functions for Streamlit UI ---

def display_results(evaluation: dict, total_time: float, questions: list):
    st.subheader("Fundamental Knowledge Evaluation")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Fundamental Score", f"{evaluation['overall_score']}/100", 
                  help="Score based on essential knowledge for the role")
    with col2:
        # Color code the recommendation
        rec = evaluation['recommendation']
        color = "green" if "Yes" in rec else "red" if "No" in rec else "orange"
        st.metric("Recommendation", rec, 
                  help="Hiring recommendation based on fundamental knowledge")
    
    st.markdown(f"**Total Interview Time:** {total_time:.2f} minutes")
    st.markdown("---")
    
    st.markdown("##### Qualitative Feedback")
    st.info(evaluation['qualitative_feedback'])
    
    # Display criterion scores
    st.markdown("##### Criterion Scores")
    if 'criterion_scores' in evaluation:
        crit_df = pd.DataFrame([
            {"Criterion": "Technical Accuracy", "Score": evaluation['criterion_scores'].get('technical_accuracy', 0)},
            {"Criterion": "Completeness", "Score": evaluation['criterion_scores'].get('completeness', 0)},
            {"Criterion": "Relevance", "Score": evaluation['criterion_scores'].get('relevance', 0)},
            {"Criterion": "Practicality", "Score": evaluation['criterion_scores'].get('practicality', 0)}
        ])
        
        fig = px.bar(crit_df, x='Criterion', y='Score', 
                     color='Score', color_continuous_scale=px.colors.sequential.Teal,
                     text='Score', height=300)
        fig.update_layout(coloraxis_showscale=False, yaxis_range=[0, 100], margin=dict(t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    
    # Display question scores if available
    if 'question_scores' in evaluation and evaluation['question_scores']:
        st.markdown("##### Question-wise Scores")
        
        scores_data = []
        for q_key, score in evaluation['question_scores'].items():
            scores_data.append({
                "Question": q_key,
                "Score": score,
            })
        
        if scores_data:
            scores_df = pd.DataFrame(scores_data)
            fig = px.bar(scores_df, x='Score', y='Question', 
                         orientation='h',
                         color='Score', 
                         color_continuous_scale=px.colors.sequential.Teal,
                         height=400)
            fig.update_layout(coloraxis_showscale=False, xaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("##### Strengths")
    if evaluation['strengths']:
        for s in evaluation['strengths']:
            st.write(f"✅ {s}")
    else:
        st.write("No specific strengths identified.")
        
    st.markdown("##### Weaknesses")
    if evaluation['weaknesses']:
        for w in evaluation['weaknesses']:
            st.write(f"⚠️ {w}")
    else:
        st.write("No significant weaknesses identified.")

# --- Interview System Class ---

class InterviewSystem:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            st.error("GROQ_API_KEY not found. Please set it in your .env file.")
            raise ValueError("GROQ_API_KEY not found.")
        
        # Get model from env or use default
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        
        self.client = Groq(api_key=api_key)
        self.jd_parser = JDParser()
        self.evaluator = EvaluationEngine(api_key, model)
        self.question_generator = QuestionGenerator(api_key, model)

    def parse_uploaded_jd(self, uploaded_file):
        return self.jd_parser.parse_uploaded_file(uploaded_file)
    
    def detect_job_role(self, jd_text: str):
        return self.jd_parser.detect_job_role(jd_text)
    
    def generate_questions(self, role: str, job_description: str):
        return self.question_generator.generate_fundamental_questions(role, job_description)
    
    def evaluate_responses(self, role: str, job_description: str, questions: list, responses: list):
        return self.evaluator.evaluate_fundamental_responses(role, job_description, questions, responses)

# --- Main Function ---

def main():
    st.set_page_config(layout="wide", page_title="Fundamental Knowledge Interviewer")
    
    # Initialize session state
    if 'system' not in st.session_state:
        try:
            st.session_state.system = InterviewSystem()
        except ValueError:
            st.stop()
    
    if 'interview_history' not in st.session_state:
        st.session_state.interview_history = []
    if 'current_interview' not in st.session_state:
        st.session_state.current_interview = None
    if 'questions' not in st.session_state:
        st.session_state.questions = []
    if 'responses' not in st.session_state:
        st.session_state.responses = []
    if 'jd_text' not in st.session_state:
        st.session_state.jd_text = ""
    if 'role' not in st.session_state:
        st.session_state.role = None
    if 'response_start_time' not in st.session_state:
        st.session_state.response_start_time = {}
    if 'total_time' not in st.session_state:
        st.session_state.total_time = 0.0
    if 'model_used' not in st.session_state:
        st.session_state.model_used = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    if 'questions_generated' not in st.session_state:
        st.session_state.questions_generated = False
    if 'file_uploaded' not in st.session_state:
        st.session_state.file_uploaded = False
    if 'evaluation_done' not in st.session_state:
        st.session_state.evaluation_done = False

    # Main content
    st.title("Fundamental Knowledge Interviewer (Groq)")
    st.markdown("Test essential skills and knowledge for technical roles")
    
    # Sidebar configuration
    st.sidebar.header("Configuration")
    
    # Show model info in sidebar
    st.sidebar.info(f"**Model:** {st.session_state.model_used}")
    
    if st.session_state.role:
        st.sidebar.subheader("Current Role")
        st.sidebar.info(f"**{st.session_state.role}**")
    
    st.markdown("---")
    
    # Step 1: JD Upload
    st.subheader("Step 1: Upload Job Description")
    
    uploaded_file = st.file_uploader(
        "Upload Job Description File",
        type=['pdf', 'docx', 'txt'],
        help="Supported formats: PDF, Word documents, Text files",
        key="jd_file_uploader"
    )
    
    # Handle file upload
    if uploaded_file is not None and not st.session_state.file_uploaded:
        with st.spinner("Parsing uploaded JD file..."):
            try:
                parsed_jd = st.session_state.system.parse_uploaded_jd(uploaded_file)
                st.session_state.jd_text = parsed_jd
                
                # Detect role
                detected_role = st.session_state.system.detect_job_role(parsed_jd)
                st.session_state.role = detected_role
                st.session_state.file_uploaded = True
                st.session_state.questions_generated = False  # Reset questions flag
                st.session_state.evaluation_done = False  # Reset evaluation flag
                
                st.success(f"JD parsed successfully!")
                st.info(f"**Detected Role:** {detected_role}")
                
                # Show JD preview
                with st.expander("View JD Preview"):
                    st.text_area("Job Description", parsed_jd[:1000] + "..." if len(parsed_jd) > 1000 else parsed_jd, 
                               height=200, disabled=True, key="jd_preview")
                
            except Exception as e:
                st.error(f"Error parsing file: {str(e)}")
    elif uploaded_file is None:
        st.session_state.file_uploaded = False
        st.session_state.questions_generated = False
        st.session_state.evaluation_done = False
        st.session_state.questions = []
        st.info("👆 Upload a job description file to get started.")
    
    # Generate Questions Button - Only show if JD is uploaded but questions not generated yet
    if st.session_state.file_uploaded and st.session_state.role and not st.session_state.questions_generated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Generate Fundamental Questions", type="primary", use_container_width=True, key="generate_btn"):
                with st.spinner(f"Generating fundamental questions for {st.session_state.role}..."):
                    try:
                        questions = st.session_state.system.generate_questions(st.session_state.role, st.session_state.jd_text)
                        st.session_state.questions = questions
                        st.session_state.responses = [""] * len(questions)
                        st.session_state.response_start_time = {}
                        st.session_state.questions_generated = True
                        st.session_state.evaluation_done = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error generating questions: {str(e)}")
                        st.info("Using fallback questions instead...")
                        # Use fallback questions
                        from core.question_generator import QuestionGenerator
                        api_key = os.getenv("GROQ_API_KEY")
                        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
                        qg = QuestionGenerator(api_key, model)
                        st.session_state.questions = qg._get_fallback_questions(st.session_state.role)[:5]
                        st.session_state.responses = [""] * len(st.session_state.questions)
                        st.session_state.response_start_time = {}
                        st.session_state.questions_generated = True
                        st.session_state.evaluation_done = False
                        st.rerun()
    
    # Step 2: Interview Questions - Only show if questions have been generated
    if st.session_state.questions_generated and st.session_state.questions and not st.session_state.evaluation_done:
        st.markdown("---")
        st.subheader(f"Step 2: Fundamental Questions for {st.session_state.role}")
        st.info(f"**{len(st.session_state.questions)} questions generated** - Answer each question concisely to test your fundamental knowledge.")
        
        # Initialize responses if needed
        if len(st.session_state.responses) != len(st.session_state.questions):
            st.session_state.responses = [""] * len(st.session_state.questions)
        
        # Display each question
        for i, question in enumerate(st.session_state.questions):
            st.markdown(f"### Question {i+1}/{len(st.session_state.questions)}")
            
            col_type, col_diff = st.columns(2)
            with col_type:
                st.info(f"**Type:** {question['type'].title()}")
            with col_diff:
                st.info(f"**Difficulty:** {question['difficulty'].title()}")
            
            st.markdown(f"**{question['question']}**")
            
            # Show expected keywords if available
            if question.get('expected_keywords'):
                with st.expander("Expected keywords (hint)"):
                    st.write(", ".join(question['expected_keywords']))
            
            # Response input
            response = st.text_area(
                f"Your Answer (Question {i+1}):",
                height=150,
                placeholder="Type your answer here...",
                value=st.session_state.responses[i],
                key=f"response_{i}"
            )
            
            # Update response in session state
            st.session_state.responses[i] = response
            
            # Timer for this question
            col_time, col_btn = st.columns([3, 1])
            with col_btn:
                if st.button(f"Start Timer Q{i+1}", key=f"timer_{i}"):
                    st.session_state.response_start_time[i] = time.time()
            
            with col_time:
                if i in st.session_state.response_start_time:
                    elapsed = time.time() - st.session_state.response_start_time[i]
                    st.write(f"⏱️ Time: {elapsed/60:.1f} minutes")
            
            st.markdown("---")
        
        # Submit for Evaluation
        st.markdown("### Step 3: Submit for Evaluation")
        
        # Check if all questions have responses
        all_answered = all(response.strip() for response in st.session_state.responses)
        
        if not all_answered:
            st.warning("Please answer all questions before submitting.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Submit All Answers for Evaluation", 
                        type="secondary", 
                        use_container_width=True,
                        disabled=not all_answered,
                        key="evaluate_btn"):
                # Calculate total time
                total_time = 0.0
                for i in range(len(st.session_state.questions)):
                    if i in st.session_state.response_start_time:
                        total_time += (time.time() - st.session_state.response_start_time[i]) / 60
                
                st.session_state.total_time = total_time
                
                with st.spinner("Evaluating fundamental knowledge..."):
                    try:
                        # Prepare responses data
                        responses_data = []
                        for i, question in enumerate(st.session_state.questions):
                            responses_data.append({
                                "question": question['question'],
                                "type": question['type'],
                                "difficulty": question['difficulty'],
                                "expected_keywords": question.get('expected_keywords', []),
                                "response": st.session_state.responses[i],
                                "response_time": total_time / len(st.session_state.questions)
                            })
                        
                        # Evaluate
                        evaluation = st.session_state.system.evaluate_responses(
                            st.session_state.role,
                            st.session_state.jd_text[:1000],
                            st.session_state.questions,
                            responses_data
                        )
                        
                        # Store interview
                        interview_data = {
                            "role": st.session_state.role,
                            "job_description": st.session_state.jd_text[:1000],
                            "questions": st.session_state.questions,
                            "responses": responses_data,
                            "total_time": total_time,
                            "evaluation": evaluation,
                            "timestamp": datetime.now().isoformat(),
                            "model_used": st.session_state.model_used
                        }
                        
                        st.session_state.current_interview = interview_data
                        st.session_state.interview_history.append(interview_data)
                        st.session_state.evaluation_done = True
                        
                        # Show results
                        display_results(evaluation, total_time, st.session_state.questions)
                        
                        # Reset for new interview (keep history)
                        st.session_state.questions_generated = False
                        st.session_state.questions = []
                        st.session_state.responses = []
                        st.session_state.response_start_time = {}
                        
                    except Exception as e:
                        st.error(f"Error during evaluation: {str(e)}")
                        # Show fallback evaluation
                        from core.evaluator import EvaluationEngine
                        api_key = os.getenv("GROQ_API_KEY")
                        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
                        evaluator = EvaluationEngine(api_key, model)
                        fallback_eval = evaluator._fallback_evaluation(st.session_state.questions, st.session_state.responses, e)
                        display_results(fallback_eval, total_time, st.session_state.questions)
                        st.session_state.evaluation_done = True
    
    # Step 3: Show previous results if available
    if st.session_state.current_interview and st.session_state.evaluation_done:
        st.markdown("---")
        st.subheader("Evaluation Results")
        display_results(
            st.session_state.current_interview['evaluation'],
            st.session_state.current_interview['total_time'],
            st.session_state.current_interview['questions']
        )
        
        # Button to start new interview
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Start New Interview", type="primary", use_container_width=True):
                st.session_state.file_uploaded = False
                st.session_state.role = None
                st.session_state.jd_text = ""
                st.session_state.current_interview = None
                st.session_state.evaluation_done = False
                st.rerun()
    
    # Interview History Sidebar
    if st.session_state.interview_history:
        st.sidebar.header("Interview History")
        
        history_df = pd.DataFrame([
            {
                'Role': i['role'].title(), 
                'Score': i['evaluation']['overall_score'],
                'Recommendation': i['evaluation']['recommendation'],
                'Questions': len(i['questions']),
                'Time': i['timestamp'][:19]
            }
            for i in st.session_state.interview_history
        ])
        
        st.sidebar.dataframe(history_df, use_container_width=True, height=200)
        
        # Progress chart
        if len(st.session_state.interview_history) > 1:
            st.sidebar.subheader("Score Progress")
            progress_df = pd.DataFrame({
                'Interview': range(1, len(st.session_state.interview_history) + 1),
                'Score': [i['evaluation']['overall_score'] for i in st.session_state.interview_history]
            })
            
            fig = px.line(progress_df, x='Interview', y='Score', 
                        title="", markers=True, height=250)
            fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), yaxis_range=[0, 100])
            st.sidebar.plotly_chart(fig, use_container_width=True)
    
    # Clear session state button (for debugging)
    with st.sidebar.expander("Advanced"):
        if st.button("Clear Session State"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

if __name__ == "__main__":
    main()
