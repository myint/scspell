############################################################################
# scspell
# Copyright (C) 2009 Paul Pelzl
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
############################################################################


"""
scspell -- an interactive, conservative spell-checker for source code.
"""


from __future__ import with_statement
import contextlib, os, re, sys, shelve, shutil
from bisect import bisect_left
import ConfigParser

import portable
from corpus import SetCorpus, DictStoredSetCorpus, FileStoredCorpus, PrefixMatchingCorpus


VERSION = '0.9.0'
CONTEXT_SIZE  = 4       # Size of context printed upon request
LEN_THRESHOLD = 3       # Subtokens shorter than 4 characters are likely to be abbreviations
CTRL_C = '\x03'         # Special key codes returned from getch()
CTRL_D = '\x04'
CTRL_Z = '\x1a'

USER_DATA_DIR        = portable.get_data_dir('scspell')
KEYWORDS_DEFAULT_LOC = os.path.join(USER_DATA_DIR, 'keywords.txt')
SCSPELL_DATA_DIR     = os.path.normpath(os.path.join(os.path.dirname(__file__), 'data'))
SCSPELL_CONF         = os.path.join(USER_DATA_DIR, 'scspell.conf')


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


class MatchDescriptor(object):
    """A MatchDescriptor captures the information necessary to represent a token
    matched within some source code.
    """

    def __init__(self, text, matchobj):
        self._data     = text
        self._pos      = matchobj.start()
        self._token    = matchobj.group()
        self._context  = None
        self._line_num = None

    def get_token(self):
        return self._token

    def get_string(self):
        """Gets the entire string in which the match was found."""
        return self._data

    def get_ofs(self):
        """Gets the offset within the string where the match is located."""
        return self._pos

    def get_prefix(self):
        """Gets the string preceding this match."""
        return self._data[:self._pos]

    def get_remainder(self):
        """Gets the string consisting of this match and all remaining characters."""
        return self._data[self._pos:]

    def get_context(self):
        """Computes the lines of context associated with this match, as a sequence of
        (line_num, line_string) values.
        """
        if self._context is not None:
            return self._context

        lines = self._data.split('\n')

        # Compute the byte offset of start of every line
        offsets = []
        for i in xrange(len(lines)):
            if i == 0:
                offsets.append(0)
            else:
                offsets.append(offsets[i-1] + len(lines[i-1]) + 1)

        # Compute the line number where the match is located
        for (i, ofs) in enumerate(offsets):
            if ofs > self._pos:
                self._line_num = i
                break
        if self._line_num is None:
            self._line_num = len(lines)

        # Compute the set of lines surrounding this line number
        self._context = [(i+1, line.strip('\r\n')) for (i, line) in enumerate(lines) if 
                (i+1 - self._line_num) in range(-CONTEXT_SIZE/2, CONTEXT_SIZE/2 + 1)]
        return self._context

    def get_line_num(self):
        """Computes the line number of the match."""
        if self._line_num is None:
            self.get_context()
        return self._line_num


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
    

def _handle_add(failed_subtokens, dicts):
    """Handles addition of one or more subtokens to a dictionary."""
    for subtoken in failed_subtokens:
        while True:
            print ("""\
   Subtoken '%s':
      (i)gnore, add to (c)ustom dictionary, add to per-(f)ile custom
      dictionary, or add to (k)eyword dictionary: [i]""") % subtoken
            ch = portable.getch()
            if ch in (CTRL_C, CTRL_D, CTRL_Z):
                print 'User abort.'
                sys.exit(1)
            elif ch in ('i', '\r', '\n'):
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


def _handle_failed_check(match_desc, filename, failed_subtokens, dicts):
    """Handles a spellchecker match failure.

    Returns: (text, ofs), where <text> is the (possibly modified) source text and
             <ofs> is the byte offset within the text where searching should resume.
    """
    token = match_desc.get_token()
    print "%s:%u: Unmatched '%s' --> {%s}" % (filename, match_desc.get_line_num(), token, 
                ', '.join([st for st in failed_subtokens]))
    match_regex = re.compile(re.escape(match_desc.get_token()))
    while True:
        print """\
   (i)gnore, (I)gnore all, (r)eplace, (R)eplace all, (a)dd to dictionary, or show (c)ontext? [i]"""
        ch = portable.getch()
        if ch in (CTRL_C, CTRL_D, CTRL_Z):
            print 'User abort.'
            sys.exit(1)
        elif ch in ('i', '\r', '\n'):
            break
        elif ch == 'I':
            dicts.ignores.add(token.lower())
            break
        elif ch == 'r':
            replacement = raw_input('      Replacement text: ')
            if replacement == '':
                print '      (Not replaced.)'
                break
            dicts.ignores.add(replacement.lower())
            tail = re.sub(match_regex, replacement, match_desc.get_remainder(), 1)
            return (match_desc.get_prefix() + tail, match_desc.get_ofs() + len(replacement))
        elif ch == 'R':
            replacement = raw_input('      Replacement text: ')
            if replacement == '':
                print '      (Not replaced.)'
                break
            dicts.ignores.add(replacement.lower())
            tail = re.sub(match_regex, replacement, match_desc.get_remainder())
            return (match_desc.get_prefix() + tail, match_desc.get_ofs() + len(replacement))
        elif ch == 'a':
            _handle_add(failed_subtokens, dicts)
            break
        elif ch == 'c':
            for ctx in match_desc.get_context():
                print '%4u: %s' % ctx
            print
    print
    # Default: text is unchanged
    return (match_desc.get_string(), match_desc.get_ofs() + len(match_desc.get_token()))


