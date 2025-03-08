import json
import os
import textwrap
from datetime import datetime
from typing import Dict, List
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

class GPTAnswerer:
    def __init__(self, openai_api_key, model="gpt-4o"):
        self.llm = ChatOpenAI(model_name=model, openai_api_key=openai_api_key, temperature=0.4)

    def query(self, prompt: str) -> str:
        prompt_template = ChatPromptTemplate.from_template(prompt)
        chain = prompt_template | self.llm | StrOutputParser()
        return chain.invoke({})

    def summarize_job_description(self, text: str) -> str:
        prompt = f"Summarize the following job description in a concise way:\n\n{text}"
        return self.query(prompt)