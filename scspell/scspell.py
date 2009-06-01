#!/usr/bin/env python
"""
scspell -- an interactive, conservative spell-checker for source code.
"""

from __future__ import with_statement
import contextlib, os, re, sys, shelve, shutil
from bisect import bisect_left

import portable
from corpus import SetCorpus, DictStoredSetCorpus, FileStoredCorpus, PrefixMatchingCorpus


CONTEXT_SIZE  = 4       # Size of context printed upon request
LEN_THRESHOLD = 3       # Subtokens shorter than 4 characters are likely to be abbreviations
CTRL_C = '\x03'         # Special key codes returned from getch()
CTRL_D = '\x04'
CTRL_Z = '\x1a'

USER_DATA_DIR    = portable.get_data_dir('scspell')
SCSPELL_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), 'data'))

# Treat anything alphanumeric as a token of interest
_token_regex = re.compile(r'\w+')

# Hex digits will be treated as a special case, because they can look like
# word-like even though they are actually numeric
_hex_regex = re.compile(r'0x[0-9a-fA-F]+')

# We assume that tokens will be split using either underscores,
# digits, or camelCase conventions (or both)
_us_regex         = re.compile(r'[_\d]+')
_camel_word_regex = re.compile(r'([A-Z][a-z]*)')


# Used as a generic struct
class Bunch:
    pass


def _clamp(value, low_limit, high_limit):
    return min(max(value, low_limit), high_limit)


def _make_unique(items):
    """Removes duplicate items from a list, while preserving list order."""
    seen = set()
    def first_occurrence(i):
        if i not in seen:
            seen.add(i)
            return True
        return False
    return [i for i in items if first_occurrence(i)]


def _decompose_token(token):
    """Divides a token into a list of strings of letters.  Tokens are divided by
    underscores and digits, and capital letters will begin new subtokens.

    Returns: list of subtoken strings
    """
    us_parts    = _us_regex.split(token)
    if ''.join(us_parts).isupper():
        # This looks like a CONSTANT_DEFINE_OF_SOME_SORT
        subtokens = us_parts
    else:
        camelcase_parts = [_camel_word_regex.split(us_part) for us_part in us_parts]
        subtokens = sum(camelcase_parts, [])
    # This use of split() will create many empty strings
    return [st.lower() for st in subtokens if st != '']
    

def _handle_add(rejected_subtokens, dicts):
    """Handles addition of one or more subtokens to a dictionary."""
    for subtoken in rejected_subtokens:
        while True:
            print ("""\
   Subtoken '%s':
      (N)ext subtoken, add to (C)ustom dictionary, add to per-(F)ile custom
      dictionary, or add to (K)eyword dictionary? [N]""") % subtoken
            ch = portable.getch().lower()
            if ch in (CTRL_C, CTRL_D, CTRL_Z):
                print 'User abort.'
                sys.exit(1)
            elif ch in ('n', '\r', '\n'):
                break
            elif ch == 'c':
                dicts.custom.add(subtoken)
                break
            elif ch == 'f':
                dicts.per_file.add(subtoken)
                break
            elif ch == 'k':
                dicts.keyword.add(subtoken)
                break


def _handle_failed_check(token, filename, line_num, context, rejected_subtokens, dicts):
    """Handles a spellchecker match failure."""
    print "%s:%u: Unmatched '%s' --> {%s}" % \
        (filename, (line_num + 1), token, ', '.join([st for st in rejected_subtokens]))
    while True:
        print '   (N)ext token, (I)gnore all, (A)dd to dictionary, or show (C)ontext? [N]'
        ch = portable.getch().lower()
        if ch in (CTRL_C, CTRL_D, CTRL_Z):
            print 'User abort.'
            sys.exit(1)
        elif ch in ('n', '\r', '\n'):
            break
        elif ch == 'i':
            dicts.ignores.add(token.lower())
            break
        elif ch == 'a':
            _handle_add(rejected_subtokens, dicts)
            break
        elif ch == 'c':
            for ln, ctx in context:
                print '%4u: %s' % (ln, ctx.strip('\r\n'))
            print
    print


def _spell_check_line(filename, line_num, line, context, dicts):
    """Runs the spellchecker for a single <line> of text.  The line is at offset
    <line_num>, and is surrounded by the given set of <context>.  The dictionaries
    enumerated in <dicts> shall be searched.

    Returns: N/A.  <modified> shall be updated to reflect the various dictionaries
                   that have been mutated.
    """
    for token in _token_regex.findall(line):
        # Exclude hex as a special case
        if dicts.ignores.match(token.lower()) or (_hex_regex.match(token) is not None):
            continue
        subtokens = _decompose_token(token)
        rejected_subtokens = [st for st in subtokens if len(st) > LEN_THRESHOLD
                                                     and (not dicts.english.match(st))
                                                     and (not dicts.keyword.match(st))
                                                     and (not dicts.custom.match(st))
                                                     and (not dicts.per_file.match(st))
                                                     and (not dicts.ignores.match(st))]
        if rejected_subtokens != []:
            # remove duplicate subtokens
            rejected_subtokens = _make_unique(rejected_subtokens)
            _handle_failed_check(token, filename, line_num, context, rejected_subtokens, dicts)
                        

def _spell_check_file(source_filename, db, dicts):
    """Runs the spellchecker on a single <source_filename>, using <dicts> as
    the set of dictionaries.  <db> is the user's persistent storage class.
    """

    fq_filename = os.path.normcase(os.path.realpath(source_filename))
    try:
        source_file = open(fq_filename, 'r')
        lines = source_file.readlines()
    except IOError, e:
        print str(e)
        return

    # Look up the per-file dictionary
    with DictStoredSetCorpus(db, fq_filename) as per_file_dict:
        dicts.per_file = per_file_dict
        for line_num, line in enumerate(lines):
            context_min = _clamp(line_num - CONTEXT_SIZE/2, 0, len(lines) - 1)
            context_max = _clamp(line_num + CONTEXT_SIZE/2, 0, len(lines) - 1)
            context = [(i, lines[i]) for i in range(context_min, context_max+1)]
            _spell_check_line(source_filename, line_num, line, context, dicts)


def spell_check(source_filenames):
    """Runs the interactive spellchecker on the set of <source_filenames>.

    Returns: N/A
    """
    ENGLISH_LOC  = os.path.join(SCSPELL_DATA_DIR, 'english-words.txt')
    KEYWORDS_LOC = os.path.join(USER_DATA_DIR,    'keywords.txt')
    if not os.path.exists(USER_DATA_DIR):
        print 'Creating new personal dictionaries in %s .' % USER_DATA_DIR
        os.makedirs(USER_DATA_DIR)
        shutil.copyfile(os.path.join(SCSPELL_DATA_DIR, 'keywords.txt'), KEYWORDS_LOC)
    db = shelve.open(os.path.join(USER_DATA_DIR, 'custom.shelf'))
    try:
        with contextlib.nested(
                PrefixMatchingCorpus(ENGLISH_LOC),
                FileStoredCorpus(KEYWORDS_LOC),
                DictStoredSetCorpus(db, '__custom')) as (english_dict, keyword_dict, custom_dict):
            dicts = Bunch()
            dicts.english    = english_dict
            dicts.keyword = keyword_dict
            dicts.custom  = custom_dict
            dicts.ignores = SetCorpus()

            for f in source_filenames:
                _spell_check_file(f, db, dicts)
    finally:
        db.close()


