from __future__ import unicode_literals, print_function, absolute_import

import sys
from base64 import b64decode as b64d
from io import BytesIO

try:  # Python 3
    from urllib.parse import urlsplit
except ImportError:  # pragma: no cover - Python 2 fallback
    from urlparse import urlsplit

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from PIL import Image
from scihub2pdf.tools import download_pdf

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Tried in order; the first reachable mirror that serves the PDF wins.
DEFAULT_MIRRORS = [
    "https://sci-hub.st/",
    "https://sci-hub.ist/",
    "https://sci-hub.ru/",
    "https://sci-hub.se/",
]


def normalize_mirrors(value):
    """Return a clean, trailing-slash list of mirror URLs from a str or list."""
    items = [value] if isinstance(value, str) else list(value or [])
    mirrors = []
    for item in items:
        item = (item or "").strip()
        if not item:
            continue
        if not item.endswith("/"):
            item += "/"
        if item not in mirrors:
            mirrors.append(item)
    return mirrors

# Ordered (css_selector, attribute) pairs used to locate the PDF on a modern
# Sci-Hub article page. Selenium resolves href/src/data to absolute URLs, so
# those are preferred over the relative ``citation_pdf_url`` meta tag.
PDF_SELECTORS = [
    (".download a", "href"),
    ("object[type='application/pdf']", "data"),
    ("embed#pdf", "src"),
    ("iframe#pdf", "src"),
    ("#pdf", "src"),
    ("meta[name='citation_pdf_url']", "content"),
]


class SciHub(object):
    """Download PDFs from a Sci-Hub mirror using headless Chrome (Selenium 4)."""

    def __init__(self,
                 headers=None,
                 xpath_captcha="//*[@id='captcha']",
                 xpath_pdf="//*[@id='pdf']",
                 xpath_input="/html/body/div/table/tbody/tr/td/form/input",
                 xpath_form="/html/body/div/table/tbody/tr/td/form",
                 domain_scihub=None,
                 ):
        self.xpath_captcha = xpath_captcha
        self.xpath_input = xpath_input
        self.xpath_form = xpath_form
        self.xpath_pdf = xpath_pdf
        self.domains = normalize_mirrors(domain_scihub) or list(DEFAULT_MIRRORS)
        self.active_domain = self.domains[0]
        self._reachable = None
        self.headers = dict(headers) if headers else {}
        self.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

        self.driver = None
        self.s = None
        self.sci_url = None
        self.pdf_url = None
        self.doi = None
        self.pdf_file = None
        self.el_captcha = None
        self.el_input_text = None
        self.el_form = None
        self.has_captcha = False

    def start(self):
        try:
            self.s = requests.Session()
            self.s.headers.update(self.headers)
            options = ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-size=1120,1000")
            options.add_argument("user-agent=" + self.headers["User-Agent"])
            # Selenium 4 (>=4.6) ships Selenium Manager, which resolves a
            # matching chromedriver automatically.
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as e:
            print("\n\t Could not start headless Chrome for Sci-Hub.")
            print("\t Make sure Google Chrome is installed and up to date.")
            print("\t Selenium error:", str(e).splitlines()[0])
            sys.exit(1)

    def _sync_cookies(self):
        if self.driver is None:
            return
        for cookie in self.driver.get_cookies():
            self.s.cookies.set(cookie["name"], cookie["value"])

    def get_session(self):
        self._sync_cookies()
        return self.s

    def _reachable_domains(self):
        if self._reachable is not None:
            return self._reachable
        reachable = []
        for domain in self.domains:
            try:
                resp = self.s.get(domain, timeout=8, allow_redirects=True)
                if resp.status_code < 500:
                    reachable.append(domain)
                else:
                    print("\tMirror", domain, "returned", resp.status_code,
                          "- skipping")
            except requests.RequestException:
                print("\tMirror", domain, "unreachable - skipping")
        self._reachable = reachable
        return reachable

    def navigate_to(self, doi, pdf_file):
        self.doi = doi
        self.pdf_file = pdf_file
        print("\n\tDOI: ", doi)
        domains = self._reachable_domains()
        if not domains:
            print("\tNo Sci-Hub mirror is reachable right now.")
            return False, None
        for domain in domains:
            url = domain + doi
            print("\tSci-Hub Link: ", url)
            try:
                self.driver.get(url)
            except WebDriverException as e:
                print("\t  could not load:", str(e).splitlines()[0])
                continue
            self.active_domain = domain
            self.sci_url = url
            found_pdf, _ = self.get_pdf_url()
            if found_pdf:
                return True, None
            print("\t  no PDF on this mirror, trying next...")
        return False, None

    def _find_attr(self, selector, attribute):
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            return None
        return el.get_attribute(attribute) or None

    def _absolutize(self, url):
        url = url.split("#")[0].strip()
        if url.startswith("//"):
            return "http:" + url
        if url.startswith("/"):
            parts = urlsplit(self.active_domain)
            return "{}://{}{}".format(parts.scheme, parts.netloc, url)
        return url

    def get_pdf_url(self):
        for selector, attribute in PDF_SELECTORS:
            raw = self._find_attr(selector, attribute)
            if raw:
                self.pdf_url = self._absolutize(raw)
                print("\tPDF URL: ", self.pdf_url)
                return True, self.pdf_url
        self.pdf_url = None
        return False, None

    # --- Captcha handling (best effort; modern mirrors rarely use it) ---
    def _get_el(self, xpath):
        try:
            return True, self.driver.find_element(By.XPATH, xpath)
        except NoSuchElementException:
            return False, None

    def check_captcha(self):
        self.has_captcha, self.el_captcha = self._get_el(self.xpath_captcha)
        if self.has_captcha:
            _, self.el_input_text = self._get_el(self.xpath_input)
            _, self.el_form = self._get_el(self.xpath_form)
        return self.has_captcha

    def get_captcha_img(self):
        location = self.el_captcha.location
        size = self.el_captcha.size
        png = b64d(self.driver.get_screenshot_as_base64())
        image = Image.open(BytesIO(png))
        left = location["x"]
        top = location["y"]
        right = left + size["width"]
        bottom = top + size["height"]
        return image.crop((left, top, right, bottom))

    def solve_captcha(self, captcha_text):
        if self.el_input_text is not None and self.el_form is not None:
            self.el_input_text.send_keys(captcha_text)
            self.el_form.submit()
        self.navigate_to(self.doi, self.pdf_file)
        return self.check_captcha()

    def download(self):
        self._sync_cookies()
        found, r = download_pdf(self.s, self.pdf_file, self.pdf_url, self.headers)
        if not found and self.driver is not None:
            try:
                self.driver.save_screenshot(self.pdf_file + ".png")
            except WebDriverException:
                pass
        return found, r

    def quit(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None
