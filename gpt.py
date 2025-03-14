import json
import os
import textwrap
import re
import src.strings as strings
from datetime import datetime
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

class LLMLogger:
    """Logs requests and responses from the LLM API."""
    
    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        calls_log = os.path.join(Path("data_folder/output"), "llm_calls.json")

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "model": parsed_reply.get("model", ""),
            "time": current_time,
            "prompts": prompts,
            "replies": parsed_reply.get("content", ""),  
            "total_tokens": parsed_reply.get("total_tokens", 0),
            "input_tokens": parsed_reply.get("input_tokens", 0),
            "output_tokens": parsed_reply.get("output_tokens", 0),
            "total_cost": parsed_reply.get("total_cost", 0),
        }

        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")


class GPTAnswerer:
    def __init__(self, openai_api_key, model="gpt-4o"):
        self.llm = ChatOpenAI(model_name=model, openai_api_key=openai_api_key, temperature=0.4)
        self.job_application_profile = None  # ✅ Fix: Store job application profile
        self.resume = None  # ✅ Fix: Store resume

    def set_resume(self, resume):  
        """Set the resume object."""
        self.resume = resume

    def set_job_application_profile(self, job_application_profile):
        """Set the job application profile object."""
        self.job_application_profile = job_application_profile

    def query(self, prompt: str) -> str:
        """Send a query to OpenAI's API and return the response."""
        prompt_template = ChatPromptTemplate.from_template(prompt)
        chain = prompt_template | self.llm | StrOutputParser()
        return chain.invoke({})

    def summarize_job_description(self, text: str) -> str:
        """Summarize a job description into a concise format."""
        prompt = f"Summarize the following job description concisely:\n\n{text}"
        return self.query(prompt)

    def answer_question_textual_wide_range(self, question: str) -> str:
        """
        Determines the most relevant section of the resume and generates an answer.
        """
        sections = {
            "personal_information": "Personal details like name, email, phone, LinkedIn, and GitHub.",
            "self_identification": "Information about gender, pronouns, veteran status, disability, and ethnicity.",
            "legal_authorization": "Details about work authorization and visa requirements.",
            "work_preferences": "Preferences like remote work, relocation, and willingness to complete assessments.",
            "education_details": "Academic background including degrees, universities, and GPA.",
            "experience_details": "Previous job roles, responsibilities, and acquired skills.",
            "projects": "Personal and professional projects worked on.",
            "availability": "Notice period and availability for new roles.",
            "salary_expectations": "Expected salary range.",
            "certifications": "Professional certifications and licenses.",
            "languages": "Spoken languages and proficiency levels.",
            "interests": "Personal and professional interests.",
            "cover_letter": "Cover letter content tailored to a job."
        }

        section_prompt = f"""
        Based on the following question: "{question}",
        determine the most relevant section of the resume.

        Sections:
        {json.dumps(sections, indent=2)}

        Respond with the exact name of the section only (e.g., "experience_details", "projects").
        """

        section_name = self.query(section_prompt).strip().lower().replace(" ", "_")

        resume_section = getattr(self.resume, section_name, None) or getattr(
            self.job_application_profile, section_name, None
        )

        if resume_section is None:
            raise ValueError(f"Section '{section_name}' not found in resume or job profile.")

        return self.query(f"Using the following resume section: {resume_section}, answer: {question}")

    def answer_question_numeric(self, question: str, default_experience: int = 3) -> int:
        """
        Estimate the number of years of experience required based on the resume.
        """
        prompt = f"Based on the resume, estimate the number of years of experience for the question: '{question}'. Return only the number."
        response = self.query(prompt)
        numbers = re.findall(r"\d+", response)
        return int(numbers[0]) if numbers else default_experience

    def generate_cover_letter(self, job):
        job_desc = job.description
        ai_generated_text = self._generate_text(job_desc)  # Call AI Model

        cover_letter = strings.coverletter_template.format(
            job_title=job.title,
            company_name=job.company,
            job_description=job_desc,
            generated_text=ai_generated_text
        )

        return cover_letter

    def resume_or_cover(self, phrase: str) -> str:
        """
        Determine if a given phrase relates to a resume or a cover letter.
        """
        prompt = f"Is the phrase '{phrase}' about a resume or a cover letter? Respond with 'resume' or 'cover'."
        response = self.query(prompt).strip().lower()
        return "resume" if "resume" in response else "cover"