def _handle_token(match_desc, filename, dicts):
    """Handles a matched token described by <match_desc>.  <filename> is the
    current filename, and <dicts> is the set of dictionaries against which
    we will search.

    Returns: (text, ofs), where <text> is the (possibly modified) source text and
             <ofs> is the byte offset within the text where searching should resume.
    """
    token = match_desc.get_token()
    if (not dicts.ignores.match(token.lower())) and (_hex_regex.match(token) is None):
        subtokens = _decompose_token(token)
        failed_subtokens = [st for st in subtokens if len(st) > LEN_THRESHOLD
                                                   and (not dicts.english.match(st))
                                                   and (not dicts.keyword.match(st))
                                                   and (not dicts.custom.match(st))
                                                   and (not dicts.per_file.match(st))
                                                   and (not dicts.ignores.match(st))]
        if failed_subtokens != []:
            failed_subtokens = _make_unique(failed_subtokens)
            return _handle_failed_check(match_desc, filename, failed_subtokens, dicts)
    return (match_desc.get_string(), match_desc.get_ofs() + len(token))


def _spell_check_file(source_filename, db, dicts):
    """Runs the spellchecker on a single <source_filename>, using <dicts> as
    the set of dictionaries.  <db> is the user's persistent storage class.
    """

    fq_filename = os.path.normcase(os.path.realpath(source_filename))
    with open(fq_filename, 'rb') as source_file:
        try:
            source_text = source_file.read()
        except IOError, e:
            print str(e)
            return

    # Look up the per-file dictionary
    with DictStoredSetCorpus(db, fq_filename) as per_file_dict:
        dicts.per_file = per_file_dict

        data = source_text
        pos  = 0
        while True:
            m = _token_regex.search(data, pos)
            if m is None:
                break
            (data, pos) = _handle_token(MatchDescriptor(data, m), source_filename, dicts)

    # Write out the source file if it was modified
    if data != source_text:
        with open(fq_filename, 'wb') as source_file:
            try:
                source_file.write(data)
            except IOError, e:
                print str(e)
                return
            

def verify_user_data_dir():
    """Verifies that the user data directory is present, or creates one
    from scratch.
    """
    if not os.path.exists(USER_DATA_DIR):
        print 'Creating new personal dictionaries in %s .\n' % USER_DATA_DIR
        os.makedirs(USER_DATA_DIR)
        shutil.copyfile(os.path.join(SCSPELL_DATA_DIR, 'keywords.txt'), KEYWORDS_DEFAULT_LOC)



def locate_keyword_dict():
    """Loads the location of the keyword dictionary.  This is either
    the default location, or an override specified in 'scspell.conf'.
    """
    verify_user_data_dir()
    try:
        f = open(SCSPELL_CONF, 'r')
    except IOError:
        return KEYWORDS_DEFAULT_LOC

    config = ConfigParser.RawConfigParser()
    try:
        config.readfp(f)
    except ConfigParser.ParsingError, e:
        print str(e)
        sys.exit(1)
    finally:
        f.close()

    try:
        loc = config.get('Locations', 'keyword_dictionary')
        if os.path.isabs(loc):
            return loc
        else:
            print ('Error while parsing "%s": keyword_dictionary must be an absolute path.' %
                    SCSPELL_CONF)
            sys.exit(1)
    except ConfigParser.Error:
        return KEYWORDS_DEFAULT_LOC


def set_keyword_dict(filename):
    """Sets the location of the keyword dictionary to the specified filename."""
    if not os.path.isabs(filename):
        print 'Error: keyword dictionary location must be an absolute path.'
        sys.exit(1)

    verify_user_data_dir()
    config = ConfigParser.RawConfigParser()
    try:
        config.read(SCSPELL_CONF)
    except ConfigParser.ParsingError, e:
        print str(e)
        sys.exit(1)

    try:
        config.add_section('Locations')
    except ConfigParser.DuplicateSectionError:
        pass
    config.set('Locations', 'keyword_dictionary', filename)

    with open(SCSPELL_CONF, 'w') as f:
        config.write(f)


def export_keyword_dict(filename):
    """Exports the current keyword dictionary to the specified file."""
    shutil.copyfile(locate_keyword_dict(), filename)

    
def spell_check(source_filenames):
    """Runs the interactive spellchecker on the set of <source_filenames>.

    Returns: N/A
    """
    ENGLISH_LOC  = os.path.join(SCSPELL_DATA_DIR, 'english-words.txt')
    KEYWORDS_LOC = locate_keyword_dict()

    verify_user_data_dir()
    db = shelve.open(os.path.join(USER_DATA_DIR, 'custom.shelf'))
    try:
        with contextlib.nested(
                PrefixMatchingCorpus(ENGLISH_LOC),
                FileStoredCorpus(KEYWORDS_LOC),
                DictStoredSetCorpus(db, '__custom')) as (english_dict, keyword_dict, custom_dict):
            dicts = Bunch()
            dicts.english = english_dict
            dicts.keyword = keyword_dict
            dicts.custom  = custom_dict
            dicts.ignores = SetCorpus()

            for f in source_filenames:
                _spell_check_file(f, db, dicts)
    finally:
        db.close()


