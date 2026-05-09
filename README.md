# Wikipedia Wordlist Generator

A Python script to generate wordlists from Wikipedia static HTML dumps. This tool extracts article titles from Wikipedia dumps in various languages, cleans the text, and creates a dictionary file useful for penetration testing, password cracking, and linguistic analysis. Credits to ChrisAD for creating the original PowerShell version: https://github.com/ChrisAD/wiki-dictionary-creator.

## Features

- Fetches Wikipedia static HTML dumps automatically.
- Allows users to select a language from available Wikipedia dumps.
- Downloads and processes article titles into cleaned wordlists.
- Removes underscores, dashes, parentheses, and other unwanted characters.
- Splits concatenated words (e.g., `AbuSimbel,RamessesTemple,front,Egypt,Oct2004` → `AbuSimbel`, `RamessesTemple`, `front`, `Egypt`, `Oct2004`).
- Saves two output files:
  - `{LANGCODE}-unfiltered.txt`: The raw list of titles.
  - `{LANGCODE}-wordlist.txt`: The cleaned and formatted dictionary.
- Supports non-interactive use via `--language` flag for automation/scripting.
- Cross-platform: works on Windows, macOS, and Linux.

## Installation

No external dependencies — uses Python's standard library only. Requires Python 3.6+.

```sh
git clone https://github.com/whatsdd/wikipedia_wordlist_dictionary_creator.git
cd wikipedia_wordlist_dictionary_creator
```

## Usage

### Interactive mode

```sh
python3 Wikipedia-Wordlist-Generator.py
```

### Non-interactive (scripted) mode

```sh
python3 Wikipedia-Wordlist-Generator.py --language en
```

### Custom output directory

```sh
python3 Wikipedia-Wordlist-Generator.py --language no --output-dir /tmp/wordlists
```

### All options

```
usage: Wikipedia-Wordlist-Generator.py [-h] [--language LANGUAGE] [--output-dir OUTPUT_DIR]

options:
  --language    Language code to download (e.g. 'en', 'no'). Skips interactive prompt.
  --output-dir  Directory to save output files. Defaults to platform data dir.
```

## Output location (default)

| Platform | Path |
|----------|------|
| Linux    | `~/.local/share/wikipedia-dictionary-creator/` |
| macOS    | `~/.local/share/wikipedia-dictionary-creator/` |
| Windows  | `%LOCALAPPDATA%\wikipedia-dictionary-creator\` |
