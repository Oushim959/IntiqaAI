# src/dynamic_workflow.py - FULL FIXED VERSION

import os
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, List
from operator import add
try:
    import streamlit as st
except ImportError:
    st = None
from datetime import datetime, timedelta
import pytz

# Load .env so GROQ_API_KEY / GOOGLE_API_KEY are available (e.g. when run from API)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(_env_path)
except Exception:
    pass

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph.message import add_messages


# LangChain imports
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langchain.tools.retriever import create_retriever_tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document


# PDF generation
from shared.src.pdf_utils import generate_pdf


# --- Helper function to format retriever outputs ---
def format_retriever_output(result):
    """
    Convert retriever tool outputs (which may be Document objects or lists)
    into plain text strings that Gemini can accept.
    """
    if result is None:
        return "No results found."
    
    if isinstance(result, str):
        return result
    
    # Handle Document objects
    if isinstance(result, Document):
        return result.page_content
    
    # Handle lists of Documents
    if isinstance(result, list):
        if not result:
            return "No results found."
        
        formatted_parts = []
        for idx, item in enumerate(result, 1):
            if isinstance(item, Document):
                formatted_parts.append(f"Result {idx}:\n{item.page_content}")
            else:
                formatted_parts.append(f"Result {idx}:\n{str(item)}")
        
        return "\n\n".join(formatted_parts)
    
    # Fallback for any other type
    return str(result)


def get_content_as_string(content):
    """
    Safely convert message content to string, handling list content from some LLM providers.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c) for c in content if c)
    return str(content)


class AgentState(TypedDict):
    mode: str
    num_of_q: int
    num_of_follow_up: int
    position: str
    evaluation_result: Annotated[str, add]
    company_name: str
    messages: Annotated[Sequence[BaseMessage], add_messages]
    report: Annotated[str, add]
    pdf_path: str | None
    resume_path: str | None
    questions_path: str | None
    resume_text: str | None
    interview_questions: List[str]
    question_index: int


# --- TIMEZONE-AWARE DATE FUNCTIONS (UTC+3) ---
def get_current_date_4ms():
    """Get current date in UTC+3 timezone (IntiqAI timezone)"""
    try:
        tz = pytz.timezone('Asia/Kuwait')  # UTC+3
        current = datetime.now(tz)
        return current.strftime("%d %B %Y")
    except:
        utc_now = datetime.utcnow()
        local_time = utc_now + timedelta(hours=3)
        return local_time.strftime("%d %B %Y")


def get_current_datetime_4ms():
    """Get current date and time in UTC+3 timezone"""
    try:
        tz = pytz.timezone('Asia/Kuwait')  # UTC+3
        current = datetime.now(tz)
        return current.strftime("%d %B %Y, %H:%M")
    except:
        utc_now = datetime.utcnow()
        local_time = utc_now + timedelta(hours=3)
        return local_time.strftime("%d %B %Y, %H:%M")


# --- LLM and Embeddings ---
# Interview uses Groq (GROQ_API_KEY required)
def _get_llm():
    from langchain_groq import ChatGroq
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is required for the voice interview. "
            "Add it to your .env file (e.g. GROQ_API_KEY=gsk_...)."
        )
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(model=model, temperature=0.7)


def _get_evaluator_llm():
    from langchain_groq import ChatGroq
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is required for the voice interview. "
            "Add it to your .env file (e.g. GROQ_API_KEY=gsk_...)."
        )
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(model=model, temperature=0.0)


llm = _get_llm()
evaluator_llm = _get_evaluator_llm()
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# --- Prompts ---
interviewer_prompt = PromptTemplate(
    input_variables=["mode", "company_name", "position", "interviewer_name", "interview_questions", "question_index"],
    template="""
You are a {mode} AI technical interviewer for {company_name}, conducting an interview for a {position} position.
Your name is {interviewer_name}.

Interview Structure:
1. Introduction: Introduce yourself and ask the candidate to briefly introduce themselves.
2. Technical Interview: You MUST ask the following 5 questions one by one in order.
3. Current Status: You are at question index {question_index} in the list below.

Question Pool:
{interview_questions}

Rules:
- DO NOT use any tools to search for questions.
- Ask the question at the current index ({question_index}).
- If the candidate's answer is vague, you may ask ONE brief follow-up, but then move to the next question in the next turn.
- After all 5 questions are finished, skip the follow-ups and ask: "Before we wrap up, do you have any questions for me?"
- When the candidate has no more questions, end the interview by saying exactly: "Thank you, that's it for today."

