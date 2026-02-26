import json
from groq import Groq
from typing import Dict, Any

class JDGenerator:
    """Uses LLM to generate scenario and criteria from a Job Description."""
    
    def __init__(self, client: Groq, model: str = "llama-3.1-8b-instant"):
        self.client = client
        self.model = model

    def generate_job_description(self, role: str) -> str:
        """
        Dynamically generates a detailed Job Description based on the general role.
        """
        # Role is a simple string input from the user (e.g., 'Senior Go Engineer')
        prompt = f"""
        Generate a detailed and realistic Job Description (JD) for a mid-to-senior level 
        "{role.title()}" role. 
        
        The JD should include:
        1. A brief company/team description (make it generic but compelling).
        2. Key Responsibilities (5-7 bullet points).
        3. Required Qualifications (4-6 bullet points of technical skills).
        4. Preferred Qualifications (2-3 additional skills/experience).
        
        Return ONLY the plain text of the job description. Do not include any JSON formatting or preamble.
        """
        try:
            print(f"⚙️ Generating a detailed Job Description for {role.title()}...")
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7, 
                max_tokens=1500,
            )
            
            job_description = chat_completion.choices[0].message.content.strip()
            print(" Job Description generated.")
            return job_description
            
        except Exception as e:
            print(f" JD generation error: {e}")
            return f"Error generating JD. Fallback JD for a {role.title()}:\n\n- Write clean, scalable code.\n- Design and implement data solutions."


    def generate_interview_blueprint(self, role: str, job_description: str) -> Dict[str, Any]:
        """
        Dynamically generates a technical scenario and evaluation criteria
        based on the provided job description and general role.
        """
        prompt = f"""
ROLE: {role.title()}
JOB DESCRIPTION:
{job_description}

Based on the provided ROLE and detailed JOB DESCRIPTION, generate a highly relevant and challenging 
technical/system design scenario suitable for the logic phase of the interview.
Also, define 5 specific, measurable evaluation criteria for this scenario, ensuring they cover the 
key technical requirements mentioned in the JD.

Keep the scenario focused on the problem statement, not the solution.
The criteria should be concise (name: description).

Return the output as a valid JSON object:
{{
    "scenario": "A detailed, role-specific technical problem statement (e.g., 'Design a scalable real-time...')",
    "evaluation_criteria": {{
        "criterion_1_name": "criterion_1_description",
        "criterion_2_name": "criterion_2_description",
        "criterion_3_name": "criterion_3_description",
        "criterion_4_name": "criterion_4_description",
        "criterion_5_name": "criterion_5_description"
    }}
}}
"""
        try:
            print("⚙️ Generating dynamic interview blueprint from JD...")
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.2, 
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            response_text = chat_completion.choices[0].message.content
            # Safely parse the response, handling potential markdown fences
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1]
            else:
                json_str = response_text
                
            blueprint = json.loads(json_str.strip())
            print(" Blueprint generated.")
            return blueprint
            
        except Exception as e:
            print(f" JD generation error: {e}")
            # Fallback to general criteria
            return {
                "scenario": f"General logic phase challenge for a {role.title()}",
                "evaluation_criteria": {
                    "logical_coherence": "Clarity and structure of the argument.",
                    "technical_feasibility": "Practicality of the proposed solution.",
                    "scalability_efficiency": "Handling of large-scale constraints."
                }
            }
