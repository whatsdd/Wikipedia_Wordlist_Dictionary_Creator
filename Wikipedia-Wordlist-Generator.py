import argparse
import logging
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=level)


# ── Progress bar (stdlib only) ─────────────────────────────────────────────────

class ProgressBar:
    """Inline ASCII progress bar written to stderr so it doesn't pollute output."""

    BAR_WIDTH = 40

    def __init__(self, total: int, label: str = "") -> None:
        self.total = total
        self.label = label
        self.current = 0
        self._draw()

    def update(self, n: int = 1) -> None:
        self.current = min(self.current + n, self.total)
        self._draw()

    def close(self) -> None:
        self.current = self.total
        self._draw()
        sys.stderr.write("\n")
        sys.stderr.flush()

    def _draw(self) -> None:
        if self.total == 0:
            pct = 100
            filled = self.BAR_WIDTH
        else:
            pct = int(self.current * 100 / self.total)
            filled = int(self.BAR_WIDTH * self.current / self.total)
        bar = "#" * filled + "-" * (self.BAR_WIDTH - filled)
        sys.stderr.write(f"\r{self.label} [{bar}] {pct}%  ")
        sys.stderr.flush()


class SpinnerBar:
    """Fallback dot-spinner for when total size is unknown."""

    FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.tick = 0

    def update(self, n: int = 1) -> None:
        self.tick += n
        frame = self.FRAMES[self.tick % len(self.FRAMES)]
        sys.stderr.write(f"\r{self.label} {frame}  ")
        sys.stderr.flush()

    def close(self) -> None:
        sys.stderr.write(f"\r{self.label} done  \n")
        sys.stderr.flush()


# ── Fetch available dumps ──────────────────────────────────────────────────────