Begin the interview now. Introduce yourself first.
"""
)


evaluator_prompt = PromptTemplate(
    input_variables=["num_of_q", "position"],
    template="""You are an AI evaluator for a competency-based job interview.
Your task is to evaluate the candidate's responses to {num_of_q} technical questions.

DO NOT continue the conversation.
DO NOT act as the recruiter.

Position: {position}

Evaluation Criteria:
- Technical accuracy and depth of understanding.
- Clarity of reasoning.
- Alignment with expectations for a {position}.

Rules:
- Score only the {num_of_q} technical questions.
- Each question is on a scale of 1-5.
- If a response is missing, assign 1/5.

REQUIRED OUTPUT FORMAT:

Evaluation:
Q1:
Score: X/5
Justification: [concise sentences]

...
Q{num_of_q}:
Score: X/5
Justification: [concise sentences]
"""
)


report_writer_prompt = PromptTemplate(
    input_variables=["position", "company_name", "interview_transcript", "evaluation_report", "interview_date", "jd_content"],
    template="""You are an AI HR Report Writer.

Your task is to synthesize a concise, professional interview summary for Human Resources at {company_name}, based STRICTLY on:
1) the interview transcript, and
2) the completed evaluation report.

CRITICAL RULES:
- Do NOT re-evaluate, re-score, or contradict the evaluation report.
- Treat the evaluation report as the authoritative assessment.
- Use the interview transcript ONLY to support or illustrate points already reflected in the evaluation.
- Do NOT introduce new judgments, assumptions, or personality inferences.
- Maintain a neutral, professional HR tone.

The interview was for a **{position}** position.
Interview Date: {interview_date}

Report Guidelines:
- Focus on job-related evidence only.
- Avoid speculation.
- Keep the report concise and decision-oriented.
- Communication assessment should focus on clarity of explanation, NOT accent, grammar, or speaking style.
- **Handling Missing Data:** If the evaluation report indicates a score of 1/5 due to "No response provided," categorize this strictly as a "CRITICAL GAP," distinct from a general weakness.
- IMPORTANT: Job Description Reference (Use as Baseline for All Conclusions)

Your report should include the following sections:

### Candidate Overall Suitability
Provide a brief summary of the candidate’s overall suitability for the {position}, grounded in the evaluation results.

### Key Strengths
List 2–3 strengths demonstrated during the interview.
Support each with brief evidence from the transcript where clearly applicable.

### Areas for Development & Critical Gaps
List 2–3 areas where the candidate showed gaps or limitations.
- If the candidate attempted an answer but was weak, label it as **"Development Area"**.
- If the candidate failed to provide a response or completely missed the question (Score 1/5), label it as **"CRITICAL GAP"**.
Reference transcript examples only if they clearly illustrate the issue.

### Technical Skills Demonstrated
List core technical or role-relevant skills explicitly demonstrated or discussed by the candidate.

### Communication Effectiveness
Assess the candidate’s ability to clearly explain ideas and reasoning, based on content and structure of responses.

### Overall Recommendation 
Provide a high-level recommendation (e.g., Proceed to next round / Consider with reservations / Not a fit at this time),
briefly justified by patterns in the evaluation report.


{jd_content}


---

Interview Transcript:
{interview_transcript}

---

