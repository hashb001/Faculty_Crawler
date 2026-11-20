#!/usr/bin/env python3
"""Public faculty-directory crawler. No AI service or API key required."""
import argparse
import csv
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urldefrag, urljoin, urlsplit, unquote
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup, Comment

__version__ = '1.1.0'
# Change this to your GitHub repository so site administrators can see what this tool is.
PROJECT_URL = 'https://github.com/hashb001/Faculty_Crawler'
AGENT = f'FacultyDirectoryCollector/{__version__} (+{PROJECT_URL})'
MIN_DELAY = 1.0  # seconds between requests; enforced so the tool stays polite to university servers
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
FACULTY = re.compile(r'\b(professor|lecturer|instructor|faculty|reader|research scientist|chair)\b', re.I)
STAFF = re.compile(r'\b(staff|administrative|administrator|coordinator|manager|secretary|receptionist|'
                   r'specialist|technician|advisor|adviser|accountant|assistant to)\b', re.I)
NON_NAME = re.compile(r'\b(professors?|lecturers?|instructors?|university|department|research|directory|faculty|staff|contact|admissions|computer|science|engineering|visit|website|program|studies|about|news|events|resources|graduate|undergraduate)\b', re.I)
# Trailing degrees such as ", Ph.D." or " Ph. D." after a name.
DEGREES = re.compile(r'(?:,?\s*\b(?:P\.?h\.?\s?D|Ed\.?\s?D|D\.\s?Sc|M\.\s?S|M\.\s?A|MBA|M\.\s?Eng)\b\.?)+\s*$')
# Cloudflare replaces published addresses with this placeholder for anti-harvesting.
PROTECTED = '.__cf_email__, a[href*="/cdn-cgi/l/email-protection"]'
FIELDS = ['name', 'email', 'title', 'research_areas', 'profile_url', 'source_url', 'status']


def clean(value):
    return ' '.join(value.split())


def person_name(value):
    value = clean(value)
    words = value.split()
    return (2 <= len(words) <= 7 and len(value) < 100 and not NON_NAME.search(value)
            and not any(c.isdigit() for c in value)
            and all(any(c.isalpha() for c in w) for w in words)
            and all(w[0].isupper() or w.lower() in {'de', 'van', 'von', 'al', 'bin', 'da', 'del'} for w in words))


def emails(node):
    values = set()
    for a in node.select('a[href]'):
        if a['href'].lower().startswith('mailto:'):
            values.update(EMAIL.findall(unquote(a['href'][7:].split('?')[0])))
    text = node.get_text(' ', strip=True)
    text = re.sub(r'\s*[\[(]at[\])]\s*', '@', text, flags=re.I)
    text = re.sub(r'\s*[\[(]dot[\])]\s*', '.', text, flags=re.I)
    values.update(EMAIL.findall(text))
    return sorted(values)


def title_of(node):
    explicit = node.select_one('.eng-profile-title, .directory-leader-title, [itemprop="jobTitle"], .job-title, .position, .person-title')
    if explicit:
        return clean(explicit.get_text(' ', strip=True))
    lines = [clean(p.get_text(' ', strip=True)) for p in node.select('p, .title')]
    for value in lines:
        if len(value) < 180 and FACULTY.search(value):
            return value
    # Recognise staff titles too, so they can be left out (unless --include-staff).
    for value in lines:
        if len(value) < 80 and STAFF.search(value):
            return value
    return ''


