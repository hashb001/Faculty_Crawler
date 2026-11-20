"""Tests for faculty_crawler.py. Run from the project folder:

    .venv/bin/python -m unittest discover tests        (Linux/Mac)
    .venv\\Scripts\\python -m unittest discover tests   (Windows)

All pages here are made up; no network access is needed.
"""
import csv
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'faculty_crawler.py'
spec = importlib.util.spec_from_file_location('fc', SCRIPT)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

BASE = 'https://www.example.edu/cs/faculty'


def card(name, title, email=None, href=None, protected=False):
    link = f'<a href="{href}"><strong>{name}</strong></a>' if href else f'<strong>{name}</strong>'
    if protected:
        mail = ('<p><a href="/cdn-cgi/l/email-protection#abc"><span class="__cf_email__" '
                'data-cfemail="abc">[email&#160;protected]</span></a></p>')
    elif email:
        mail = f'<p><a href="mailto:{email}">{email}</a></p>'
    else:
        mail = ''
    return f'<div class="person"><p>{link}</p><p>{title}</p>{mail}</div>'


def page(*cards, heading='Associate Professors', extra=''):
    return (f'<html><head><link rel="canonical" href="{BASE}"></head><body>'
            f'<nav><a href="/people/x"><strong>Jane Navlink</strong></a></nav>'
            f'<main><h3>{heading}</h3><div class="grid">{"".join(cards)}</div>{extra}</main>'
            f'<footer>Contact Us</footer></body></html>')


def people(html):
    return fc.candidates(BeautifulSoup(html, 'html.parser'), BASE)


class Detection(unittest.TestCase):
    def test_bold_profile_links_are_people_and_headings_are_not(self):
        rows = people(page(card('Ada Lovelace, Ph.D.', 'Professor', 'ada@example.edu', '/cs/lovelace-ada-1'),
                           card('Alan Turing Ph. D.', 'Assistant Professor', 'alan@example.edu', '/cs/turing-alan-2')))
        self.assertEqual([r['name'] for r in rows], ['Ada Lovelace', 'Alan Turing'])
        self.assertEqual([r['email'] for r in rows], ['ada@example.edu', 'alan@example.edu'])
        self.assertEqual(rows[0]['title'], 'Professor')
        self.assertEqual(rows[0]['profile_url'], 'https://www.example.edu/cs/lovelace-ada-1')

    def test_navigation_is_ignored(self):
        names = [r['name'] for r in people(page(card('Ada Lovelace', 'Professor', 'ada@example.edu', '/a')))]
        self.assertNotIn('Jane Navlink', names)
        self.assertNotIn('Associate Professors', names)

    def test_degree_variants_removed(self):
        for raw in ['Grace Hopper, Ph.D.', 'Grace Hopper Ph.D.', 'Grace Hopper, P.h.D.', 'Grace Hopper, Ph.D., M.S.']:
            self.assertEqual(fc.DEGREES.sub('', raw).rstrip(' ,'), 'Grace Hopper', raw)
        self.assertEqual(fc.DEGREES.sub('', 'Yi Ma'), 'Yi Ma')  # a real surname, not a degree

    def test_same_person_twice_is_one_row(self):
        twice = ('<div class="person"><a href="/cs/hopper-grace"><img alt=""><strong>Grace Hopper</strong></a>'
                 '<p><a href="/cs/hopper-grace"><strong>Grace Hopper</strong></a></p><p>Professor</p></div>')
        self.assertEqual(len(people(page(twice))), 1)

    def test_two_people_with_the_same_name_are_both_kept(self):
        rows = people(page(card('Wei Zhang', 'Professor', 'wzhang1@example.edu', '/cs/zhang-wei-1'),
                           card('Wei Zhang', 'Lecturer', 'wzhang2@example.edu', '/cs/zhang-wei-2')))
        self.assertEqual(sorted(r['email'] for r in rows), ['wzhang1@example.edu', 'wzhang2@example.edu'])

    def test_hidden_email_is_reported(self):
        rows = people(page(card('Ada Lovelace', 'Professor', href='/cs/a', protected=True)))
        self.assertEqual(rows[0]['email'], '')
        self.assertTrue(rows[0]['status'].startswith('email hidden'))

    def test_name_repeated_in_title_is_trimmed(self):
        chair = ('<div><p><a href="/cs/babbage-charles"><strong>Charles Babbage Ph.D.</strong></a><br>'
                 '<i>Interim Chair, Department of Computer Science</i></p></div>')
        rows = people(page(chair))
        self.assertEqual(rows[0]['title'], 'Interim Chair, Department of Computer Science')


