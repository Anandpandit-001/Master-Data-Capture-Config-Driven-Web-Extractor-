<<<<<<< HEAD
# Configuration-Driven Web Extractor

This is a powerful, CLI-based web scraping tool built with Python. It uses a flexible configuration system to allow scraping different websites without changing the core code.

## Features

- **Config-Driven:** Define scrape targets and data fields in simple YAML files.
- **CLI Interface:** Easy to run and integrate into scripts.
- **Robust Scraping:** Uses Playwright and BeautifulSoup4 for modern, JavaScript-heavy sites.
- **Anti-Scraping Evasion:** Implements `playwright-stealth` to avoid common bot detection.
- **Resumable Jobs:** Automatically saves and resumes scraping progress.
- **Data Validation:** Uses Pydantic to ensure data quality based on your schema.
- **Multiple Export Formats:** Save results as CSV, JSON, or XLSX.

## Setup

1.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install Playwright browsers:**
    ```bash
    playwright install chromium
    ```

## How to Use

1.  **Create Configuration Files:**
    - In the `jobs/` directory, create two files: `my_job_static.yml` and `my_job_dynamic.yml`.
    - Populate them based on the provided `example_job_*.yml` files.

2.  **Run the Scraper:**
    - Execute the scraper from your terminal using the `main.py` script.
    - The `job-name` is the base name of your config files (e.g., `my_job`).

    ```bash
    python -m web_extractor.main run my_job
    ```

3.  **Find Your Data:**
    - The scraped data will be saved in the `output/` directory.
    - The job's progress will be saved in the `state/` directory.
=======
# Config-Driven Web Extractor

This is a powerful, asynchronous, command-line web scraping tool built with Python. It uses a flexible YAML configuration system to allow scraping different websites without changing the core code.



## Features

-   **Config-Driven**: Define scrape targets and data fields in simple YAML files.
-   **Asynchronous**: Built with `asyncio` and `playwright.async_api` for high-performance scraping.
-   **Robust Scraping**: Uses Playwright for modern, JavaScript-heavy sites and BeautifulSoup4 for efficient parsing.
-   **Anti-Scraping Evasion**: Implements `playwright-stealth` to avoid common bot detection.
-   **Resumable Jobs**: Automatically saves and resumes scraping progress from a state file.
-   **Data Validation**: Uses Pydantic to ensure data quality based on your schema.
-   **Multiple Export Formats**: Save results as CSV, JSON, or XLSX.

---
## 1. Setup

Follow these steps to set up the project environment.

#### **Step 1: Create and Activate Virtual Environment**
This isolates your project's dependencies. From the project's root directory, run:

```bash
# Create the environment
python -m venv .venv --without-pip

# Activate the environment (on Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate the environment (on macOS/Linux)
source .venv/bin/activate
```
our terminal prompt should now start with (.venv).

#### **Step 2: Install Python Libraries**
This command installs Playwright, Typer, Pydantic, and all other required libraries.

```bash

pip install -r requirements.txt
```
#### **Step 3: Install Playwright's Browser**
Playwright needs a browser binary to control. This command installs Chromium.

```bash

playwright install chromium
```
## 2. How to Use
#### **Step 1: Configure Your Job**
Go to the jobs/ directory.

Create two files: my_job_static.yml and my_job_dynamic.yml.

Use the example_job_*.yml files as a template.

#### **Step 2: Run the Scraper**
Execute the scraper from your terminal. The job-name argument is the base name of your config files (e.g., for example_job_static.yml, the name is example_job).

```bash

python -m web_extractor.main run example_job
```
#### **Step 3: Run in Debug Mode (Optional)**
To watch the browser operate in real-time, use the --no-headless flag.

```bash

python -m web_extractor.main run example_job --no-headless
```
#### **Step 4: Find Your Data**
Scraped data is saved in the output/ folder.

Job progress is saved in the state/ folder.

## 3. Troubleshooting Common Errors
Here is a guide to resolving errors you might encounter.

Error: ModuleNotFoundError: No module named 'yaml' (or any other module)
Why it happens: The required library is not installed in your active virtual environment. You might see a "Requirement already satisfied" message pointing to a different Python installation (like Anaconda).

Solution:

Make sure your virtual environment is active (you see (.venv) in your terminal).

Run the installation command again:

```bash

pip install -r requirements.txt
```
Error: ImportError or ModuleNotFoundError for playwright_stealth
Why it happens: The playwright-stealth library has changed its structure in recent versions. An old version might be installed, or the code's import statement might be outdated.

Solution:

First, upgrade the library to the latest version:

```bash

pip install --upgrade playwright-stealth
```
Ensure your web_extractor/core/browser_manager.py uses the correct modern import:

```Python

from playwright_stealth.async_api import stealth_async
```
Ensure you call it correctly on the page object:

```Python

await stealth_async(page)
```
Error: Got unexpected extra argument...
Why it happens: You are providing the job_name incorrectly in the command. This error occurs if you provide the full filename instead of the base name.

Solution: Use only the base name of the job files.

Incorrect: python -m web_extractor.main run example_job_static.yml

Correct: python -m web_extractor.main run example_job

Error: TypeError: '...' object is not callable or AttributeError
Why it happens: This usually means you are calling a function incorrectly. For example, the traceback AttributeError: 'Browser' object has no attribute 'chromium' means the stealth function was applied to the wrong object.

Solution: Ensure your code matches the final correct versions provided. Specifically, stealth_async(page) must be applied to the page object inside the new_page method of the BrowserManager.

Error: UnicodeEncodeError: 'charmap' codec can't encode character...
Why it happens: This is a Windows-specific error where the logger tries to write a special character (like an emoji) to the log file, but the file is not opened with the correct encoding.

Solution:

Open web_extractor/utils/logging_config.py.

Ensure the FileHandler is set to use UTF-8:

```Python

logging.FileHandler("scraper.log", encoding="utf-8")
```
>>>>>>> 5b268333b44596952c17f8c74c1f82b7fe562477
