# Configuration-Driven Web Extractor

This is a powerful, CLI-based web scraping tool built with Python. It uses a flexible configuration system to allow scraping different websites without changing the core code.

## Setup

1. **Create a virtual environment:**

```bash
python -m venv venv
# If above don't work
python -m venv .venv --without-pip
# On Mac
source venv/bin/activate  
# On Windows
venv\Scripts\activate
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers:**

```bash
playwright install chromium
```

## How to Use

### 1. Create Configuration File

- In the `config/` directory, create a file: `your_job.yaml`.


### 2. Create Session File (for login-protected sites)

- Run the following command and log in to the website:

```bash
playwright codegen --save-storage=state/your_job.json (login website)
```

- Example: login at [https://www.scrapingcourse.com/login](https://www.scrapingcourse.com/login)  
- Your login credentials will be saved in the session file.

### 3. Example Config File with Pagination

```yaml
site:
  name: MyEcommerceSite
  base_url: "https://www.scrapingcourse.com"

runtime:
  concurrency: 5
  sleep_ms_between_pages: 1500   
  stop_after_n_errors: 50

module:
  name: products
  entities:
    - name: ProductList
      url: "/pagination/"
      paginate:
        type: "next_button"
        selector: "a.next-page"
        max_pages: 20
      row_selector: "div.product-item"
      fields:
        detail_url: "a@href"

    - name: ProductDetail
      follow_from: "ProductList.detail_url"
      row_selector: "div.summary"
      fields:
        product_name: "h1.product_title"
        price: "p.price"
        description: "div.woocommerce-product-details__short-description"
        sku: "span.sku"
        category: ".posted_in > a"

output:
  dir: "./output"
  formats: ["csv", "json"]
  primary_key: ["product_name"]
```
### 3. Example Config File with Login
```yaml
site:
  name: MyEcommerceSite
  base_url: "https://www.scrapingcourse.com"

auth:
  session_file: "state/scrapingcourse_session.json"

runtime:
  concurrency: 5
  sleep_ms_between_pages: 1500
  stop_after_n_errors: 50

module:
  name: products
  entities:
    - name: ProductList
      url: "/dashboard/"
      row_selector: "div.product-item"
      fields:
        detail_url: "a@href"

    - name: ProductDetail
      follow_from: "ProductList.detail_url"
      row_selector: "div.summary"
      fields:
        product_name: "h1.product_title"
        price: "p.price"
        description: "div.woocommerce-product-details__short-description"
        sku: "span.sku"
        category: ".posted_in > a"
output:
  dir: "./output"
  formats: ["csv", "json"]
  primary_key: ["product_name"]
```
### 4. Run the Scraper

- **Browser open (operations visible on screen):**

```bash
python -m web_extractor.main --no-headless your_job
```

- **Browser closed (headless mode, runs in background):**
```bash
python -m web_extractor.main --headless your_job
```
### 5. Find Your Data

- Session files are saved in the `state/` directory.  
- Scraped data is saved in the `output/` directory.  
- Job reports are saved in the `reports/` directory.  

## Features

- **Config-Driven:** Define scrape targets and data fields in simple YAML files.  
- **CLI Interface:** Easy to run and integrate into scripts.  
- **Robust Scraping:** Uses Playwright and BeautifulSoup4 for modern, JavaScript-heavy sites.  
- **Anti-Scraping Evasion:** Implements `playwright-stealth` to avoid common bot detection.    
- **Multiple Export Formats:** Save results as CSV, JSON, or XLSX.
