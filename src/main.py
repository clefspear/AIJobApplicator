import os
import re
import sys
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from lib_resume_builder_AIHawk import Resume, StyleManager, FacadeManager, ResumeGenerator
from src.utils import chromeBrowserOptions
from src.gpt import GPTAnswerer
from src.linkedIn_authenticator import LinkedInAuthenticator
from src.linkedIn_bot_facade import LinkedInBotFacade
from src.linkedIn_job_manager import LinkedInJobManager
from src.job_application_profile import JobApplicationProfile

sys.stderr = open(os.devnull, 'w')  # Suppress stderr logs

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None

    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"🚨 Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"❌ File not found: {yaml_path}")

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> tuple:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        mandatory_secrets = ['email', 'password', 'openai_api_key']

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"⚠️ Missing secret '{secret}' in {secrets_yaml_path}")

        if not ConfigValidator.validate_email(secrets['email']):
            raise ConfigError(f"❌ Invalid email format in {secrets_yaml_path}.")
        if not secrets['password']:
            raise ConfigError(f"⚠️ Password cannot be empty in {secrets_yaml_path}.")
        if not secrets['openai_api_key']:
            raise ConfigError(f"⚠️ OpenAI API key cannot be empty in {secrets_yaml_path}.")

        return secrets['email'], secrets['password'], secrets['openai_api_key']

class FileManager:
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"❌ Data folder not found: {app_data_folder}")

        required_files = ['secrets.yaml', 'config.yaml', 'plain_text_resume.yaml']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"⚠️ Missing files in data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', output_folder)

    @staticmethod
    def file_paths_to_dict(resume_file: Path | None, plain_text_resume_file: Path) -> dict:
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"❌ Plain text resume file not found: {plain_text_resume_file}")

        result = {'plainTextResume': plain_text_resume_file}

        if resume_file:
            if not resume_file.exists():
                raise FileNotFoundError(f"❌ Resume file not found: {resume_file}")
            result['resume'] = resume_file

        return result

def init_browser() -> webdriver.Chrome:
    try:
        print("🌍 Setting up Chrome browser...")
        options = chromeBrowserOptions()
        service = ChromeService(ChromeDriverManager().install())
        browser = webdriver.Chrome(service=service, options=options)
        print("✅ Chrome browser initialized successfully.")
        return browser
    except WebDriverException as e:
        print("❌ Error: WebDriver failed to initialize. LinkedIn may be blocking automation.")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(email: str, password: str, parameters: dict, openai_api_key: str, plain_text_resume_file: Path):
    try:
        print("🔍 Initializing Resume Generation Components...")
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        
        # ✅ Use the correctly passed plain_text_resume_file
        with open(plain_text_resume_file, "r", encoding="utf-8") as f:
            yaml_data = f.read()

        resume_object = Resume(yaml_data)

        print("✅ Resume loaded successfully.")

        resume_generator_manager = FacadeManager(openai_api_key, style_manager, resume_generator, resume_object, Path("data_folder/output"))
        pdf_base64_data = resume_generator_manager.pdf_base64()
        print("📄 PDF Resume Generated Successfully.")

        print("🌐 Initializing Browser...")
        browser = init_browser()
        login_component = LinkedInAuthenticator(browser)
        gpt_answerer_component = GPTAnswerer(openai_api_key)  # ✅ Use API key from secrets.yaml
        job_application_profile_object = JobApplicationProfile(yaml_data)  # ✅ Create job profile
        apply_component = LinkedInJobManager(browser, gpt_answerer_component, job_application_profile_object, resume_generator_manager)

        print("🤖 Setting up LinkedIn Bot...")
        bot = LinkedInBotFacade(login_component, apply_component)
        bot.set_secrets(email, password)
        bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        bot.set_parameters(parameters)
        
        print("🔑 Logging into LinkedIn...")
        bot.start_login()

        print("📩 Starting job applications...")
        bot.start_apply()

        print("🎉 Job application process completed successfully!")
    except WebDriverException as e:
        print(f"❌ WebDriver error occurred: {e}")
    except Exception as e:
        print(f"⚠️ Unexpected Error: {e}")

@click.command()
@click.option('--resume', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), help="Path to the resume PDF file")
def main(resume: Path = None):
    try:
        print("📂 Validating data folder and files...")
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)
        
        print("✅ Loading configuration files...")
        parameters = ConfigValidator.validate_yaml_file(config_file)
        email, password, openai_api_key = ConfigValidator.validate_secrets(secrets_file)
        
        parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        parameters['outputFileDirectory'] = output_folder
        
        print("🚀 Launching job application bot...")
        create_and_run_bot(email, password, parameters, openai_api_key, plain_text_resume_file)  # ✅ Pass it explicitly

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
