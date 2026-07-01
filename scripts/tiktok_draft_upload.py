"""
Local-only TikTok Studio draft uploader placeholder.

Install Playwright and implement the selectors for your account flow before use:
  python -m pip install playwright
  python -m playwright install chromium

This script is intentionally not wired into the backend. Run it manually with
your own cookies/profile when you want draft automation.
"""

from pathlib import Path


def main() -> None:
    cookies = Path("cookies.json")
    if not cookies.exists():
        raise SystemExit("cookies.json not found. Export your own TikTok Studio cookies first.")
    raise SystemExit("Draft upload automation is not enabled yet. Implement account-specific Playwright selectors.")


if __name__ == "__main__":
    main()