Evaluation Report:
{evaluation_report}
"""
)


# --- Vector Store and Retriever Setup ---
DEFAULT_QUESTIONS_PDF = "shared/data/default_questions.pdf"
DEFAULT_RESUME_PDF = "shared/data/default_resume.pdf"


text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


def initialize_questions_retriever(questions_path=None):
    questions_file = questions_path if questions_path and os.path.exists(questions_path) else DEFAULT_QUESTIONS_PDF


    import uuid
    import time
    session_id = f"{uuid.uuid4().hex}_{int(time.time())}"
    collection_name = f"questions_{session_id}"


    loader = PyPDFLoader(questions_file)
    pages = loader.load()
    pages_split = text_splitter.split_documents(pages)


    questions_vectorstore = Chroma.from_documents(
        documents=pages_split,
        embedding=embeddings,
        collection_name=collection_name
    )


    questions_retriever = questions_vectorstore.as_retriever(search_kwargs={"k": 3})


    questions_retriever_tool = create_retriever_tool(
        questions_retriever,
        "retrieve_questions",
        "Search and return interview questions related to the position from the knowledge base.",
    )


    return questions_retriever_tool


def initialize_resume_retriever(resume_path=None, resume_text=None):
    import uuid
    import time
    session_id = f"{uuid.uuid4().hex}_{int(time.time())}"
    collection_name = f"resume_{session_id}"


    docs = []
    if resume_text:
        docs = [Document(page_content=resume_text)]
    else:
        resume_file = resume_path if resume_path and os.path.exists(resume_path) else DEFAULT_RESUME_PDF
        resume_loader = PyPDFLoader(resume_file)
        docs = resume_loader.load()


    resume_split = text_splitter.split_documents(docs)


    resume_vectorstore = Chroma.from_documents(
        documents=resume_split,
        embedding=embeddings,
        collection_name=collection_name
    )


    resume_retriever = resume_vectorstore.as_retriever(search_kwargs={"k": 3})


    resume_retriever_tool = create_retriever_tool(
        resume_retriever,
        "retrieve_resume",
        "Search the candidate's resume to find specific projects, skills, and experiences.",
    )


    return resume_retriever_tool


def initialize_jd_retriever(jd_path):
    import uuid
    import time
    session_id = f"{uuid.uuid4().hex}_{int(time.time())}"
    collection_name = f"job_description_{session_id}"

    loader = PyPDFLoader(jd_path)
    pages = loader.load()
    pages_split = text_splitter.split_documents(pages)

    jd_vectorstore = Chroma.from_documents(
        documents=pages_split,
        embedding=embeddings,
        collection_name=collection_name
    )

    jd_retriever = jd_vectorstore.as_retriever(search_kwargs={"k": 3})

    jd_retriever_tool = create_retriever_tool(
        jd_retriever,
        "retrieve_job_description",
        "Retrieve job responsibilities, required skills, and competency expectations from the job description."
    )

    return jd_retriever_tool

# --- Graph Nodes ---
def recruiter(state: AgentState) -> AgentState:
    """
    Main recruiter node - generates AI responses.
    Does NOT handle tool calls - those are handled by the tools node.
    """
    sys_prompt = SystemMessage(content=interviewer_prompt.format(
        mode=state['mode'],
        company_name=state['company_name'],
        position=state['position'],
        interviewer_name=state.get('interviewer_name', 'Optimus Prime'),
        interview_questions=state.get('interview_questions', []),
        question_index=state.get('question_index', 0),
    ))

    # Build message history for LLM
    # Strategy: Include the full conversation but handle tool results specially
    conversation_messages = []
    
    i = 0
    while i < len(state["messages"]):
        msg = state["messages"][i]
        
        if isinstance(msg, HumanMessage):
            # Always include human messages
            conversation_messages.append(msg)
            i += 1
            
        elif isinstance(msg, AIMessage):
            # Check if this AI message has tool_calls
            if getattr(msg, 'tool_calls', None):
                # This AI message called tools - look for the following ToolMessages
                tool_results = []
                j = i + 1
                while j < len(state["messages"]) and isinstance(state["messages"][j], ToolMessage):
                    tool_results.append(state["messages"][j])
                    j += 1
                
                # If we found tool results, include them in the conversation
                if tool_results:
                    # Include the AI message with tool_calls
                    conversation_messages.append(msg)
                    # Include all the tool result messages
                    conversation_messages.extend(tool_results)
                    i = j  # Skip past the tool messages we just processed
                else:
                    # No tool results found, skip this AI message
                    i += 1
            else:
                # Regular AI message with content
                if msg.content and msg.content.strip():
                    conversation_messages.append(msg)
                i += 1
                
        elif isinstance(msg, ToolMessage):
            # Standalone ToolMessage (shouldn't happen, but skip it)
            i += 1
        else:
            i += 1

    all_messages = [sys_prompt] + conversation_messages

    try:
        # Build tools list - no tools for now as we use pool questions
        tools = []

        # Retry up to 3 times if we get an empty response
        max_retries = 3
        for attempt in range(max_retries):
            response = llm.bind_tools(tools).invoke(all_messages)
            has_tool_calls = bool(getattr(response, 'tool_calls', None))
            # Handle case where content is a list (some LLM providers) or string
            content = response.content
            if isinstance(content, list):
                content = " ".join(str(c) for c in content if c)
            has_content = bool(content and content.strip())

            print(f"[DEBUG] Recruiter response (attempt {attempt+1}) - has tool_calls: {has_tool_calls}, has content: {has_content}")

            # If we got a valid response (either content or tool_calls), return it
            if has_content or has_tool_calls:
                return {"messages": [response]}

            # Empty response - log details and retry
            print(f"[WARNING] Empty response from LLM (attempt {attempt+1}/{max_retries})")
            print(f"[DEBUG] Message count: {len(all_messages)}")
            if conversation_messages:
                last_human = next((m for m in reversed(conversation_messages) if isinstance(m, HumanMessage)), None)
                if last_human:
                    print(f"[DEBUG] Last human message: {last_human.content[:100]}...")

        # All retries exhausted - generate a continuation prompt
        print(f"[ERROR] All {max_retries} attempts returned empty response, using fallback")

        # Try one more time with an explicit continuation prompt
        continuation_prompt = HumanMessage(content="Please continue the interview by asking the next question based on my previous response.")
        fallback_messages = all_messages + [continuation_prompt]
        response = llm.bind_tools(tools).invoke(fallback_messages)

        if response.content or getattr(response, 'tool_calls', None):
            return {"messages": [response]}

        # Ultimate fallback
        return {"messages": [AIMessage(content="Thank you for your introduction. Now, let me look at your resume to ask you about your projects.")]}

    except Exception as e:
        print(f"[ERROR] LLM invocation failed: {str(e)}")
        return {"messages": [AIMessage(content="I apologize, but I encountered an error. Could you please repeat your last response?")]}

def maybe_increment_index(state: AgentState) -> dict:
    """Check if the AI just asked a technical question and increment index if so."""
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and last_msg.content:
        content = get_content_as_string(last_msg.content).lower()
        # Heuristic: if the AI asked one of our specified questions, and it wasn't a follow-up
        questions = state.get("interview_questions", [])
        idx = state.get("question_index", 0)
        if idx < len(questions):
            current_q = questions[idx].lower()
            # If the current question text specifically appeared in the AI's message
            # and it's not the closing segment
            if current_q in content and "that's it for today" not in content:
                # We'll increment for the NEXT turn. 
                # Note: This is simplified; refined logic might wait for a valid human response.
                return {"question_index": idx + 1}
    return {}


def evaluator(state: AgentState) -> AgentState:
    sys_prompt = evaluator_prompt.format(
        num_of_q=state['num_of_q'],
        num_of_follow_up=state['num_of_follow_up'],
        position=state['position']
    )

    # Build the interview transcript for evaluation
    interview_transcript = []
    for m in state["messages"]:
        content_str = get_content_as_string(m.content)
        # Stop evaluation before the candidate Q&A closing segment
        if isinstance(m, AIMessage) and content_str and "do you have any questions for me" in content_str.lower():
            break

        if isinstance(m, HumanMessage):
            if content_str and content_str.strip():
                interview_transcript.append(f"Candidate: {content_str}")
        elif isinstance(m, AIMessage):
            # Only include AIMessages with actual content
            if content_str and content_str.strip():
                # Exclude the final "that's it for today" message from evaluation
                if "that's it for today" not in content_str.lower():
                    interview_transcript.append(f"AI Recruiter: {content_str}")

    # Validate we have content to evaluate
    if not interview_transcript or len(interview_transcript) < 2:
        print("[ERROR] Not enough interview content to evaluate")
        return {"evaluation_result": "Error: Insufficient interview content for evaluation."}

    # Try to get JD content for scoring context
    jd_content = "Job description not available."
    jd_path = "cv_filtering/Improved Job Descriptions/Improved_Job_Description.pdf"
    if os.path.exists(jd_path):
        try:
            jd_retriever_tool = initialize_jd_retriever(jd_path)
            jd_content = format_retriever_output(jd_retriever_tool.invoke({"query": "must-have requirements, core responsibilities, and expected skills"}))
        except Exception as e:
            print(f"[WARNING] Could not load JD for evaluation: {e}")
    else:
        print(f"[WARNING] JD file not found at {jd_path}, proceeding without JD context")

    # Create a single prompt with the full transcript
    full_prompt = f"""{sys_prompt}

