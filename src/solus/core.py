import atexit
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class SolusError(Exception):
    pass


class ClosedError(SolusError):
    pass


class ResponseTimeoutError(SolusError):
    pass


class Solus:
    GEMINI_URL = "https://gemini.google.com/"
    LOGIN_URL = (
        "https://accounts.google.com/v3/signin/identifier?continue=https%3A%2F%2Fgemini"
        ".google.com%2Fsignin%3Fcontinue%3Dhttps%3A%2F%2Fgemini.google.com%2Fapp%3Fhl%253Den"
        "&followup=https%3A%2F%2Fgemini.google.com%2Fsignin%3Fcontinue%3Dhttps%3A%2F%2Fgemini"
        ".google.com%2Fapp%3Fhl%253Den&flowName=GlifWebSignIn&flowEntry=ServiceLogin"
    )
    LOGGED_IN_SELECTOR = (
        '[data-test-id="side-nav-sparkle-button"], [data-test-id="new-chat-button"]'
    )
    INPUT_SELECTOR = "div.ql-editor"
    RESPONSE_SELECTOR = ".markdown-main-panel"
    GENERATING_SELECTOR = 'button[aria-label="Stop response"]'
    STREAM_URL_PART = "StreamGenerate"
    LOCALE = "en-US"
    FIRST_RESPONSE_TIMEOUT_MS = 45000
    GENERATION_START_GRACE_MS = 3000
    MAX_WAIT_SECONDS = 60
    STABLE_CYCLES_TO_COMPLETE = 5
    LOGIN_CHECK_TIMEOUT_MS = 5000
    LOGIN_TIMEOUT_MS = 300000
    DEFAULT_PROFILE_DIR = str(Path.home() / ".solus" / "chrome-profile")

    def __init__(self, system_prompt=None, headless=True, channel="chrome",
                 persistent_session=False, profile_dir=None):
        self._closed = False
        self._headless = headless
        self._channel = channel
        self._browser = None
        self._context = None
        self._playwright = sync_playwright().start()

        if persistent_session:
            self._profile_dir = profile_dir or self.DEFAULT_PROFILE_DIR
            Path(self._profile_dir).mkdir(parents=True, exist_ok=True)
            self._context = self._launch_context(headless)
            self._page = self._context.new_page()
            self._page.goto(self.GEMINI_URL)
            self._ensure_logged_in()
        else:
            self._browser = self._playwright.chromium.launch(headless=headless, channel=channel)
            self._page = self._browser.new_page(locale=self.LOCALE)
            self._page.goto(self.GEMINI_URL)

        atexit.register(self.quit)

        if system_prompt:
            self.send_message(system_prompt)

    def _launch_context(self, headless):
        return self._playwright.chromium.launch_persistent_context(
            self._profile_dir, headless=headless, channel=self._channel, locale=self.LOCALE
        )

    def _reopen_page(self, headless, url=None):
        self._context.close()
        self._context = self._launch_context(headless)
        self._page = self._context.new_page()
        self._page.goto(url or self.GEMINI_URL)

    def _ensure_logged_in(self):
        try:
            self._page.wait_for_selector(self.LOGGED_IN_SELECTOR,
                                          timeout=self.LOGIN_CHECK_TIMEOUT_MS)
            return
        except PlaywrightTimeoutError:
            pass

        self._reopen_page(headless=False, url=self.LOGIN_URL)
        self._page.wait_for_selector(self.LOGGED_IN_SELECTOR, timeout=self.LOGIN_TIMEOUT_MS)

        if self._headless:
            self._reopen_page(headless=True)
            self._page.wait_for_selector(self.LOGGED_IN_SELECTOR,
                                          timeout=self.LOGIN_CHECK_TIMEOUT_MS)

    def _submit(self, prompt):
        self._page.locator(self.INPUT_SELECTOR).fill(prompt)
        self._page.keyboard.press("Enter")

    def _is_stream_response(self, response):
        return response.request.method == "POST" and self.STREAM_URL_PART in response.url

    def _send_via_stream(self, prompt):
        try:
            with self._page.expect_response(self._is_stream_response,
                                             timeout=self.FIRST_RESPONSE_TIMEOUT_MS) as resp_info:
                self._submit(prompt)
        except PlaywrightTimeoutError:
            return None

        try:
            resp_info.value.finished()
            return self._extract_response_text()
        except Exception:
            return None

    def send_message(self, prompt: str) -> str:
        if self._closed:
            raise ClosedError("Solus instance has already been closed.")

        text = self._send_via_stream(prompt)
        if text is not None:
            return text

        try:
            self._page.wait_for_selector(self.RESPONSE_SELECTOR,
                                          timeout=self.FIRST_RESPONSE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            raise ResponseTimeoutError(
                "Response did not appear in time; the selector may have changed."
            )

        return self._wait_for_generation_to_finish()

    def _wait_for_generation_to_finish(self) -> str:
        try:
            self._page.wait_for_selector(self.GENERATING_SELECTOR,
                                          timeout=self.GENERATION_START_GRACE_MS)
            self._page.wait_for_selector(
                self.GENERATING_SELECTOR, state="hidden", timeout=self.MAX_WAIT_SECONDS * 1000
            )
            return self._extract_response_text()
        except PlaywrightTimeoutError:
            return self._wait_for_full_response()

    def _extract_response_text(self) -> str:
        text = self._page.locator(self.RESPONSE_SELECTOR).last.inner_text()
        return re.sub(r"\n{2,}", "\n", text).strip()

    def _wait_for_full_response(self) -> str:
        last_text = ""
        stable_cycles = 0
        total_cycles = 0

        while total_cycles < self.MAX_WAIT_SECONDS:
            current_text = self._page.locator(self.RESPONSE_SELECTOR).last.inner_text()

            if current_text != last_text and len(current_text) > 0:
                last_text = current_text
                stable_cycles = 0
            else:
                stable_cycles += 1

            time.sleep(1)
            total_cycles += 1

            if stable_cycles >= self.STABLE_CYCLES_TO_COMPLETE and len(last_text) > 0:
                break

        return re.sub(r"\n{2,}", "\n", last_text).strip()

    def quit(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._context is not None:
                self._context.close()
            elif self._browser is not None:
                self._browser.close()
        finally:
            self._playwright.stop()
