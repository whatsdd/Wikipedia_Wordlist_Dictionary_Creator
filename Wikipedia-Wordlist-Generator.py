import argparse
import logging
import os
import re
import sys
import time
import urllib.request
from collections import Counter, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
    """Fallback spinner for unknown-size operations."""

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


# ── Regex constants ────────────────────────────────────────────────────────────

_IP_RE = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
_HASH_RE = re.compile(r"_[0-9a-f]{4,}$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"[;,.!@#%&()]")
_DIGITS_ONLY_RE = re.compile(r"^\d+$")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002000-\U0000206F"
    "\U00002700-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


# ── Fetch available Wikipedia dumps ───────────────────────────────────────────

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

        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(stripped):
                return stripped[idx]
            print(f"  Please enter a number between 1 and {len(stripped)}.")
            continue

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


# ── Title cleaning (dump mode) ─────────────────────────────────────────────────

def _filter_word(word: str, min_length: int, max_length, no_numbers: bool):
    """Return cleaned word or None if it should be excluded."""
    word = _EMOJI_RE.sub("", word).strip()
    if not word:
        return None
    if no_numbers and _DIGITS_ONLY_RE.fullmatch(word):
        return None
    length = len(word)
    if length < min_length:
        return None
    if max_length is not None and length > max_length:
        return None
    return word


def clean_titles(
    file_path: Path,
    min_length: int = 3,
    max_length: int = None,
    no_numbers: bool = False,
) -> set:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        logging.error("File not found: %s", file_path)
        return set()

    total = len(lines)
    logging.info("Processing %d lines from %s ...", total, file_path.name)
    bar = ProgressBar(total, "  Cleaning  ")

    cleaned: set = set()
    for line in lines:
        bar.update()
        clean = line.strip()
        clean = clean.split("/")[-1].split(".")[0]
        if "~" in clean:
            clean = clean.split("~")[-1]
        clean = _HASH_RE.sub("", clean)
        clean = clean.replace("_", "").replace("-", "")
        clean = clean.replace("(", "").replace(")", "")
        if _IP_RE.match(clean):
            continue
        for word in _SPLIT_RE.split(clean):
            w = _filter_word(word, min_length, max_length, no_numbers)
            if w:
                cleaned.add(w)

    bar.close()
    logging.info("Extracted %d unique words.", len(cleaned))
    return cleaned


# ── Web-crawling mode ──────────────────────────────────────────────────────────

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HtmlWordExtractor(HTMLParser):
    """Extracts visible text and href links from HTML, skipping script/style."""

    _SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._text_parts: list = []
        self.links: list = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag.lower() == "a":
            for attr, val in attrs:
                if attr == "href" and val and not val.startswith(
                    ("#", "mailto:", "javascript:", "tel:")
                ):
                    self.links.append(val)

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._text_parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)


def extract_words_from_html(
    html: str,
    base_url: str,
    min_length: int = 3,
    max_length: int = None,
    no_numbers: bool = False,
):
    """Parse HTML, return (set_of_words, list_of_absolute_urls)."""
    parser = HtmlWordExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass  # tolerate malformed HTML

    # Resolve links to absolute URLs
    links = []
    for href in parser.links:
        try:
            absolute = urljoin(base_url, href).split("#")[0]
            if absolute.startswith(("http://", "https://")):
                links.append(absolute)
        except Exception:
            pass

    # Extract and filter words from visible text
    words: set = set()
    for chunk in parser.text.split():
        chunk = chunk.strip("'\".,!?;:-()")
        for word in _SPLIT_RE.split(chunk):
            w = _filter_word(word, min_length, max_length, no_numbers)
            if w:
                words.add(w)

    return words, links


def is_in_scope(url: str, start_url: str, scope: str) -> bool:
    """Check whether url falls within the crawl scope relative to start_url."""
    try:
        url_netloc = urlparse(url).netloc.lower()
        start_netloc = urlparse(start_url).netloc.lower()
    except Exception:
        return False

    if scope == "exact":
        return url_netloc == start_netloc
    if scope == "children":
        return url_netloc == start_netloc or url_netloc.endswith("." + start_netloc)
    # "all": share the same registered domain (last two labels)
    def _root(netloc):
        parts = netloc.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else netloc
    return _root(url_netloc) == _root(start_netloc)


def crawl_url(
    start_url: str,
    depth: int,
    rate: float,
    scope: str,
    user_agent: str,
    min_length: int,
    max_length,
    no_numbers: bool,
) -> set:
    """BFS-crawl start_url up to depth hops; return set of extracted words."""
    ua = user_agent or _DEFAULT_UA
    min_interval = 1.0 / rate if rate > 0 else 0.0

    queue: deque = deque([(start_url, 0)])
    visited: set = set()
    all_words: set = set()
    last_request_time = 0.0

    spinner = SpinnerBar(f"  Crawling {urlparse(start_url).netloc}")
    page_count = 0

    while queue:
        url, current_depth = queue.popleft()
        url = url.split("#")[0]
        if not url or url in visited:
            continue
        visited.add(url)

        elapsed = time.time() - last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        logging.debug("Crawling [depth=%d]: %s", current_depth, url)
        spinner.update()

        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=15) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    continue
                html = response.read(5 * 1024 * 1024).decode("utf-8", errors="replace")
            last_request_time = time.time()
            page_count += 1
        except OSError as e:
            logging.debug("Skipping %s: %s", url, e)
            continue

        words, links = extract_words_from_html(html, url, min_length, max_length, no_numbers)
        all_words |= words

        if current_depth < depth:
            for link in links:
                if link not in visited and is_in_scope(link, start_url, scope):
                    queue.append((link, current_depth + 1))

    spinner.close()
    logging.info(
        "Crawl complete: %d pages visited, %d unique words extracted.",
        page_count, len(all_words),
    )
    return all_words