Authoritative Job Description (Use as Scoring Standard):
{jd_content}

Interpret scores as:
- 1–2: Below job description expectations
- 3: Meets job description expectations
- 4–5: Exceeds job description expectations


Here is the complete interview transcript to evaluate:

{chr(10).join(interview_transcript)}

Please provide the evaluation now in the specified format."""

    print(f"[DEBUG] Evaluator - transcript has {len(interview_transcript)} messages")
    print(f"[DEBUG] Evaluator - prompt length: {len(full_prompt)} chars")
    print(f"[DEBUG] Evaluator - first 200 chars of prompt: {full_prompt[:200]}")
    
    # Validate the prompt is not empty
    if not full_prompt or len(full_prompt.strip()) < 50:
        print(f"[ERROR] Evaluator prompt is too short or empty")
        return {"evaluation_result": "Error: Generated prompt is invalid or empty."}
    
    try:
        print(f"[DEBUG] Invoking evaluator LLM...")
        # Use HumanMessage instead of SystemMessage for Gemini compatibility
        # Gemini expects at least one user message
        human_message = HumanMessage(content=full_prompt)
        results = evaluator_llm.invoke([human_message])
        print(f"[DEBUG] Evaluator completed successfully")
        return {"evaluation_result": results.content}
    except Exception as e:
        print(f"[ERROR] Evaluator failed: {str(e)}")
        print(f"[DEBUG] Full transcript:")
        for i, line in enumerate(interview_transcript[:10], 1):  # Print first 10 lines
            print(f"  {i}. {line[:100]}")
        return {"evaluation_result": f"Error during evaluation: {str(e)}"}


def report_writer(state: AgentState) -> AgentState:
    # GET CURRENT DATE WITH CORRECT TIMEZONE (UTC+3)
    interview_date = get_current_date_4ms()

    # Try to get JD content for report context
    jd_content = "Job description not available."
    jd_path = "cv_filtering/Improved Job Descriptions/Improved_Job_Description.pdf"
    if os.path.exists(jd_path):
        try:
            jd_retriever_tool = initialize_jd_retriever(jd_path)
            jd_content = format_retriever_output(jd_retriever_tool.invoke({"query": "role summary, must-have skills, and expectations"}))
        except Exception as e:
            print(f"[WARNING] Could not load JD for report: {e}")
    else:
        print(f"[WARNING] JD file not found at {jd_path}")

    interviewer_transcript = []
    for m in state["messages"]:
        content_str = get_content_as_string(m.content)
        # Stop transcript before the candidate Q&A closing segment
        if isinstance(m, AIMessage) and content_str and "do you have any questions for me" in content_str.lower():
            break

        if isinstance(m, HumanMessage):
            interviewer_transcript.append('Candidate: ' + content_str)
        elif isinstance(m, AIMessage):
            if content_str and 'Evaluation:\n1. Introduction question' not in content_str:
                interviewer_transcript.append('AI Recruiter: ' + content_str)

    sys_prompt = report_writer_prompt.format(
        position=state['position'],
        company_name=state['company_name'],
        interview_transcript='\n'.join(interviewer_transcript),
        evaluation_report=state["evaluation_result"],
        interview_date=interview_date,
        jd_content=jd_content
    )


    sys_message = SystemMessage(content=sys_prompt)
    all_messages = [sys_message, HumanMessage(content="Generate the HR report")]


    result = llm.invoke(all_messages)
    return {"report": result.content}


def pdf_generator_node(state: AgentState) -> AgentState:
    if not state.get("report"):
        return {"pdf_path": None}

    candidate_name = state.get("candidate_name")
    if not candidate_name and st is not None:
        try:
            candidate_info = st.session_state.candidates_df.loc[st.session_state.selected_candidate_index]
            candidate_name = f"{candidate_info['First Name']} {candidate_info['Last Name']}"
        except Exception:
            candidate_name = "Candidate"
    if not candidate_name:
        candidate_name = "Candidate"
    filename = f"HR_Report_{candidate_name}_{state['position']}.pdf".replace(" ", "_")


    try:
        pdf_path = generate_pdf(state["report"], filename=filename)
        return {"pdf_path": pdf_path}
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        return {"pdf_path": None}


def custom_tools_condition(state):
    """
    Determine where to route after the recruiter node.
    """
    if not state['messages']:
        print("[DEBUG] No messages, routing to WAIT_FOR_HUMAN")
        return "WAIT_FOR_HUMAN"

    last_message = state['messages'][-1]
    
    # Check if AI wants to call tools
    if isinstance(last_message, AIMessage) and getattr(last_message, 'tool_calls', None):
        # Safety check: count recent consecutive tool calls to prevent infinite loops
        consecutive_tool_calls = 0
        for msg in reversed(state['messages'][-10:]):  # Check last 10 messages
            if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None):
                consecutive_tool_calls += 1
            elif isinstance(msg, HumanMessage):
                break  # Stop at the last human message
        
        if consecutive_tool_calls > 3:
            print(f"[WARNING] Too many consecutive tool calls ({consecutive_tool_calls}), forcing response")
            # Force the AI to respond with text by returning a message
            return "WAIT_FOR_HUMAN"
        
        print(f"[DEBUG] AI wants to call {len(last_message.tool_calls)} tool(s), routing to tools")
        return "tools"
    
    # Check if interview is ending
    elif isinstance(last_message, AIMessage) and last_message.content and "that's it for today" in get_content_as_string(last_message.content).lower():
        print("[DEBUG] Interview ending, routing to evaluator")
        return "END_CONVERSATION"
    
    # Normal response - check if we should increment index then wait for human
    else:
        print(f"[DEBUG] Normal response, routing to increment_index")
        return "increment_index"


def tools_node(state: AgentState) -> AgentState:
    """
    Handle tool calls by executing them and formatting the results.
    This node is called when the AI wants to use a tool.
    """
    resume_retriever_tool = initialize_resume_retriever(
        resume_path=state.get("resume_path"),
        resume_text=state.get("resume_text")
    )
    questions_retriever_tool = initialize_questions_retriever(state.get("questions_path"))

    # Initialize JD retriever if available
    jd_retriever_tool = None
    jd_path = "cv_filtering/Improved Job Descriptions/Improved_Job_Description.pdf"
    if os.path.exists(jd_path):
        try:
            jd_retriever_tool = initialize_jd_retriever(jd_path)
        except Exception as e:
            print(f"[WARNING] Could not initialize JD retriever in tools_node: {e}")

    # Get the last AI message which should have tool_calls
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        print("[WARNING] tools_node called but no tool_calls found")
        return {}

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        tool_id = tool_call.get("id", "")
        query = tool_call.get("args", {}).get("query", "")

        print(f"[DEBUG] Executing tool: {tool_name} with query: {query[:50]}...")

        try:
            if tool_name == "retrieve_resume":
                result = resume_retriever_tool.invoke({"query": query})
            elif tool_name == "retrieve_questions":
                result = questions_retriever_tool.invoke({"query": query})
            elif tool_name == "retrieve_job_description":
                if jd_retriever_tool:
                    result = jd_retriever_tool.invoke({"query": query})
                else:
                    result = "Job description not available."
            else:
                result = f"Unknown tool: {tool_name}"
            
            # Format the result to plain text
            formatted_result = format_retriever_output(result)
            
            tool_message = ToolMessage(
                content=formatted_result,
                tool_call_id=tool_id,
                name=tool_name
            )
            tool_messages.append(tool_message)
            print(f"[DEBUG] Tool {tool_name} returned {len(formatted_result)} chars")
            
        except Exception as e:
            print(f"[ERROR] Tool execution failed: {str(e)}")
            tool_message = ToolMessage(
                content=f"Error executing tool: {str(e)}",
                tool_call_id=tool_id,
                name=tool_name
            )
            tool_messages.append(tool_message)
    
    return {"messages": tool_messages}


def build_workflow():
    workflow = StateGraph(AgentState)

    # Add all nodes
    workflow.add_node("recruiter", recruiter)
    workflow.add_node("tools", tools_node)
    workflow.add_node("evaluator", evaluator)
    workflow.add_node("report_writer", report_writer)
    workflow.add_node("pdf_generator", pdf_generator_node)
    workflow.add_node("increment_index", maybe_increment_index)

    # Set entry point
    workflow.set_entry_point("recruiter")

    # Conditional routing from recruiter
    workflow.add_conditional_edges(
        "recruiter",
        custom_tools_condition,
        {
            "tools": "tools",
            "END_CONVERSATION": END,  # End interview, let user trigger evaluation manually
            "increment_index": "increment_index"
        }
    )

    # After tools execute, go back to recruiter to generate response with tool results
    workflow.add_edge("tools", "recruiter")

    # After incrementing index, end turn and wait for human
    workflow.add_edge("increment_index", END)
    
    # Evaluator goes directly to report writer (no tools needed)
    workflow.add_edge("evaluator", "report_writer")

    # Report writer to PDF generator
    workflow.add_edge("report_writer", "pdf_generator")
    
    # PDF generator to END
    workflow.add_edge("pdf_generator", END)

    return workflow.compile()
