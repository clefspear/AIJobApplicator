import os
import random
import time
import traceback
from itertools import product
from pathlib import Path
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from src.gpt import GPTAnswerer
import src.strings as strings
from src.job_application_profile import JobApplicationProfile
import src.utils as utils
from src.job import Job
from src.linkedIn_easy_applier import LinkedInEasyApplier
import json


class EnvironmentKeys:
    def __init__(self):
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")

    @staticmethod
    def _read_env_key(key: str) -> str:
        return os.getenv(key, "")

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        return os.getenv(key) == "True"

class LinkedInJobManager:
    def __init__(self, driver, gpt_answerer, job_application_profile, resume_generator_manager):
        self.driver = driver
        self.gpt_answerer = gpt_answerer
        self.job_application_profile = job_application_profile
        self.resume_generator_manager = resume_generator_manager  # ✅ Store resume generator
        self.set_old_answers = set()
        self.easy_applier_component = None

    def set_parameters(self, parameters):
        self.company_blacklist = parameters.get('companyBlacklist', []) or []
        self.title_blacklist = parameters.get('titleBlacklist', []) or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []
        resume_path = parameters.get('uploads', {}).get('resume', None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.output_file_directory = Path(parameters['outputFileDirectory'])
        self.env_config = EnvironmentKeys()

    def set_gpt_answerer(self, gpt_answerer):
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        self.resume_generator_manager = resume_generator_manager

    def start_applying(self):
        self.easy_applier_component = LinkedInEasyApplier(
            self.driver, self.resume_path, self.set_old_answers, self.gpt_answerer, self.resume_generator_manager
        )
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)

        for position, location in searches:
            location_url = "&location=" + location
            job_page_number = -1
            utils.printyellow(f"🚀 Starting the search for {position} in {location}.")

            try:
                while True:
                    job_page_number += 1
                    utils.printyellow(f"🔍 Going to job page {job_page_number}")
                    self.next_job_page(position, location_url, job_page_number)
                    time.sleep(random.uniform(1.5, 3.5))
                    utils.printyellow("📝 Starting the application process for this page...")
                    self.apply_jobs()
                    utils.printyellow("✅ Applying to jobs on this page has been completed!")

                    time.sleep(random.randint(10, 30))
            except Exception as e:
                print(f"⚠️ Error processing jobs: {e}")
                continue

    def extract_job_information_from_tile(self, job_element):
        """Extracts job information from a LinkedIn job tile based on the updated HTML structure."""
        try:
            # Wait until the job title appears
            wait = WebDriverWait(self.driver, 5)  # 5-second timeout

            # Update selectors based on the new structure
            title = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.job-card-list__title"))).text
            company = job_element.find_element(By.CSS_SELECTOR, "span.job-card-container__company-name").text
            location = job_element.find_element(By.CSS_SELECTOR, "span.job-search-card__location").text
            job_link = job_element.find_element(By.TAG_NAME, "a").get_attribute("href")

            # Check if "Easy Apply" is present
            try:
                easy_apply = job_element.find_element(By.CLASS_NAME, "job-card-container__apply-method").text
                apply_method = "Easy Apply" if "Easy Apply" in easy_apply else "Standard"
            except NoSuchElementException:
                apply_method = "Standard"

            return title, company, location, job_link, apply_method

        except TimeoutException:
            print(f"⚠️ Timeout: The job information elements did not load in time.")
        except NoSuchElementException:
            print(f"⚠️ Error: Could not find job title or other elements. LinkedIn may have changed its structure.")
        except Exception as e:
            print(f"⚠️ Unexpected error extracting job info: {e}")

        return None, None, None, None, None


    def apply_jobs(self):
        try:
            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-two-pane__no-results-banner--expand')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                raise Exception("No more jobs on this page")
        except NoSuchElementException:
            pass
        
        try:
            job_results = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "scaffold-layout__list-detail-container"))
            )
        except Exception:
            print("⚠️ Job results list not found. LinkedIn may have changed its layout or the page hasn't fully loaded.")
            return
        utils.scroll_slow(self.driver, job_results)
        utils.scroll_slow(self.driver, job_results, step=300, reverse=True)
        # Wait for the job list container to load
        job_results = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "scaffold-layout__list-detail-container"))
        )
        job_list_container = self.driver.find_element(By.CLASS_NAME, "scaffold-layout__list-detail-container")
        job_list_elements = job_list_container.find_elements(By.TAG_NAME, "li")  # Jobs are inside <li> tags
        
        # Debugging: Print extracted jobs
        for job in job_list_elements:
            print(job.text)  # Verify that jobs are being detected
            
        if not job_list_elements:
                print("⚠️ No job listings found on this page. Moving to the next page...")
                return
        job_list = [Job(*self.extract_job_information_from_tile(job_element)) for job_element in job_list_elements] 
        for job in job_list:
            if self.is_blacklisted(job.title, job.company, job.link):
                utils.printyellow(f"🚫 Blacklisted {job.title} at {job.company}, skipping...")
                self.write_to_file(job, "skipped")
                continue
            try:
                if job.apply_method not in {"Continue", "Applied", "Apply"}:
                    self.easy_applier_component.job_apply(job)
                    self.write_to_file(job, "success")
            except Exception as e:
                utils.printred(traceback.format_exc())
                self.write_to_file(job, "failed")
                continue
    def _handle_standard_apply(self, job, resume_text, cover_letter_text):
        try:
            print("Redirecting to an external application site.")
            WebDriverWait(self.driver, 10).until(
                lambda d: "apply" in d.current_url or "careers" in d.current_url
            )

            try:
                resume_input = self.driver.find_element(By.XPATH, "//input[@type='file']")
                resume_input.send_keys(resume_text)
            except Exception:
                print("No resume upload field found.")

            try:
                cover_letter_field = self.driver.find_element(By.XPATH, "//textarea[contains(@name, 'coverLetter')]")
                cover_letter_field.send_keys(strings.coverletter_template.format(job_description=job.description, resume=resume_text))
            except Exception:
                print("No cover letter field found.")

            try:
                self._fill_application_fields()
            except Exception as e:
                print(f"Error filling application fields: {e}")

            try:
                submit_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'Apply')]")
                submit_button.click()
                print(f"Successfully applied to {job.title} at {job.company} via standard apply.")
            except Exception:
                print("Could not submit application. Manual review needed.")
        except Exception as e:
            print(f"Error handling external application: {e}")

    def handle_external_application(self, job):
        print(f"\n🌍 Applying on external site for: {job.title} at {job.company}")
        self.driver.get(job.link)
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        ai_cover_letter = self.gpt_answerer.generate_cover_letter(job)
        ai_resume = self.gpt_answerer.generate_resume(job)

        try:
            apply_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Apply') or contains(text(), 'Easy Apply')]"))
            )
            apply_button.click()
        except Exception:
            print("Apply button not found. Skipping application.")
            return

        time.sleep(2)

        if "Easy Apply" in apply_button.text:
            self._handle_easy_apply(job, ai_resume, ai_cover_letter)
        else:
            self._handle_standard_apply(job, ai_resume, ai_cover_letter)
    def _fill_application_fields(self):
        """Fills out application fields using job application profile data."""
        fields = {
            "gender": self.job_application_profile.self_identification.gender,
            "pronouns": self.job_application_profile.self_identification.pronouns,
            "work_auth": self.job_application_profile.legal_authorization.us_work_authorization,
            "remote": self.job_application_profile.work_preferences.remote_work,
            "relocate": self.job_application_profile.work_preferences.open_to_relocation,
            "notice": self.job_application_profile.availability.notice_period,
            "salary": self.job_application_profile.salary_expectations.salary_range_usd,
        }

        for field, value in fields.items():
            try:
                input_element = self.driver.find_element(By.NAME, field)
                input_element.clear()
                input_element.send_keys(value)
            except NoSuchElementException:
                print(f"Field {field} not found.")
    def write_to_file(self, job, file_name):
        data = {
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "job_recruiter": job.recruiter_link,
            "job_location": job.location,
            "pdf_path": Path(job.pdf_path).resolve().as_uri(),
        }
        file_path = self.output_file_directory / f"{file_name}.json"
        if not file_path.exists():
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([data], f, indent=4)
        else:
            with open(file_path, 'r+', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []
                existing_data.append(data)
                f.seek(0)
                json.dump(existing_data, f, indent=4)
                f.truncate()

    def get_base_search_url(self, parameters):
        url_parts = []
        
        if parameters['remote']:
            url_parts.append("f_CF=f_WRA")
        if parameters['onsite']:
            url_parts.append("f_CF=f_ON")

        experience_levels = [str(i+1) for i, (level, v) in enumerate(parameters.get('experienceLevel', {}).items()) if v]
        if experience_levels:
            url_parts.append(f"f_E={','.join(experience_levels)}")

        url_parts.append(f"distance={parameters['distance']}")

        job_types = [key[0].upper() for key, value in parameters.get('jobTypes', {}).items() if value]
        if job_types:
            url_parts.append(f"f_JT={','.join(job_types)}")

        # ✅ Add Date Filtering Logic
        date_filter_map = {
            "all time": None,
            "month": "f_TPR=r2592000",
            "week": "f_TPR=r604800",
            "24 hours": "f_TPR=r86400"  # ✅ This is the filter for last 24 hours
        }
        
        for key, value in parameters.get('date', {}).items():
            if value and key in date_filter_map:
                date_filter = date_filter_map[key]
                if date_filter:
                    url_parts.append(date_filter)
                break  # Only apply the first matched filter

        return f"?{'&'.join(url_parts)}"

    def next_job_page(self, position, location, job_page):
        self.driver.get(f"https://www.linkedin.com/jobs/search/{self.base_search_url}&keywords={position}{location}&start={job_page * 25}")

    def is_blacklisted(self, job_title, company, link):
        return any([
            job_title.lower() in self.title_blacklist,
            company.lower() in self.company_blacklist,
            link in self.seen_jobs
        ])
