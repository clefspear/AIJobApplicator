import os
import random
import time
from selenium import webdriver

chromeProfilePath = os.path.join(os.getcwd(), "chrome_profile", "linkedin_profile")


def ensure_chrome_profile():
    """Ensures the Chrome profile directory exists and returns the profile path."""
    profile_dir = os.path.dirname(chromeProfilePath)
    if not os.path.exists(profile_dir):
        os.makedirs(profile_dir)
    if not os.path.exists(chromeProfilePath):
        os.makedirs(chromeProfilePath)
    return chromeProfilePath


def is_scrollable(element):
    """Checks if an element is scrollable."""
    try:
        scroll_height = element.get_attribute("scrollHeight")
        client_height = element.get_attribute("clientHeight")
        return int(scroll_height) > int(client_height)
    except Exception as e:
        printred(f"⚠️ Error checking scrollability: {e}")
        return False


def scroll_slow(driver, scrollable_element, start=0, end=3600, step=100, reverse=False):
    """Scrolls an element slowly in increments."""
    if step == 0:
        raise ValueError("Step cannot be zero.")

    if reverse:
        start, end = end, start
        step = -step

    try:
        if scrollable_element.is_displayed():
            if not is_scrollable(scrollable_element):
                printyellow("⚠️ The element is not scrollable.")
                return
            if (step > 0 and start >= end) or (step < 0 and start <= end):
                printyellow("⚠️ No scrolling will occur due to incorrect start/end values.")
                return

            for position in range(start, end, step):
                try:
                    driver.execute_script("arguments[0].scrollTop = arguments[1];", scrollable_element, position)
                except Exception as e:
                    printred(f"❌ Error during scrolling: {e}")
                time.sleep(random.uniform(1.0, 2.6))

            driver.execute_script("arguments[0].scrollTop = arguments[1];", scrollable_element, end)
            time.sleep(1)
        else:
            printyellow("⚠️ The element is not visible.")
    except Exception as e:
        printred(f"❌ Exception occurred during scrolling: {e}")


def chromeBrowserOptions():
    """Sets up Chrome browser options for automation."""
    ensure_chrome_profile()
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")  # Start browser maximized
    options.add_argument("--no-sandbox")  # Disable sandboxing for better performance
    options.add_argument("--disable-dev-shm-usage")  # Use temp directory for shared memory
    options.add_argument("--ignore-certificate-errors")  # Ignore SSL certificate errors
    options.add_argument("--disable-extensions")  # Disable browser extensions
    options.add_argument("--disable-gpu")  # Disable GPU acceleration
    options.add_argument("window-size=1200x800")  # Set fixed window size
    options.add_argument("--disable-background-timer-throttling")  # Improve performance in background
    options.add_argument("--disable-backgrounding-occluded-windows")  # Prevent suspension of hidden windows
    options.add_argument("--disable-translate")  # Disable Google Translate popup
    options.add_argument("--disable-popup-blocking")  # Allow popups
    options.add_argument("--no-first-run")  # Disable first-run setup
    options.add_argument("--no-default-browser-check")  # Skip default browser check
    options.add_argument("--disable-logging")  # Reduce logging
    options.add_argument("--disable-autofill")  # Disable autofill
    options.add_argument("--disable-plugins")  # Disable plugins
    options.add_argument("--disable-animations")  # Disable animations
    options.add_argument("--disable-cache")  # Disable cache to force fresh loading
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])  # Reduce automation detection

    # Preferences to reduce unnecessary load
    prefs = {
        "profile.default_content_setting_values.images": 2,  # Disable images for speed
        "profile.managed_default_content_settings.stylesheets": 2,  # Disable stylesheets
    }
    options.add_experimental_option("prefs", prefs)

    if chromeProfilePath:
        initialPath = os.path.dirname(chromeProfilePath)
        profileDir = os.path.basename(chromeProfilePath)
        options.add_argument('--user-data-dir=' + initialPath)
        options.add_argument("--profile-directory=" + profileDir)
    else:
        options.add_argument("--incognito")

    return options


def printred(text):
    """Prints text in red (for errors)."""
    RED = "\033[91m"
    RESET = "\033[0m"
    print(f"{RED}{text}{RESET}")


def printyellow(text):
    """Prints text in yellow (for warnings/info)."""
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    print(f"{YELLOW}{text}{RESET}")