# ── Password variant generation ────────────────────────────────────────────────

_YEARS = [str(y) for y in range(2015, 2027)]
_NUM_SUFFIXES = ["1", "12", "123", "1234", "12345"]
_SYM_SUFFIXES = ["!", "@", "#", "1!", "123!"]


def generate_password_variants(words: set) -> list:
    logging.info("Generating password variants for %d base words...", len(words))
    variants: set = set()

    bar = ProgressBar(len(words), "  Variants  ")
    for word in words:
        bar.update()
        lower = word.lower()
        title = word.capitalize()
        upper = word.upper()

        for form in (lower, title, upper):
            variants.add(form)
        for suf in _NUM_SUFFIXES:
            variants.add(lower + suf)
            variants.add(title + suf)
        for year in _YEARS:
            variants.add(title + year)
            variants.add(lower + year)
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

POPULAR_LANGUAGES = [
    "en", "de", "fr", "es", "it", "pt", "nl", "pl", "ru",
    "sv", "no", "da", "fi", "ja", "zh", "ar", "tr", "ko",
]


# ── Cross-platform working dir ─────────────────────────────────────────────────

def get_working_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "wikipedia-dictionary-creator"


# ── Output helpers ─────────────────────────────────────────────────────────────

def _save_and_report(
    words: set,
    working_dir: Path,
    label: str,
    password_mode: bool,
    args,
) -> None:
    """Shared final-step: optional password expansion, stats, write file."""
    if not words:
        logging.error("No words extracted. Nothing to save.")
        return

    base_count = len(words)

    if password_mode:
        final_words = generate_password_variants(words)
        pw_path = working_dir / f"{label}-passwords.txt"
        pw_path.write_text("\n".join(final_words), encoding="utf-8")
        logging.info("Password list saved: %s (%d candidates)", pw_path, len(final_words))
        print_stats(final_words, base_count=base_count)
    else:
        final_words = sorted(words)
        wl_path = working_dir / f"{label}-wordlist.txt"
        wl_path.write_text("\n".join(final_words), encoding="utf-8")
        logging.info("Wordlist saved: %s (%d words)", wl_path, len(final_words))
        print_stats(final_words)

    print("\nProcess completed successfully.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate wordlists / password lists from Wikipedia dumps "
            "or by crawling any website."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # interactive Wikipedia dump mode (fuzzy language search)
  %(prog)s

  # Norwegian Wikipedia wordlist with filters
  %(prog)s --language no --min-length 5 --no-numbers --verbose

  # Swedish + English merged dump
  %(prog)s --language sv,en --min-length 4 --no-numbers

  # human-like password candidates from English + Norwegian
  %(prog)s --language en,no --password-mode --min-length 5 --max-length 12

  # all 18 major language dumps at once
  %(prog)s --popular --password-mode --min-length 5

  # crawl a single website (like cewler)
  %(prog)s --url https://example.com --depth 2 --scope exact

  # crawl with password-mode output
  %(prog)s --url https://example.com --depth 3 --password-mode --min-length 5

  # crawl multiple URLs from a file (one URL per line)
  %(prog)s --url-file targets.txt --depth 2 --scope exact

  # force re-download to a custom directory
  %(prog)s --language en --force --output-dir /tmp/wordlists
""",
    )

    # ── Crawl mode ──────────────────────────────────────────────
    crawl_group = parser.add_argument_group("web crawl mode")
    url_mx = crawl_group.add_mutually_exclusive_group()
    url_mx.add_argument(
        "--url",
        metavar="URL",
        help="Crawl this URL and extract a wordlist",
    )
    url_mx.add_argument(
        "--url-file",
        metavar="FILE",
        help="Text file with one URL per line; crawls all and merges results",
    )
    crawl_group.add_argument(
        "--depth", "-d",
        type=int,
        default=2,
        metavar="N",
        help="Maximum crawl depth from start URL (default: 2)",
    )
    crawl_group.add_argument(
        "--rate", "-r",
        type=float,
        default=5.0,
        metavar="N",
        help="Maximum requests per second (default: 5.0)",
    )
    crawl_group.add_argument(
        "--scope", "-s",
        choices=["exact", "children", "all"],
        default="exact",
        help="Domain crawl scope: exact (default), children, all",
    )
    crawl_group.add_argument(
        "--user-agent",
        metavar="STR",
        default=None,
        help="Custom User-Agent string for crawl requests",
    )

    # ── Wikipedia dump mode ──────────────────────────────────────
    dump_group = parser.add_argument_group("wikipedia dump mode")
    dump_group.add_argument(
        "--language", "-l",
        nargs="+",
        metavar="CODE",
        help="Language code(s), e.g. 'en' or 'en,no,de' or 'en' 'no'",
    )
    dump_group.add_argument(
        "--popular",
        action="store_true",
        help="Download all 18 major language dumps: " + ", ".join(POPULAR_LANGUAGES),
    )
    dump_group.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-download even if a cached unfiltered file already exists",
    )

    # ── Shared options ───────────────────────────────────────────
    shared_group = parser.add_argument_group("shared options")
    shared_group.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Directory to save output files (default: platform data dir)",
    )
    shared_group.add_argument(
        "--min-length",
        type=int,
        default=3,
        metavar="N",
        help="Minimum word length to include (default: 3)",
    )
    shared_group.add_argument(
        "--max-length",
        type=int,
        default=None,
        metavar="N",
        help="Maximum word length to include (default: no limit)",
    )
    shared_group.add_argument(
        "--no-numbers",
        action="store_true",
        help="Exclude words that are purely numeric",
    )
    shared_group.add_argument(
        "--password-mode",
        action="store_true",
        help="Generate near-human password candidates (case + number/year/symbol suffixes)",
    )
    shared_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def resolve_languages(raw: list, links: list) -> list:
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


def _load_url_file(path: str) -> list:
    """Read URLs from a file, one per line. Skip blank lines and # comments."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logging.error("Cannot read URL file %s: %s", path, e)
        return []
    urls = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    logging.info("Loaded %d URL(s) from %s", len(urls), path)
    return urls


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    working_dir = Path(args.output_dir) if args.output_dir else get_working_dir()
    working_dir.mkdir(parents=True, exist_ok=True)
    logging.debug("Output directory: %s", working_dir)

    # ── Crawl mode ───────────────────────────────────────────────
    if args.url or args.url_file:
        urls = [args.url] if args.url else _load_url_file(args.url_file)
        if not urls:
            logging.error("No URLs to crawl.")
            return

        merged_words: set = set()
        try:
            for url in urls:
                logging.info("Starting crawl: %s (depth=%d, scope=%s)", url, args.depth, args.scope)
                merged_words |= crawl_url(
                    start_url=url,
                    depth=args.depth,
                    rate=args.rate,
                    scope=args.scope,
                    user_agent=args.user_agent,
                    min_length=args.min_length,
                    max_length=args.max_length,
                    no_numbers=args.no_numbers,
                )
        except KeyboardInterrupt:
            logging.warning(
                "Interrupted — saving partial results (%d words collected)...",
                len(merged_words),
            )

        if len(urls) == 1:
            label = urlparse(urls[0]).netloc.replace(":", "_") or "crawl"
        else:
            label = "crawl-merged"

        _save_and_report(merged_words, working_dir, label, args.password_mode, args)
        return

    # ── Wikipedia dump mode ──────────────────────────────────────
    url, links = get_wikipedia_dumps()
    if not links:
        return

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

    merged_words = set()
    try:
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

            sorted_words = sorted(words)
            dict_path.write_text("\n".join(sorted_words), encoding="utf-8")
            logging.info("Wordlist saved: %s (%d words)", dict_path, len(sorted_words))

    except KeyboardInterrupt:
        logging.warning(
            "Interrupted — saving partial results (%d words collected)...",
            len(merged_words),
        )

    if len(languages) > 1 and merged_words:
        merged_path = working_dir / "MERGED-wordlist.txt"
        sorted_merged = sorted(merged_words)
        merged_path.write_text("\n".join(sorted_merged), encoding="utf-8")
        logging.info("Merged wordlist saved: %s (%d words)", merged_path, len(sorted_merged))

    label = "MERGED" if len(languages) > 1 else languages[0].upper()
    _save_and_report(merged_words, working_dir, label, args.password_mode, args)


if __name__ == "__main__":
    main()
