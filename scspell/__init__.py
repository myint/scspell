#
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
#

"""scspell -- an interactive, conservative spell-checker for source code."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import sys
import shutil

try:
    import ConfigParser
except ImportError:
    # Python 3
    import configparser as ConfigParser

from . import _portable
from ._corpus import CorporaFile
from . import _util

from ._util import set_verbosity
from ._util import VERBOSITY_NORMAL
from ._util import VERBOSITY_MAX


assert set_verbosity
assert VERBOSITY_NORMAL is not None
assert VERBOSITY_MAX is not None


try:
    raw_input
except NameError:
    raw_input = input


__version__ = '1.3'

# Name of scspell.conf section header
CONFIG_SECTION = 'Settings'

# Size of context printed upon request
CONTEXT_SIZE = 4

# Subtokens shorter than 4 characters are likely to be abbreviations
LEN_THRESHOLD = 3

# Special key codes returned from getch()
CTRL_C = '\x03'
CTRL_D = '\x04'
CTRL_Z = '\x1a'

USER_DATA_DIR = _portable.get_data_dir('scspell')
DICT_DEFAULT_LOC = os.path.join(USER_DATA_DIR, 'dictionary.txt')
SCSPELL_DATA_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(
            __file__),
        'data'))
SCSPELL_CONF = os.path.join(USER_DATA_DIR, 'scspell.conf')

# Treat anything alphanumeric as a token of interest, as long as it is not
# immediately preceded by a single backslash.  (The string "\ntext" should
# match on "text" rather than "ntext".)
C_ESCAPE_TOKEN_REGEX = re.compile(r'(?<![^\\]\\)\w+')

# \ is not a character escape in e.g. LaTeX
TOKEN_REGEX = re.compile(r'\w+')

# Hex digits will be treated as a special case, because they can look like
# word-like even though they are actually numeric
HEX_REGEX = re.compile(r'0x[0-9a-fA-F]+')

# We assume that tokens will be split using either underscores,
# digits, or camelCase conventions (or both)
US_REGEX = re.compile(r'[_\d]+')
CAMEL_WORD_REGEX = re.compile(r'([A-Z][a-z]*)')

# File-id specifiers take this form
FILE_ID_REGEX = re.compile(r'scspell-id:[ \t]*([a-zA-Z0-9_\-]+)')


class MatchDescriptor(object):

    """A MatchDescriptor captures the information necessary to represent a
    token matched within some source code."""

    def __init__(self, text, matchobj):
        self._data = text
        self._pos = matchobj.start()
        self._token = matchobj.group()
        self._context = None
        self._line_num = None

    def get_token(self):
        return self._token

    def get_string(self):
        """Get the entire string in which the match was found."""
        return self._data

    def get_ofs(self):
        """Get the offset within the string where the match is located."""
        return self._pos

    def get_prefix(self):
        """Get the string preceding this match."""
        return self._data[:self._pos]

    def get_remainder(self):
        """Get the string consisting of this match and all remaining
        characters."""
        return self._data[self._pos:]

    def get_context(self):
        """Compute the lines of context associated with this match, as a
        sequence of (line_num, line_string) pairs."""
        if self._context is not None:
            return self._context

        lines = self._data.split('\n')

        # Compute the byte offset of start of every line
        offsets = []
        for i in range(len(lines)):
            if i == 0:
                offsets.append(0)
            else:
                offsets.append(offsets[i - 1] + len(lines[i - 1]) + 1)

        # Compute the line number where the match is located
        for (i, ofs) in enumerate(offsets):
            if ofs > self._pos:
                self._line_num = i
                break
        if self._line_num is None:
            self._line_num = len(lines)

        # Compute the set of lines surrounding this line number
        self._context = [
            (i + 1, line.strip('\r\n'))for (i, line) in enumerate(lines)
            if (i + 1 - self._line_num) in
            range(-CONTEXT_SIZE // 2, CONTEXT_SIZE // 2 + 1)]
        return self._context

    def get_line_num(self):
        """Computes the line number of the match."""
        if self._line_num is None:
            self.get_context()
        return self._line_num


def make_unique(items):
    """Remove duplicate items from a list, while preserving list order."""
    seen = set()

    def first_occurrence(i):
        if i not in seen:
            seen.add(i)
            return True
        return False
    return [i for i in items if first_occurrence(i)]


def decompose_token(token):
    """Divide a token into a list of strings of letters.

    Tokens are divided by underscores and digits, and capital letters will
    begin new subtokens.

    :param token: string to be divided
    :returns: sequence of subtoken strings

    """
    us_parts = US_REGEX.split(token)
    if ''.join(us_parts).isupper():
        # This looks like a CONSTANT_DEFINE_OF_SOME_SORT
        subtokens = us_parts
    else:
        camelcase_parts = [
            CAMEL_WORD_REGEX.split(
                us_part) for us_part in us_parts]
        subtokens = sum(camelcase_parts, [])
    # This use of split() will create many empty strings
    return [st.lower() for st in subtokens if st != '']


def handle_new_filetype(extension, dicts):
    """Handle creation of a new file-type for the given extension.

    :returns: True if created, False if canceled.

    """
    while True:
        descr = raw_input("""\
            Enter a descriptive name for the programming language: """).strip()
        if descr == '':
            print("""\
            (Canceled.)\n""")
            return False

        if (':' in descr) or (';' in descr):
            print("""\
            Illegal characters in descriptive name.""")
            continue

        if descr in dicts.get_filetypes():
            print("""\
            That name is already in use.""")
            continue

        dicts.new_filetype(descr, [extension])
        return True


def handle_new_extension(ext, dicts):
    """Handle creation of a new file-type extension.

    :returns: True if new extension was registered, False if canceled.

    """
    print(("""\
            Extension "%s" is not registered.  With which programming language
            should "%s" be associated?""" % (ext, ext)))

    type_format = """\
               %3u: %s"""
    filetypes = dicts.get_filetypes()
    for i, ft in enumerate(filetypes):
        print(type_format % (i, ft))
    print(type_format % (len(filetypes), '(Create new language file-type)'))

    while True:
        selection = raw_input("""\
            Enter number of desired file-type: """)
        if selection == '':
            print("""\
            (Canceled.)\n""")
            return False

        try:
            selection = int(selection)
        except ValueError:
            continue
        if selection == len(filetypes):
            return handle_new_filetype(ext, dicts)
        elif selection >= 0 and selection < len(filetypes):
            dicts.register_extension(ext, filetypes[selection])
            return True


def handle_add(unmatched_subtokens, filename, file_id, dicts):
    """Handle addition of one or more subtokens to a dictionary.

    :param unmatched_subtokens: sequence of subtokens, each of which failed
           spell check
    :param filename: name of file containing the token
    :param file_id: unique identifier for current file
    :type  file_id: string or None
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :returns: True if subtokens were handled, False if canceled

    """
    (_, ext) = os.path.splitext(filename.lower())

    if file_id is None:
        if ext != '':
            prompt = """\
      Subtoken '%s':
         (b)ack, (i)gnore, add to (p)rogramming language dictionary, or add to
         (n)atural language dictionary? [i]"""
        else:
            prompt = """\
      Subtoken '%s':
         (b)ack, (i)gnore or add to (n)atural language dictionary? [i]"""
    else:
        if ext != '':
            prompt = """\
      Subtoken '%s':
         (b)ack, (i)gnore, add to (p)rogramming language dictionary, add to
         (f)ile-specific dictionary, or add to (n)atural language
         dictionary? [i]"""
        else:
            prompt = """\
      Subtoken '%s':
         (b)ack, (i)gnore, add to (f)ile-specific dictionary, or add to
         (n)atural language dictionary? [i]"""

    for subtoken in unmatched_subtokens:
        while True:
            print(prompt % subtoken)
            ch = _portable.getch()
            if ch in (CTRL_C, CTRL_D, CTRL_Z):
                print('User abort.')
                sys.exit(1)
            elif ch == 'b':
                print("""\
         (Canceled.)\n""")
                return False
            elif ch in ('i', '\r', '\n'):
                break
            elif ext != '' and ch == 'p':
                if dicts.add_by_extension(subtoken, ext):
                    break
                else:
                    if handle_new_extension(ext, dicts) and \
                            dicts.add_by_extension(subtoken, ext):
                        break
            elif ch == 'n':
                dicts.add_natural(subtoken)
                break
            elif (file_id is not None) and (ch == 'f'):
                dicts.add_by_fileid(subtoken, file_id)
                break
    return True


def handle_failed_check_interactively(
        match_desc, filename, file_id, unmatched_subtokens, dicts, ignores):
    """Handle a token which failed the spell check operation.

    :param match_desc: description of the token matching instance
    :type  match_desc: MatchDescriptor
    :param filename: name of file containing the token
    :param file_id: unique identifier for current file
    :type  file_id: string or None
    :param unmatched_subtokens: sequence of subtokens, each of which failed
                                spell check
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :param ignores: set of tokens to ignore for this session
    :returns: (text, ofs) where ``text`` is the (possibly modified) source
              contents and ``ofs`` is the byte offset within the text where
              searching shall resume.

    """
    token = match_desc.get_token()
    print("%s:%u: Unmatched '%s' --> {%s}" %
          (filename, match_desc.get_line_num(), token,
           ', '.join([st for st in unmatched_subtokens])))
    MATCH_REGEX = re.compile(re.escape(match_desc.get_token()))
    while True:
        print("""\
   (i)gnore, (I)gnore all, (r)eplace, (R)eplace all, (a)dd to dictionary, or
   show (c)ontext? [i]""")
        ch = _portable.getch()
        if ch in (CTRL_C, CTRL_D, CTRL_Z):
            print('User abort.')
            sys.exit(1)
        elif ch in ('i', '\r', '\n'):
            break
        elif ch == 'I':
            ignores.add(token.lower())
            break
        elif ch in ('r', 'R'):
            replacement = raw_input("""\
      Replacement text for '%s': """ % token)
            if replacement == '':
                print("""\
      (Canceled.)\n""")
            else:
                ignores.add(replacement.lower())
                tail = re.sub(
                    MATCH_REGEX, replacement, match_desc.get_remainder(),
                    1 if ch == 'r' else 0)
                print()
                return (match_desc.get_prefix() + tail,
                        match_desc.get_ofs() + len(replacement))
        elif ch == 'a':
            if handle_add(unmatched_subtokens, filename, file_id, dicts):
                break
        elif ch == 'c':
            for ctx in match_desc.get_context():
                print('%4u: %s' % ctx)
            print()
    print()
    # Default: text is unchanged
    return (match_desc.get_string(),
            match_desc.get_ofs() + len(match_desc.get_token()))


def report_failed_check(match_desc, filename, unmatched_subtokens):
    """Handle a token which failed the spell check operation.

    :param match_desc: description of the token matching instance
    :type  match_desc: MatchDescriptor
    :param filename: name of file containing the token
    :param unmatched_subtokens: sequence of subtokens, each of which failed
                                spell check
    :returns: (text, ofs) where ``text`` is the (possibly modified) source
              contents and ``ofs`` is the byte offset within the text where
              searching shall resume.

    """
    token = match_desc.get_token()
    if len(unmatched_subtokens) == 1:
        print(
            "%s:%u: '%s' not found in dictionary (from token '%s')" %
            (filename, match_desc.get_line_num(), unmatched_subtokens[0],
             token),
            file=sys.stderr)
    else:
        unmatched_subtokens = ', '.join(
            "'%s'" %
            t for t in unmatched_subtokens)
        print(
            "%s:%u: %s were not found in the dictionary (from token '%s'" %
            (filename,
             match_desc.get_line_num(),
             unmatched_subtokens,
             token),
            file=sys.stderr)
    # Default: text is unchanged
    return (match_desc.get_string(),
            match_desc.get_ofs() + len(match_desc.get_token()))


def spell_check_token(
        match_desc, filename, file_id, dicts, ignores, report_only):
    """Spell check a single token.

    :param match_desc: description of the token matching instance
    :type  match_desc: MatchDescriptor
    :param filename: name of file containing the token
    :param file_id: unique identifier for this file
    :type  file_id: string or None
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :param ignores: set of tokens to ignore for this session
    :returns: ((text, ofs), error_found) where ``text`` is the (possibly
    modified) source contents and ``ofs`` is the byte offset within the text
    where searching shall resume.

    """
    token = match_desc.get_token()
    if (token.lower() not in ignores) and (HEX_REGEX.match(token) is None):
        subtokens = decompose_token(token)
        unmatched_subtokens = [
            st for st in subtokens if len(st) > LEN_THRESHOLD and
            (not dicts.match(st, filename, file_id)) and
            (st not in ignores)]
        if unmatched_subtokens:
            unmatched_subtokens = make_unique(unmatched_subtokens)
            if report_only:
                return (report_failed_check(match_desc, filename,
                                            unmatched_subtokens),
                        True)
            else:
                return (
                    handle_failed_check_interactively(
                        match_desc, filename, file_id, unmatched_subtokens,
                        dicts, ignores),
                    True)
    return (
        (match_desc.get_string(), match_desc.get_ofs() + len(token)),
        False)


def spell_check_file(filename, dicts, ignores, report_only, c_escapes):
    """Spell check a single file.

    :param filename: name of the file to check
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :param ignores: set of tokens to ignore for this session

    """
    fq_filename = os.path.normcase(os.path.realpath(filename))
    try:
        with _util.open_with_encoding(fq_filename) as source_file:
            source_text = source_file.read()
    except IOError as e:
        print("Error: can't read source file '{}'; "
              'skipping (reason: {})'.format(filename, e),
              file=sys.stderr)
        return False

    # Look for a file ID
    file_id = None
    m_id = FILE_ID_REGEX.search(source_text)
    if m_id is not None:
        file_id = m_id.group(1)
        _util.mutter(
            _util.VERBOSITY_DEBUG,
            '(File contains id "%s".)' %
            file_id)

    if c_escapes:
        token_regex = C_ESCAPE_TOKEN_REGEX
    else:
        token_regex = TOKEN_REGEX

    # Search for tokens to spell-check
    data = source_text
    pos = 0
    okay = True
    while True:
        m = token_regex.search(data, pos)
        if m is None:
            break
        if (m_id is not None and
                m.start() >= m_id.start() and
                m.start() < m_id.end()):
            # This is matching the file-id.  Skip over it.
            pos = m_id.end()
            continue
        result = spell_check_token(MatchDescriptor(
            data, m), filename, file_id, dicts, ignores, report_only)
        (data, pos) = result[0]
        error_found = result[1]
        if error_found:
            okay = False

    # Write out the source file if it was modified
    if data != source_text:
        with _util.open_with_encoding(fq_filename, mode='w') as source_file:
            try:
                source_file.write(data)
            except IOError as e:
                print(str(e), file=sys.stderr)
                return False

    return okay


def verify_user_data_dir():
    """Verify that the user data directory is present, or create one from
    scratch."""
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
        shutil.copyfile(
            os.path.join(
                SCSPELL_DATA_DIR,
                'dictionary.txt'),
            DICT_DEFAULT_LOC)


def locate_dictionary():
    """Load the location of the dictionary file.

    This is either the default location, or an override specified in
    'scspell.conf'.

    """
    verify_user_data_dir()
    try:
        f = _util.open_with_encoding(SCSPELL_CONF, encoding='utf-8')
    except IOError:
        return DICT_DEFAULT_LOC

    config = ConfigParser.RawConfigParser()
    try:
        config.readfp(f)
    except ConfigParser.ParsingError as e:
        print(str(e))
        sys.exit(1)
    finally:
        f.close()

    try:
        loc = config.get(CONFIG_SECTION, 'dictionary')
        if os.path.isabs(loc):
            return loc
        else:
            print('Error while parsing "%s": dictionary must be an absolute '
                  'path.' % SCSPELL_CONF)
            sys.exit(1)
    except ConfigParser.Error:
        return DICT_DEFAULT_LOC


def set_dictionary(filename):
    """Set the location of the dictionary to the specified filename.

    :returns: None

    """
    filename = os.path.realpath(
        os.path.expandvars(
            os.path.expanduser(
                filename)))

    verify_user_data_dir()
    config = ConfigParser.RawConfigParser()
    try:
        config.read(SCSPELL_CONF)
    except ConfigParser.ParsingError as e:
        print(str(e))
        sys.exit(1)

    try:
        config.add_section(CONFIG_SECTION)
    except ConfigParser.DuplicateSectionError:
        pass
    config.set(CONFIG_SECTION, 'dictionary', filename)

    with _util.open_with_encoding(SCSPELL_CONF, encoding='utf-8',
                                  mode='w') as f:
        config.write(f)


def export_dictionary(filename):
    """Export the current keyword dictionary to the specified file.

    :returns: None

    """
    shutil.copyfile(locate_dictionary(), filename)


def spell_check(source_filenames, override_dictionary=None, report_only=False,
                c_escapes=True):
    """Run the interactive spell checker on the set of source_filenames.

    If override_dictionary is provided, it shall be used as a dictionary
    filename for this session only.

    :returns: None

    """
    verify_user_data_dir()

    dict_file = locate_dictionary(
    ) if override_dictionary is None else override_dictionary

    dict_file = os.path.expandvars(os.path.expanduser(dict_file))
    okay = True
    with CorporaFile(dict_file) as dicts:
        ignores = set()
        for f in source_filenames:
            if not spell_check_file(f, dicts, ignores, report_only, c_escapes):
                okay = False
    return okay