def candidates(soup, base, name_selector=None):
    root = soup.select_one('main, [role="main"]') or soup
    for bad in root.select('nav, header, footer, script, style, aside'):
        bad.decompose()
    nodes = root.select(name_selector) if name_selector else root.select('h1, h2, h3, h4, a[href], [itemprop="name"]')
    if not name_selector:
        nodes = [n for n in nodes if n.name != 'a' or n.find(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
                 or n.find_parent(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
                 or re.search(r'/(?:eng-directory|people|person|faculty|profile|staff)/', n.get('href', ''))]
    names = [(n, DEGREES.sub('', clean(n.get_text(' ', strip=True))).rstrip(' ,')) for n in nodes]
    names = [(n, name) for n, name in names if name_selector or person_name(name)]
    # Each name node's ancestors, looked up by id, so card boundaries are cheap to test on big pages.
    ancestors = {id(n): {id(n)} | {id(p) for p in n.parents} for n, _ in names}
    output, seen = [], set()
    for node, name in names:
        link = node if node.name == 'a' else node.find('a', href=True)
        if link is None:
            link = node.find_parent('a', href=True)
        profile = urljoin(base, link['href']) if link and link.get('href') else ''
        if profile and urlsplit(profile).scheme not in ('http', 'https'):
            profile = ''
        # The same person often appears twice (photo link and name link); two different people
        # who share a name have different profile pages, so keep both of them.
        if (name, profile) in seen or (name, '') in seen or (not profile and any(s[0] == name for s in seen)):
            continue
        seen.add((name, profile))
        card = node
        # Never cross a boundary containing a second person's name.
        for parent in node.parents:
            if parent.name in ('body', 'html', '[document]'):
                break
            other_names = {v for n, v in names if id(parent) in ancestors[id(n)]}
            if len(other_names) > 1:
                break
            card = parent
            if emails(card) or title_of(card):
                # Continue to capture email when the title is in an inner wrapper.
                if emails(card):
                    break
        found = emails(card)
        title = title_of(card)
        # A title paragraph that also holds the name (e.g. "<b>Name</b> <i>Chair</i>") repeats it.
        raw_name = clean(node.get_text(' ', strip=True))
        if title.startswith(raw_name) and title != raw_name:
            title = title[len(raw_name):].strip(' ,')
        # Ignore arbitrary name-like navigation links with no person evidence.
        if not found and not title and not (profile and re.search(r'/(?:eng-directory|people|person|faculty|profile|staff)/', profile)) and not name_selector:
            continue
        areas = [clean(x.get_text(' ', strip=True)) for x in card.select('ul[class*="research"] li')]
        status = 'found' if found else 'email not found'
        if not found and card.select_one(PROTECTED):
            status = 'email hidden by site protection; check page manually'
        output.append(dict(name=name, email='; '.join(found), title=title,
                           research_areas='; '.join(areas), profile_url=profile,
                           source_url=base, status=status))
    return output


def page_links(soup, base, seed):
    origin = urlsplit(seed).netloc
    seed_path = re.sub(r'/page/\d+/?$', '/', urlsplit(seed).path).rstrip('/')
    for a in soup.select('a[href]'):
        target = urldefrag(urljoin(base, a['href']))[0]
        target = re.sub(r'/page/1/?$', '/', target)
        parts = urlsplit(target)
        label = a.get_text(' ', strip=True).lower()
        classes = a.get('class', [])
        pagination = ('next' in a.get('rel', []) or 'page-numbers' in classes
                      or label in {'next', 'next page', '›', '»'} or label.isdigit())
        same_listing = parts.path.rstrip('/') == seed_path or parts.path.startswith(seed_path + '/page/')
        if pagination and same_listing and parts.netloc == origin and parts.scheme in ('http', 'https'):
            yield target


class Fetcher:
    def __init__(self, delay):
        self.delay, self.last, self.rules = delay, 0, {}

    def raw(self, url, delay):
        time.sleep(max(0, delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        with urlopen(Request(url, headers={'User-Agent': AGENT}), timeout=30) as response:
            data = response.read(5_000_001)
            if len(data) > 5_000_000:
                raise ValueError('Page exceeds 5 MB limit')
            return data.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')

    def get(self, url):
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.rules:
            robot = RobotFileParser(origin + '/robots.txt')
            try:
                robot.parse(self.raw(origin + '/robots.txt', self.delay).splitlines())
            except HTTPError as error:
                if error.code == 404:
                    robot.parse([])
                else:
                    raise RuntimeError(f'Cannot check robots.txt: HTTP {error.code}') from error
            self.rules[origin] = robot
        robot = self.rules[origin]
        if not robot.can_fetch(AGENT, url):
            raise RuntimeError('Disallowed by robots.txt')
        delay = max(self.delay, robot.crawl_delay(AGENT) or robot.crawl_delay('*') or 0)
        rate = robot.request_rate(AGENT) or robot.request_rate('*')
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        return self.raw(url, delay)


def local_file(value):
    """Return a Path when the input names a saved HTML file, else None."""
    value = value.strip().strip('\'"')  # dragging a file into the terminal adds quotes
    if value.lower().startswith('file://'):
        value = unquote(urlsplit(value).path)
        if re.match(r'^/[A-Za-z]:[/\\]', value):  # Windows: file:///C:/Users/... -> C:/Users/...
            value = value[1:]
    if urlsplit(value).scheme in ('http', 'https'):
        return None
    return Path(value).expanduser()


def saved_from(soup):
    """Find the page's original web address in a browser-saved copy, if recorded."""
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        match = re.search(r'saved from url=(?:\(\d+\))?(https?://\S+)', comment)
        if match:
            return match.group(1).rstrip(' ->')
    for tag, attr in (('link[rel="canonical"]', 'href'), ('meta[property="og:url"]', 'content')):
        node = soup.select_one(tag)
        if node and urlsplit(node.get(attr, '')).scheme in ('http', 'https'):
            return node[attr]
    return None


# Domain parts that say nothing about which university it is (gvsu.edu, ox.ac.uk, buet.ac.bd).
GENERIC_DOMAINS = {'edu', 'ac', 'com', 'org', 'net', 'gov', 'co', 'info', 'io',
                   'uk', 'us', 'ca', 'au', 'nz', 'in', 'bd', 'pk', 'de', 'fr', 'nl', 'jp',
                   'cn', 'kr', 'sg', 'my', 'hk', 'za', 'ie', 'it', 'es', 'se', 'ch', 'br'}


def university_name(url):
    """Short university name from a web address: www.gvsu.edu -> gvsu, cse.engin.umich.edu -> umich."""
    labels = [label for label in (urlsplit(url or '').hostname or '').lower().split('.') if label and label != 'www']
    while len(labels) > 1 and labels[-1] in GENERIC_DOMAINS:
        labels.pop()
    return re.sub(r'[^a-z0-9-]+', '_', labels[-1]) if labels else ''


def unused_path(path):
    """gvsu_professors.csv, or gvsu_professors_2.csv etc. if that already exists."""
    path = Path(path)
    number = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f'{path.stem}_{number}{path.suffix}')
        number += 1
    return candidate


def spreadsheet_safe(value):
    """Stop downloaded text being run as a formula when the CSV is opened in Excel or LibreOffice."""
    return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value


def add_record(records, row):
    key = row['profile_url'] or row['name'].casefold()
    if key not in records or (not records[key]['email'] and row['email']):
        records[key] = row
    return key


class UserError(Exception):
    """A problem to explain to the user in one line, without a Python traceback."""


def crawl(args):
    fetch = Fetcher(args.delay)
    queue, visited, records, failures = deque([] if args.local else [args.url]), set(), {}, []
    profile_jobs = []
    site = args.url
    if args.local:
        # A page saved from the browser: read it offline, with no network requests.
        print(f'Reading file {args.local}', file=sys.stderr)
        try:
            soup = BeautifulSoup(args.local.read_bytes(), 'html.parser')
        except OSError as error:
            raise UserError(f'Cannot read {args.local}: {error.strerror or error}')
        base = args.base_url or saved_from(soup)
        site = base
        for row in candidates(soup, base or args.local.resolve().as_uri(), args.name_selector):
            row['source_url'] = base or str(args.local)
            add_record(records, row)
    while queue and len(visited) < args.max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        print(f'Reading {url}', file=sys.stderr)
        try:
            soup = BeautifulSoup(fetch.get(url), 'html.parser')
            queue.extend(u for u in page_links(soup, url, args.url) if u not in visited and u not in queue)
            for row in candidates(soup, url, args.name_selector):
                key = add_record(records, row)
                # Profiles on a protected site hide the address the same way; skip the requests.
                if not row['email'] and row['profile_url'] and not row['status'].startswith('email hidden'):
                    profile_jobs.append(key)
        except Exception as error:
            failures.append(f'{url}: {error}')
    for key in dict.fromkeys(profile_jobs):
        row = records[key]
        url = row['profile_url']
        if row['email'] or url in visited:
            continue
        if urlsplit(url).netloc != urlsplit(args.url).netloc:
            row['status'] = 'review: profile on another host'
            continue
        if len(visited) >= args.max_pages:
            row['status'] = 'review: page limit reached'
            continue
        visited.add(url)
        print(f'Reading profile {url}', file=sys.stderr)
        try:
            soup = BeautifulSoup(fetch.get(url), 'html.parser')
            matches = [r for r in candidates(soup, url) if r['name'].casefold() == row['name'].casefold() and r['email']]
            if len(matches) == 1:
                match = matches[0]
                row.update(email=match['email'], source_url=url, status='found')
                row['title'] = row['title'] or match['title']
        except Exception as error:
            row['status'] = 'review: profile request failed'
            failures.append(f'{url}: {error}')
    rows = []
    for row in records.values():
        if not args.include_staff and row['title'] and not FACULTY.search(row['title']):
            continue
        if not row['title']:
            row['status'] += '; review faculty status'
        if '; ' in row['email']:
            row['status'] += '; review multiple emails'
        rows.append(row)
    rows.sort(key=lambda r: r['name'].casefold())
    if not args.output:
        name = university_name(site)
        if not name and args.local:  # saved file without a recorded address: use the file's name
            name = re.sub(r'[^a-z0-9-]+', '_', args.local.stem.lower()).strip('_')
        args.output = f'{name}_professors.csv' if name else 'professors.csv'
    if not args.overwrite:
        args.output = str(unused_path(args.output))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(args.output, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({k: spreadsheet_safe(v) for k, v in row.items()} for row in rows)
    except PermissionError:
        raise UserError(f'Cannot write {args.output}. If it is open in Excel or another program, '
                        'close it and run again, or choose another name with -o.')
    print(f'Saved {len(rows)} people ({sum(bool(r["email"]) for r in rows)} with emails) to {args.output}')
    if queue:
        failures.append('Page limit reached; some directory pages were not read.')
    hidden = sum(r['status'].startswith('email hidden') for r in rows)
    if hidden and args.local:
        failures.append(f'{hidden} emails are still hidden in this file. Re-save the page with Ctrl+S as '
                        '"Webpage, Complete" (not "HTML only") after it has fully loaded.')
    elif hidden:
        failures.append(f'{hidden} emails are hidden by the site\'s email protection and were left blank; '
                        'open the page in a browser and save it with Ctrl+S as "Webpage, Complete", '
                        'then run this tool on the saved .html file.')
    if not rows:
        failures.append('No people detected. This layout may require --name-selector or a site-specific adapter; JavaScript-only pages are unsupported.')
    for message in failures:
        print('WARNING: ' + message, file=sys.stderr)
    return 2 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?', help='Faculty directory URL, or a page saved from your browser '
                        '(.html file); prompts if omitted')
    parser.add_argument('-o', '--output', help='CSV file to write (default: named after the university, '
                        'e.g. gvsu_professors.csv)')
    parser.add_argument('--include-staff', action='store_true', help='Also keep non-faculty titles')
    parser.add_argument('--name-selector', help='Optional CSS selector for person names on unfamiliar layouts')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace the CSV if it exists (default: add _2, _3, ... to the name)')
    parser.add_argument('--max-pages', type=int, default=80)
    parser.add_argument('--delay', type=float, default=MIN_DELAY,
                        help=f'Seconds between requests (minimum {MIN_DELAY:g})')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--base-url', help='For a saved file: the page\'s original web address, used for '
                        'profile links (detected automatically when the browser recorded it)')
    args = parser.parse_args()
    if not args.url:
        try:
            args.url = input('Paste faculty directory URL or saved .html file path: ')
        except EOFError:
            parser.error('No URL or file given')
    args.url = args.url.strip()
    if not args.url:
        parser.error('No URL or file given')
    args.local = local_file(args.url)
    raw = args.url.strip('\'"')
    looks_like_path = raw.startswith(('/', '~', '.', 'file:', '\\')) or re.match(r'^[A-Za-z]:[/\\]', raw) \
        or raw.lower().endswith(('.html', '.htm'))
    if args.local is not None and not args.local.is_file() and not looks_like_path:
        parser.error('Enter a complete http:// or https:// URL, or the path of a saved .html file')
    if args.local is not None:
        if not args.local.is_file():
            parser.error(f'File not found: {args.local}\nUse the full path; you can drag the file '
                         'into the terminal to paste it.')
    elif not urlsplit(args.url).netloc:
        parser.error('Enter a complete http:// or https:// URL, or the path of a saved .html file')
    if args.base_url and urlsplit(args.base_url).scheme not in ('http', 'https'):
        parser.error('--base-url must be an http:// or https:// URL')
    if args.max_pages < 1:
        parser.error('--max-pages must be at least 1')
    if args.delay < MIN_DELAY:
        parser.error(f'--delay must be at least {MIN_DELAY:g} second, to avoid overloading university websites')
    try:
        return crawl(args)
    except UserError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nStopped.', file=sys.stderr)
        sys.exit(130)
