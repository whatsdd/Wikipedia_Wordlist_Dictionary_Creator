import argparse
import os
import re
import sys
import urllib.request
import time
from pathlib import Path
from urllib.parse import urljoin


def get_wikipedia_dumps(retries=3, delay=5):
    url = "https://dumps.wikimedia.org/other/static_html_dumps/current/"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                html = response.read().decode("utf-8")
            links = re.findall(r'href="(.*?)"', html)
            links = [link for link in links if link != "../"]
            return url, links
        except OSError as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    print("Failed to retrieve Wikipedia dumps after multiple attempts.")
    return url, []


def display_language_options(links):
    if not links:
        print("No Wikipedia language dumps available.")
        return
    print("Available Wikipedia language dumps:")
    for i, link in enumerate(links, 1):
        print(f"{i}. {link}")


def download_titles(url, language, save_path, retries=3, delay=5):
    language_url = urljoin(url, f"{language}/html.lst")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(language_url, timeout=10) as response:
                content = response.read().decode("utf-8")
            with open(save_path, "w", encoding="utf-8") as file:
                file.write(content)
            print(f"Downloaded {language_url} to {save_path}")
            return True
        except OSError as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    print(f"Failed to fetch {language_url} after multiple attempts.")
    return False


def clean_titles(file_path, output_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return

    cleaned_titles = set()
    ip_regex = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
    split_chars = re.compile(r"[;,.!@#%&()]")

    for line in lines:
        clean = line.strip()
        clean = clean.split("/")[-1].split(".")[0]
        if "~" in clean:
            clean = clean.split("~")[-1]

        clean = clean.replace("_", "").replace("-", "")
        clean = clean.replace("(", "").replace(")", "")

        if not ip_regex.match(clean):
            words = split_chars.split(clean)
            for word in words:
                cleaned_titles.add(word.strip())

    cleaned_titles = sorted(filter(None, cleaned_titles))

    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(cleaned_titles))

    print(f"Cleaned dictionary saved to {output_path}")


def get_working_dir():
    # Use a cross-platform user data directory
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "wikipedia-dictionary-creator"


def select_language_interactive(links):
    while True:
        try:
            choice = int(input("Enter the number of the language to download: ")) - 1
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue
        if 0 <= choice < len(links):
            return links[choice].strip("/")
        print(f"Please enter a number between 1 and {len(links)}.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate wordlists from Wikipedia static HTML dumps."
    )
    parser.add_argument(
        "--language",
        help="Language code to download (e.g. 'en', 'no'). Skips interactive prompt.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save output files. Defaults to platform data dir.",
    )
    args = parser.parse_args()

    working_dir = Path(args.output_dir) if args.output_dir else get_working_dir()
    working_dir.mkdir(parents=True, exist_ok=True)

    url, links = get_wikipedia_dumps()
    if not links:
        return

    if args.language:
        # Normalise: strip slashes, lowercase to match link format
        lang = args.language.strip("/").lower()
        matches = [l.strip("/") for l in links if l.strip("/").lower() == lang]
        if not matches:
            print(f"Language '{args.language}' not found in available dumps.")
            display_language_options(links)
            return
        selected_language = matches[0]
    else:
        display_language_options(links)
        selected_language = select_language_interactive(links)

    lang_code = selected_language.upper()
    file_path = working_dir / f"{lang_code}-unfiltered.txt"
    dict_path = working_dir / f"{lang_code}-wordlist.txt"

    if not file_path.exists():
        if not download_titles(url, selected_language, file_path):
            return
    else:
        print(f"File {file_path} already exists. Reusing it.")

    clean_titles(file_path, dict_path)
    print("Process completed successfully.")


if __name__ == "__main__":
    main()