class Helpers(unittest.TestCase):
    def test_university_name(self):
        cases = {'https://www.gvsu.edu/x': 'gvsu', 'https://cse.engin.umich.edu/': 'umich',
                 'https://www.cs.ox.ac.uk/': 'ox', 'https://cse.buet.ac.bd/': 'buet', '': ''}
        for url, expected in cases.items():
            self.assertEqual(fc.university_name(url), expected, url)

    def test_spreadsheet_safe(self):
        self.assertEqual(fc.spreadsheet_safe('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        self.assertEqual(fc.spreadsheet_safe('\t=1+1'), "'\t=1+1")
        self.assertEqual(fc.spreadsheet_safe('Ada Lovelace'), 'Ada Lovelace')

    def test_unused_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp, 'gvsu_professors.csv')
            self.assertEqual(fc.unused_path(first), first)
            first.write_text('x')
            self.assertEqual(fc.unused_path(first).name, 'gvsu_professors_2.csv')
            Path(tmp, 'gvsu_professors_2.csv').write_text('x')
            self.assertEqual(fc.unused_path(first).name, 'gvsu_professors_3.csv')

    def test_windows_and_dragged_paths(self):
        self.assertIsNone(fc.local_file('https://www.example.edu/'))
        self.assertEqual(str(fc.local_file("'/home/me/My Page.html'")), '/home/me/My Page.html')
        self.assertEqual(fc.local_file('file:///C:/Users/me/page.html').as_posix(), 'C:/Users/me/page.html')


class CommandLine(unittest.TestCase):
    """Runs the script the way a user would, on a saved page, with no network access."""

    def run_tool(self, *args, stdin=''):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                              text=True, cwd=self.tmp, timeout=60)

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.saved = self.tmp / 'saved page.html'
        self.saved.write_text(page(card('Ada Lovelace', 'Professor', 'ada@example.edu', '/cs/a'),
                                   card('Alan Turing', 'Lecturer', href='/cs/t', protected=True),
                                   card('Office Person', 'Administrative Staff', 'office@example.edu', '/cs/o')),
                              encoding='utf-8')

    def tearDown(self):
        self._dir.cleanup()

    def read(self, name):
        with open(self.tmp / name, encoding='utf-8-sig') as handle:
            return list(csv.DictReader(handle))

    def test_saved_file_named_after_university_and_never_overwritten(self):
        first = self.run_tool(str(self.saved))
        self.assertIn('Saved 2 people (1 with emails) to example_professors.csv', first.stdout)
        self.assertIn('still hidden in this file', first.stderr)
        rows = self.read('example_professors.csv')
        self.assertEqual([r['name'] for r in rows], ['Ada Lovelace', 'Alan Turing'])  # staff left out
        self.assertEqual(rows[0]['source_url'], BASE)
        second = self.run_tool(str(self.saved))
        self.assertIn('to example_professors_2.csv', second.stdout)
        third = self.run_tool(str(self.saved), '--overwrite')
        self.assertIn('to example_professors.csv', third.stdout)

    def test_include_staff(self):
        self.run_tool(str(self.saved), '-o', 'all.csv', '--include-staff')
        self.assertIn('Office Person', [r['name'] for r in self.read('all.csv')])

    def test_path_typed_at_prompt_with_quotes(self):
        result = self.run_tool(stdin=f'"{self.saved}"\n')
        self.assertIn('Saved 2 people', result.stdout)

    def test_friendly_errors(self):
        cases = [((), 'No URL or file given'),                       # prompt closed with no input
                 (('www.example.edu/x',), 'Enter a complete http'),
                 ((str(self.tmp / 'missing.html'),), 'File not found'),
                 (('https://www.example.edu/', '--delay', '0'), 'at least 1 second')]
        for args, message in cases:
            result = self.run_tool(*args)
            self.assertNotEqual(result.returncode, 0, args)
            self.assertIn(message, result.stderr, args)
            self.assertNotIn('Traceback', result.stderr, args)

    def test_version(self):
        self.assertIn(fc.__version__, self.run_tool('--version').stdout)


if __name__ == '__main__':
    unittest.main()