def get_wikipedia_dumps(retries: int = 3, delay: int = 5):
    url = "https://dumps.wikimedia.org/other/static_html_dumps/current/"
    logging.info("Fetching available Wikipedia language dumps...")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                html = response.read().decode("utf-8")
            links = re.findall(r'href="(.*?)"', html)
            links = [link for link in links if link != "../"]
            logging.debug("Found %d language dumps.", len(links))
            return url, links
        except OSError as e:
            logging.warning("Attempt %d/%d failed: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay)
    logging.error("Failed to retrieve Wikipedia dumps after %d attempts.", retries)
    return url, []


# ── Download titles for one language ──────────────────────────────────────────

def download_titles(
    url: str,
    language: str,
    save_path: Path,
    force: bool = False,
    retries: int = 3,
    delay: int = 5,
) -> bool:
    if save_path.exists() and not force:
        logging.info("Using cached file: %s", save_path)
        return True

    language_url = urljoin(url, f"{language}/html.lst")
    logging.info("Downloading %s ...", language_url)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(language_url, headers={"Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as response:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    total_kb = int(content_length) // 1024
                    bar = ProgressBar(total_kb, f"  Downloading {language}")
                else:
                    bar = SpinnerBar(f"  Downloading {language}")

                chunks = []
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    bar.update(len(chunk) // 1024)
                bar.close()

            content = b"".join(chunks).decode("utf-8")
            save_path.write_text(content, encoding="utf-8")
            logging.info("Saved to %s", save_path)
            return True
        except OSError as e:
            logging.warning("Attempt %d/%d failed: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay)

    logging.error("Failed to fetch %s after %d attempts.", language_url, retries)
    return False


# ── Language selection ─────────────────────────────────────────────────────────

def display_language_options(links: list) -> None:
    if not links:
        print("No Wikipedia language dumps available.")
        return
    print("Available Wikipedia language dumps:")
    for i, link in enumerate(links, 1):
        print(f"  {i:>3}. {link.strip('/')}")


def fuzzy_select_language(links: list) -> str:
    """Interactive fuzzy search + numeric fallback."""
    stripped = [l.strip("/") for l in links]
    while True:
        query = input("\nSearch language (or enter number): ").strip()

        # Numeric selection
        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(stripped):
                return stripped[idx]
            print(f"  Please enter a number between 1 and {len(stripped)}.")
            continue

        # Fuzzy substring filter
        matches = [(i, lang) for i, lang in enumerate(stripped)
                   if query.lower() in lang.lower()]
        if not matches:
            print(f"  No language matching '{query}'. Try again.")
        elif len(matches) == 1:
            _, lang = matches[0]
            print(f"  Selected: {lang}")
            return lang
        else:
            print(f"  Found {len(matches)} matches:")
            for i, (orig_idx, lang) in enumerate(matches, 1):
                print(f"    {i}. {lang}  (#{orig_idx + 1})")
            sub = input("  Pick a number from the filtered list (or search again): ").strip()
            if sub.isdigit():
                sub_idx = int(sub) - 1
                if 0 <= sub_idx < len(matches):
                    return matches[sub_idx][1]
            print("  Invalid selection, searching again.")


# ── Title cleaning ─────────────────────────────────────────────────────────────

_IP_RE = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
_HASH_RE = re.compile(r"_[0-9a-f]{4,}$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"[;,.!@#%&()]")
_DIGITS_ONLY_RE = re.compile(r"^\d+$")


def clean_titles(
    file_path: Path,
    min_length: int = 3,
    max_length: int = None,
    no_numbers: bool = False,
) -> set:
    """
    Parse the unfiltered dump file and return a set of cleaned words.
    """
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        logging.error("File not found: %s", file_path)
        return set()

    total = len(lines)
    logging.info("Processing %d lines from %s ...", total, file_path.name)
    bar = ProgressBar(total, "  Cleaning  ")

    cleaned: set = set()
    for i, line in enumerate(lines):
        bar.update()
        clean = line.strip()

        # Extract filename component from path, drop extension
        clean = clean.split("/")[-1].split(".")[0]

        # Handle tilde-disambiguated titles
        if "~" in clean:
            clean = clean.split("~")[-1]

        # Strip Wikipedia hash suffixes (_d69e, _b835f1, …)
        clean = _HASH_RE.sub("", clean)

        # Remove unwanted characters
        clean = clean.replace("_", "").replace("-", "")
        clean = clean.replace("(", "").replace(")", "")

        # Skip IP addresses
        if _IP_RE.match(clean):
            continue

        # Split on punctuation
        for word in _SPLIT_RE.split(clean):
            word = word.strip()
            if not word:
                continue
            if no_numbers and _DIGITS_ONLY_RE.fullmatch(word):
                continue
            length = len(word)
            if length < min_length:
                continue
            if max_length is not None and length > max_length:
                continue
            cleaned.add(word)

    bar.close()
    logging.info("Extracted %d unique words.", len(cleaned))
    return cleaned


# ── Password variant generation ────────────────────────────────────────────────

_YEARS = [str(y) for y in range(2015, 2027)]
_NUM_SUFFIXES = ["1", "12", "123", "1234", "12345"]
_SYM_SUFFIXES = ["!", "@", "#", "1!", "123!"]


def generate_password_variants(words: set) -> list:
    """
    Expand a set of base words into realistic human-style password candidates.
    Applies case variants and common numeric/symbol/year suffixes.
    """
    logging.info("Generating password variants for %d base words...", len(words))
    variants: set = set()

    bar = ProgressBar(len(words), "  Variants  ")
    for word in words:
        bar.update()
        lower = word.lower()
        title = word.capitalize()
        upper = word.upper()

        # Plain case forms
        for form in (lower, title, upper):
            variants.add(form)

        # Numeric suffixes on lowercase and title-case
        for suf in _NUM_SUFFIXES:
            variants.add(lower + suf)
            variants.add(title + suf)

        # Year suffixes on title-case (most human-like)
        for year in _YEARS:
            variants.add(title + year)
            variants.add(lower + year)

        # Symbol suffixes on title-case
        for sym in _SYM_SUFFIXES:
            variants.add(title + sym)
            variants.add(lower + sym)

    bar.close()
    result = sorted(variants)
    logging.info("Generated %d password candidates.", len(result))
    return result


# ── Statistics ─────────────────────────────────────────────────────────────────

def print_stats(words: list, base_count: int = None) -> None:
    if not words:
        print("\n[Stats] No words to report.")
        return

    lengths = [len(w) for w in words]
    avg = sum(lengths) / len(lengths)
    shortest = min(words, key=len)
    longest = max(words, key=len)
    first_chars = Counter(w[0] for w in words if w)
    top5 = first_chars.most_common(5)

    print("\n" + "=" * 50)
    print("  WORDLIST STATISTICS")
    print("=" * 50)
    if base_count is not None:
        print(f"  Base words extracted : {base_count:,}")
        print(f"  Password candidates  : {len(words):,}")
    else:
        print(f"  Total words          : {len(words):,}")
    print(f"  Average word length  : {avg:.1f} chars")
    print(f"  Shortest word        : '{shortest}' ({len(shortest)} chars)")
    print(f"  Longest word         : '{longest}' ({len(longest)} chars)")
    print(f"  Top 5 starting chars : {', '.join(f'{c!r}({n})' for c, n in top5)}")
    print("=" * 50)


# ── Popular language presets ───────────────────────────────────────────────────

# Major languages covering both English and widely-spoken non-English Wikipedias.
POPULAR_LANGUAGES = [
    "en",   # English
    "de",   # German
    "fr",   # French
    "es",   # Spanish
    "it",   # Italian
    "pt",   # Portuguese
    "nl",   # Dutch
    "pl",   # Polish
    "ru",   # Russian
    "sv",   # Swedish
    "no",   # Norwegian
    "da",   # Danish
    "fi",   # Finnish
    "ja",   # Japanese
    "zh",   # Chinese
    "ar",   # Arabic
    "tr",   # Turkish
    "ko",   # Korean
]


# ── Cross-platform working dir ─────────────────────────────────────────────────

def get_working_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "wikipedia-dictionary-creator"


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate wordlists / password lists from Wikipedia static HTML dumps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # interactive mode with fuzzy language search
  %(prog)s

  # download Norwegian (Norsk), apply filters, show stats
  %(prog)s --language no --min-length 5 --no-numbers --verbose

  # download Swedish (Svenska) + English and merge
  %(prog)s --language sv,en --min-length 4 --no-numbers

  # generate human-like password candidates from English + Norwegian
  %(prog)s --language en,no --password-mode --min-length 5 --max-length 12

  # download and merge all 18 major language dumps at once
  %(prog)s --popular --password-mode --min-length 5

  # force re-download to a custom directory
  %(prog)s --language en --force --output-dir /tmp/wordlists
""",
    )
    parser.add_argument(
        "--language", "-l",
        nargs="+",
        metavar="CODE",
        help="Language code(s) to download, e.g. 'en' or 'en,no,de' or 'en' 'no'",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Directory to save output files (default: platform data dir)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-download even if a cached unfiltered file already exists",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=3,
        metavar="N",
        help="Minimum word length to include (default: 3)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=None,
        metavar="N",
        help="Maximum word length to include (default: no limit)",
    )
    parser.add_argument(
        "--no-numbers",
        action="store_true",
        help="Exclude words that are purely numeric",
    )
    parser.add_argument(
        "--password-mode",
        action="store_true",
        help="Generate near-human password candidates (case variants + number/year/symbol suffixes)",
    )
    parser.add_argument(
        "--popular",
        action="store_true",
        help=(
            "Download and merge all major language dumps: "
            + ", ".join(POPULAR_LANGUAGES)
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def resolve_languages(raw: list, links: list) -> list:
    """Expand comma-separated codes and validate against available links."""
    # Flatten comma-separated entries
    codes = []
    for item in raw:
        codes.extend(c.strip() for c in item.split(",") if c.strip())

    stripped_links = [l.strip("/").lower() for l in links]
    selected = []
    for code in codes:
        code_lower = code.lower()
        if code_lower in stripped_links:
            selected.append(code_lower)
        else:
            logging.warning("Language '%s' not found in available dumps — skipping.", code)
    return selected


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    working_dir = Path(args.output_dir) if args.output_dir else get_working_dir()
    working_dir.mkdir(parents=True, exist_ok=True)
    logging.debug("Output directory: %s", working_dir)

    url, links = get_wikipedia_dumps()
    if not links:
        return

    # ── Language selection ───────────────────────────────────────────────────
    if args.popular:
        logging.info("--popular selected: downloading %d major languages.", len(POPULAR_LANGUAGES))
        languages = resolve_languages(POPULAR_LANGUAGES, links)
        if not languages:
            logging.error("None of the popular languages found in available dumps.")
            return
    elif args.language:
        languages = resolve_languages(args.language, links)
        if not languages:
            logging.error("No valid languages selected. Run without --language to browse.")
            display_language_options(links)
            return
    else:
        display_language_options(links)
        languages = [fuzzy_select_language(links)]

    logging.info("Selected language(s): %s", ", ".join(languages))

    # ── Download + clean each language ──────────────────────────────────────
    merged_words: set = set()

    for lang in languages:
        lang_upper = lang.upper()
        file_path = working_dir / f"{lang_upper}-unfiltered.txt"
        dict_path = working_dir / f"{lang_upper}-wordlist.txt"

        if not download_titles(url, lang, file_path, force=args.force):
            logging.warning("Skipping %s due to download failure.", lang)
            continue

        words = clean_titles(
            file_path,
            min_length=args.min_length,
            max_length=args.max_length,
            no_numbers=args.no_numbers,
        )
        merged_words |= words

        # Per-language plain wordlist (always written)
        sorted_words = sorted(words)
        dict_path.write_text("\n".join(sorted_words), encoding="utf-8")
        logging.info("Wordlist saved: %s (%d words)", dict_path, len(sorted_words))

    if not merged_words:
        logging.error("No words extracted. Nothing to save.")
        return

    # ── Merged output (only when >1 language) ────────────────────────────────
    if len(languages) > 1:
        merged_path = working_dir / "MERGED-wordlist.txt"
        sorted_merged = sorted(merged_words)
        merged_path.write_text("\n".join(sorted_merged), encoding="utf-8")
        logging.info("Merged wordlist saved: %s (%d words)", merged_path, len(sorted_merged))

    # ── Password mode ────────────────────────────────────────────────────────
    final_words: list
    base_count: int = len(merged_words)

    if args.password_mode:
        final_words = generate_password_variants(merged_words)
        suffix = "MERGED" if len(languages) > 1 else languages[0].upper()
        pw_path = working_dir / f"{suffix}-passwords.txt"
        pw_path.write_text("\n".join(final_words), encoding="utf-8")
        logging.info("Password list saved: %s (%d candidates)", pw_path, len(final_words))
    else:
        final_words = sorted(merged_words)
        base_count = None  # suppress "base words" line in stats

    # ── Stats ────────────────────────────────────────────────────────────────
    print_stats(final_words, base_count=base_count if args.password_mode else None)
    print("\nProcess completed successfully.")


if __name__ == "__main__":
    main()
