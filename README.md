# Faculty Directory Crawler

Paste a university faculty directory link and get a spreadsheet (CSV) of the professors listed there: name, title, public email, profile link and source page. Handy for finding faculty to contact about research positions or graduate school.

It runs on your own computer. No account, API key or AI service is needed; only Python and an internet connection.

```
$ crawl https://eng.ua.edu/departments/computer-science/
Reading https://eng.ua.edu/departments/computer-science/
Reading https://eng.ua.edu/departments/computer-science/page/2/
...
Saved 40 people (40 with emails) to ua_professors.csv
```

## Setup

You need **Python 3.10 or newer**.

### Windows

1. Install Python from <https://www.python.org/downloads/>. On the installer's first screen, tick **"Add python.exe to PATH"**.
2. Download this project (green **Code** button → **Download ZIP**) and extract it somewhere permanent, for example `Documents\faculty_crawler`.
3. Double-click **`setup.bat`**. It creates a Python environment, installs the one required package, and offers to add a `crawl` command. Answer **Y**.

If you move the folder later, run `setup.bat` again from the new location.

### Linux and Mac

```sh
cd faculty_crawler
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

On Ubuntu/Debian, install `python3-venv` first if the second command fails: `sudo apt install python3-venv`.

Optional: add a `crawl` command that works from any folder. Add this to `~/.bashrc` (or `~/.zshrc` on Mac), with your own path, then open a new terminal:

```sh
crawl() {
    (cd "$HOME/faculty_crawler" && .venv/bin/python faculty_crawler.py "$@")
}
```

## Usage

| | Command |
|---|---|
| With the `crawl` command | `crawl` |
| Windows, without it | double-click `crawl.bat` |
| Linux / Mac, without it | `.venv/bin/python faculty_crawler.py` |

Paste the faculty directory link when asked, or give it directly:

```sh
crawl "https://www.example.edu/cs/faculty/"
```

Results are saved in the project folder, named after the university's web address: `www.gvsu.edu` gives `gvsu_professors.csv`. Existing files are never replaced; a second run saves `gvsu_professors_2.csv`. Open the CSV in Excel, LibreOffice or Google Sheets.

### Options

| Option | What it does |
|---|---|
| `-o name.csv` | Choose the output file name |
| `--overwrite` | Replace the output file if it already exists |
| `--include-staff` | Also keep people whose titles are not faculty (administrative staff, advisors, ...) |
| `--name-selector ".card .name"` | CSS selector for names, for layouts the tool does not detect |
| `--max-pages 150` | Maximum pages to read, including profile pages (default 80) |
| `--delay 2` | Seconds between requests (minimum 1) |
| `--base-url URL` | For a saved page: its original address, if the tool cannot find it |
| `--version` | Show the version |

### When emails are hidden, or the site blocks the tool

Some sites show email addresses to visitors but hide them from programs, or block automated requests entirely. The tool tells you when this happens. You can then:

1. Open the directory page in your browser and wait until it has fully loaded.
2. Press **Ctrl+S** (Cmd+S on Mac) and choose **"Webpage, Complete"**. "HTML only" keeps the emails hidden.
3. Give the saved file to the tool instead of a link, or drag it into the terminal when asked:

```sh
crawl "/home/you/Downloads/Faculty.html"
```

A saved page is read offline. The tool doesn't follow "next page" links or profile pages, so save each directory page separately.

## What's in the CSV

| Column | Contents |
|---|---|
| `name` | Name, with degrees such as ", Ph.D." removed |
| `email` | Public email, if shown on the directory or profile page |
| `title` | Job title, such as "Associate Professor" |
| `research_areas` | Research areas, when the site lists them in a recognised format |
| `profile_url` | The person's profile page |
| `source_url` | The page the information came from |
| `status` | `found`, or a note saying what to check: email not found, email hidden, faculty status unclear, multiple emails |

People whose title includes professor, lecturer, instructor, faculty, reader, research scientist or chair are kept. Recognised staff titles are left out unless you use `--include-staff`. People with no detectable title are kept and marked for review.

## Limitations

This is **not a universal scraper**. Every university builds its pages differently. The tool uses general rules that work on many directory layouts, but not all of them.

- Check the results against the website the first time you use it on a new site.
- Lists that only appear through JavaScript, "load more" buttons, emails shown as images, and unusual pagination are not supported.
- Name detection works best for names written in Latin script and capitalised normally.
- Tested on the University of Alabama Computer Science directory (four pages) and Grand Valley State University Computer Science.

If it doesn't work on a directory, please open an issue with the link.

## Responsible use

- **Use it to find people to contact individually.** For example, about research or graduate study. Don't use it for bulk or automated email. Professors receive many messages, and university mail filters block mass mail.
- **The tool is polite to websites.** It follows each site's `robots.txt`, waits at least one second between requests, identifies itself, and does not get around logins, CAPTCHAs, bot protection or hidden emails.
- **Respect a site's terms of use.** If a site doesn't allow automated access, don't use the tool on it.
- **Look after the data.** The CSV contains people's names and contact details. Don't publish or share these lists. Some places, such as the EU under GDPR, have rules on collecting and storing personal data.

The tool only collects information that is publicly listed and never guesses or invents email addresses.

## Running the tests

```sh
.venv/bin/python -m unittest discover tests        # Linux / Mac
.venv\Scripts\python -m unittest discover tests    # Windows
```

The tests use made-up pages and need no internet connection.

## License

MIT. See [LICENSE](LICENSE).
