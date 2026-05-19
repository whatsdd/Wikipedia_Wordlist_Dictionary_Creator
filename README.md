# Wikipedia Wordlist Generator

A Python script to generate wordlists and **near-human password candidates** from Wikipedia static HTML dumps. Extracts article titles from Wikipedia dumps in various languages, cleans the text, and produces dictionary files useful for penetration testing, password auditing, and linguistic analysis.

Credits to ChrisAD for the original PowerShell version: https://github.com/ChrisAD/wiki-dictionary-creator

---

## Features

- Fetches Wikipedia static HTML dumps automatically.
- **Fuzzy interactive language search** — type part of a language name to filter the list.
- Downloads and processes article titles into cleaned wordlists.
- **Progress bars** during download and processing (no external deps).
- **Password-mode** — expands each word into realistic human password candidates:
  - Case variants: `word`, `Word`, `WORD`
  - Number suffixes: `word1`, `word123`, `word1234`
  - Year suffixes: `Word2020` … `Word2026`
  - Symbol suffixes: `Word!`, `word123!`
- **Multi-language merge** — download several languages and combine into one deduplicated list.
- **`--popular`** — one flag to grab all 18 major language dumps at once.
- Word length filtering (`--min-length`, `--max-length`).
- Strip purely numeric words (`--no-numbers`).
- Removes Wikipedia filename hash artifacts (`_d69e`, `_b835f1`, …).
- **Wordlist statistics** printed after every run.
- **Verbose / debug logging** via `--verbose`.
- Force re-download with `--force`.
- Cross-platform output directory (Linux/macOS/Windows).
- **Web-crawling mode** (`--url` / `--url-file`) — crawl any website like [cewler](https://github.com/roys/cewler), no external deps.
- Emoji and Unicode symbol stripping from all output (always on).
- Graceful Ctrl+C — saves partial results instead of losing everything.
- Zero external dependencies — Python 3.6+ standard library only.

---

## Installation

```sh
git clone https://github.com/whatsdd/wikipedia_wordlist_dictionary_creator.git
cd wikipedia_wordlist_dictionary_creator
```

No packages to install.

---

## Usage

### Interactive mode (fuzzy language search)

```sh
python3 Wikipedia-Wordlist-Generator.py
```

After the language list appears, type a search term (e.g. `norsk` or `no`) or a number to select.

---

### Norwegian (Norsk) wordlist

The Norwegian Wikipedia dump is stored at:
```
https://dumps.wikimedia.org/other/static_html_dumps/current/no/html.lst
```

```sh
# Basic Norwegian wordlist
python3 Wikipedia-Wordlist-Generator.py --language no

# Norwegian with length filtering and no pure numbers
python3 Wikipedia-Wordlist-Generator.py --language no --min-length 5 --no-numbers

# Norwegian password candidates
python3 Wikipedia-Wordlist-Generator.py --language no --password-mode --min-length 5 --max-length 12
```

Output files saved to `~/.local/share/wikipedia-dictionary-creator/`:
- `NO-unfiltered.txt` — raw title paths from the dump
- `NO-wordlist.txt` — cleaned word list
- `NO-passwords.txt` — password candidates (with `--password-mode`)

---

### Swedish (Svenska) wordlist

The Swedish Wikipedia dump is stored at:
```
https://dumps.wikimedia.org/other/static_html_dumps/current/sv/html.lst
```

```sh
# Basic Swedish wordlist
python3 Wikipedia-Wordlist-Generator.py --language sv

# Swedish + English merged
python3 Wikipedia-Wordlist-Generator.py --language sv,en --min-length 4 --no-numbers
```

Output: `SV-wordlist.txt`, `EN-wordlist.txt`, and `MERGED-wordlist.txt`.

---

### Multi-language merge

```sh
# Merge Norwegian + Swedish + English into one deduplicated list
python3 Wikipedia-Wordlist-Generator.py --language no,sv,en --min-length 4 --no-numbers
```

When more than one language is specified, a `MERGED-wordlist.txt` (or `MERGED-passwords.txt` in password-mode) is created in addition to per-language files.

---

### All major languages at once (`--popular`)

Downloads and merges 18 major Wikipedia languages: `en de fr es it pt nl pl ru sv no da fi ja zh ar tr ko`

```sh
python3 Wikipedia-Wordlist-Generator.py --popular --min-length 5 --no-numbers

# With password variants
python3 Wikipedia-Wordlist-Generator.py --popular --password-mode --min-length 5 --max-length 12
```

> **Note:** `--popular --password-mode` can generate hundreds of millions of lines. Use `--max-length 12` to keep the output manageable.

---

### Web-crawling mode (`--url` / `--url-file`)

Crawl any website and extract a wordlist — inspired by [cewler](https://github.com/roys/cewler). No extra dependencies needed.

```sh
# Crawl a single site (depth 2, same domain only)
python3 Wikipedia-Wordlist-Generator.py --url https://example.com --depth 2 --scope exact

# Crawl and generate password candidates
python3 Wikipedia-Wordlist-Generator.py --url https://example.com --depth 3 --password-mode --min-length 5

# Crawl including child subdomains
python3 Wikipedia-Wordlist-Generator.py --url https://example.com --scope children --depth 2

# Crawl multiple URLs from a file (one URL per line, # for comments)
python3 Wikipedia-Wordlist-Generator.py --url-file targets.txt --depth 2 --scope exact
```

**targets.txt example:**
```
# Company sites
https://example.com
https://docs.example.com
# https://skipped.example.com
```

Output saved as `{domain}-wordlist.txt` (single URL) or `crawl-merged-wordlist.txt` (multiple URLs).

**Crawl options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--url URL` | — | Single start URL |
| `--url-file FILE` | — | File with one URL per line |
| `--depth N` | 2 | Max link-follow hops |
| `--rate N` | 5.0 | Requests per second |
| `--scope` | `exact` | `exact` same domain / `children` include subdomains / `all` parent+sister domains |
| `--user-agent STR` | Chrome UA | Custom User-Agent header |

---

### Force re-download / custom output dir

```sh
python3 Wikipedia-Wordlist-Generator.py --language no --force --output-dir /tmp/wordlists
```

---

## All options

```
usage: Wikipedia-Wordlist-Generator.py [-h] [--url URL | --url-file FILE]
                                       [--depth N] [--rate N]
                                       [--scope {exact,children,all}]
                                       [--user-agent STR]
                                       [--language CODE [CODE ...]]
                                       [--popular] [--force]
                                       [--output-dir DIR] [--min-length N]
                                       [--max-length N] [--no-numbers]
                                       [--password-mode] [--verbose]

web crawl mode:
  --url URL             Crawl this URL and extract a wordlist
  --url-file FILE       Text file with one URL per line; crawls all, merges results
  --depth N, -d N       Maximum crawl depth (default: 2)
  --rate N, -r N        Requests per second (default: 5.0)
  --scope               exact (default) | children | all
  --user-agent STR      Custom User-Agent

wikipedia dump mode:
  --language CODE       Language code(s): 'no', 'sv', 'en,no,de', or repeated flags
  --popular             Download all 18 major language dumps
  --force, -f           Re-download even if cached file exists

shared options:
  --output-dir DIR      Directory to save output files
  --min-length N        Minimum word length (default: 3)
  --max-length N        Maximum word length (default: no limit)
  --no-numbers          Exclude purely numeric words
  --password-mode       Generate near-human password candidates
  --verbose, -v         Enable debug logging
```

---

## Output location (default)

| Platform | Path |
|----------|------|
| Linux    | `~/.local/share/wikipedia-dictionary-creator/` |
| macOS    | `~/.local/share/wikipedia-dictionary-creator/` |
| Windows  | `%LOCALAPPDATA%\wikipedia-dictionary-creator\` |

---

## Output files

| File | Description |
|------|-------------|
| `{LANG}-unfiltered.txt` | Raw title paths downloaded from Wikipedia |
| `{LANG}-wordlist.txt` | Cleaned, deduplicated, sorted word list |
| `MERGED-wordlist.txt` | Union of all selected languages (multi-language runs) |
| `{LANG}-passwords.txt` | Password candidates (`--password-mode`) |
| `MERGED-passwords.txt` | Merged password candidates (multi-language + `--password-mode`) |

---

## Password-mode example output

Given the base word `London`, password-mode generates entries like:

```
london
London
LONDON
london1
london123
London2023
London2024
London!
london123!
```
