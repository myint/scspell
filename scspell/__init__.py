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

import argparse
import os
import re
import sys
import shutil
import uuid

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


__version__ = '2.1'

# Name of scspell.conf section header
CONFIG_SECTION = 'Settings'

# Size of context printed upon request
CONTEXT_SIZE = 4

# Subtokens shorter than 4 characters are likely to be abbreviations
LEN_THRESHOLD = 3

USER_DATA_DIR = _portable.get_data_dir('scspell')
DICT_DEFAULT_LOC = os.path.join(USER_DATA_DIR, 'dictionary.txt')
SCSPELL_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), 'data'))
SCSPELL_BUILTIN_DICT = os.path.join(SCSPELL_DATA_DIR, 'dictionary.txt')

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

    def __init__(self, text, match_obj):
        self._data = text
        self._pos = match_obj.start()
        self._token = match_obj.group()
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


def get_new_file_id():
    """Produce a new file ID string."""
    return str(uuid.uuid1())


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


def build_add_prompt(offer_p, offer_f, offer_N):
    """Build a prompt for adding a word to a dictionary.

    :param offer_p: offer a (p)rogramming language dictionary
    :type offer_p: bool
    :param offer_f: offer a (f)ile-specific dictionary
    :type offer_f: bool
    :param offer_N: offer to create a (N)ew file-specific dictionary
    :type offer_p: bool
    :returns: prompt string

    """

    prompt = """\
      Subtoken '%s':
         (b)ack, (i)gnore, add to (n)atural language dictionary"""
    if offer_p:
        prompt += """, add to
         (p)rogramming language dictionary"""
    if offer_f:
        prompt += """, add to
         (f)ile-specific dictionary"""
    if offer_N:
        prompt += """, add to
         (N)ew file-specific dictionary"""
    prompt += """ [i]"""
    return prompt


def handle_add(unmatched_subtokens, filename, fq_filename, file_id_ref, dicts):
    """Handle addition of one or more subtokens to a dictionary.

    :param unmatched_subtokens: sequence of subtokens, each of which failed
           spell check
    :param filename: name of file containing the token
    :param fq_filename: fully-qualified filename
    :param file_id: unique identifier for current file: [string or None]
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :returns: True if subtokens were handled, False if canceled

    """
    (_, ext) = os.path.splitext(filename.lower())

    prompt = None

    for subtoken in unmatched_subtokens:
        while True:
            if prompt is None:
                file_id = file_id_ref[0]
                offer_p = (ext != '')
                offer_f = (file_id is not None)
                offer_N = dicts._relative_to is not None and not offer_f
                prompt = build_add_prompt(offer_p, offer_f, offer_N)

            print(prompt % subtoken)
            ch = _portable.getch()
            if ch in (_portable.CTRL_C, _portable.CTRL_D, _portable.CTRL_Z):
                sys.exit(2)
            elif ch == 'b':
                print("""\
         (Canceled.)\n""")
                return False
            elif ch in ('i', '\r', '\n'):
                break
            elif offer_p and ch == 'p':
                if dicts.add_by_extension(subtoken, ext):
                    break
                else:
                    if handle_new_extension(ext, dicts) and \
                            dicts.add_by_extension(subtoken, ext):
                        break
            elif ch == 'n':
                dicts.add_natural(subtoken)
                break
            elif offer_f and (ch == 'f'):
                dicts.add_by_file_id(subtoken, file_id)
                break
            elif offer_N and (ch == 'N'):
                file_id = get_new_file_id()
                file_id_ref[0] = file_id
                print('New file ID {0} for {1}'.format(file_id, filename),
                      file=sys.stderr)
                dicts.new_file_and_file_id(fq_filename, file_id)
                dicts.add_by_file_id(subtoken, file_id)
                prompt = None  # reselect prompt now that file_id is not None
                break
    return True


def handle_failed_check_interactively(
        match_desc, filename, fq_filename, file_id_ref,
        unmatched_subtokens, dicts, ignores):
    """Handle a token which failed the spell check operation.

    :param match_desc: description of the token matching instance
    :type  match_desc: MatchDescriptor
    :param filename: name of file containing the token, to be reported to user
    :param fq_filename: fully-qualified filename
    :param file_id_ref: unique identifier for current file: [string or None]
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
        if ch in (_portable.CTRL_C, _portable.CTRL_D, _portable.CTRL_Z):
            sys.exit(2)
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
            if handle_add(unmatched_subtokens, filename, fq_filename,
                          file_id_ref, dicts):
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
            "%s:%u: %s were not found in the dictionary (from token '%s')" %
            (filename,
             match_desc.get_line_num(),
             unmatched_subtokens,
             token),
            file=sys.stderr)
    # Default: text is unchanged
    return (match_desc.get_string(),
            match_desc.get_ofs() + len(match_desc.get_token()))


def spell_check_token(
        match_desc, fq_filename, file_id,
        dicts, ignores):
    """Spell check a single token.

    :param match_desc: description of the token matching instance
    :type  match_desc: MatchDescriptor
    :param filename: name of file containing the token, to be reported to user
    :param fq_filename: fully-qualified filename
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
            (not dicts.match(st, fq_filename, file_id)) and
            (st not in ignores)]
        unmatched_subtokens = make_unique(unmatched_subtokens)
        return unmatched_subtokens
    return []


def spell_check_str(source_text, fq_filename, dicts, ignores, c_escapes):
    """Spell check an in-memory "file".

    :param fq_filename: fully-qualified filename
    :param dicts: dictionary set against which to perform matching
    :type  dicts: CorporaFile
    :param ignores: set of tokens to ignore for this session

    """
    # Look for a file ID
    file_id = None
    m_id = FILE_ID_REGEX.search(source_text)
    if m_id is not None:
        file_id = m_id.group(1)
        _util.mutter(
            _util.VERBOSITY_DEBUG,
            '(File contains id "%s".)' %
            file_id)
    else:
        file_id = dicts.file_id_of_file(fq_filename)

    if c_escapes:
        token_regex = C_ESCAPE_TOKEN_REGEX
    else:
        token_regex = TOKEN_REGEX

    # Search for tokens to spell-check
    data = source_text
    pos = 0
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
        match_desc = MatchDescriptor(data, m)
        unmatched_subtokens = spell_check_token(match_desc,
                                   fq_filename, file_id,
                                   dicts, ignores)
        pos = match_desc.get_ofs() + len(match_desc.get_token())
        if unmatched_subtokens:
            new_data = yield file_id, match_desc, unmatched_subtokens
            if new_data:
                data, pos = new_data


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

    okay = True
    speller = spell_check_str(source_text, fq_filename, dicts, ignores, c_escapes)
    new_pos = None
    while True:
        try:
            file_id, match_desc, unmatched_subtokens = speller.send(new_pos)
        except StopIteration:
            break
        okay = False
        if report_only:
            report_failed_check(match_desc, filename,
                                        unmatched_subtokens)
        else:
            # HACK: Satisfy handle_failed_check_interactively API.  Mutation of
            # file_id is currently not handled.
            file_id_ref = [file_id]
            new_pos = handle_failed_check_interactively(
                    match_desc, filename, fq_filename, file_id_ref,
                    unmatched_subtokens, dicts, ignores)

    # Write out the source file if it was modified
    if new_pos and new_pos[0] != source_text:
        with _util.open_with_encoding(fq_filename, mode='w') as source_file:
            try:
                source_file.write(new_pos[0])
            except IOError as e:
                print(str(e), file=sys.stderr)
                return False

    return okay


def verify_user_data_dir():
    """Verify that the user data directory is present, or create one from
    scratch."""
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
        shutil.copyfile(SCSPELL_BUILTIN_DICT, DICT_DEFAULT_LOC)


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


def export_dictionary(filename, base_dicts):
    """Export the current keyword dictionary to the specified file.

    :returns: None

    """
    if (base_dicts):
        raise SystemExit(
            "--export-dictionary doesn't support " +
            '--base-dict')
        return
    shutil.copyfile(locate_dictionary(), filename)


def find_dict_file(override_dictionary):
    verify_user_data_dir()
    dict_file = locate_dictionary(
    ) if override_dictionary is None else override_dictionary

    return os.path.expandvars(os.path.expanduser(dict_file))


def spell_check(source_filenames, override_dictionary=None,
                base_dicts=[],
                relative_to=None, report_only=False, c_escapes=True,
                test_input=False):
    """Run the interactive spell checker on the set of source_filenames.

    If override_dictionary is provided, it shall be used as a dictionary
    filename for this session only.

    :returns: None

    """
    if test_input:
        _portable.allow_non_terminal_input()

    dict_file = find_dict_file(override_dictionary)

    okay = True
    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        ignores = set()
        for f in source_filenames:
            if not spell_check_file(f, dicts, ignores, report_only, c_escapes):
                okay = False
    return okay


def filter_out_base_dicts(override_dictionary=None, base_dicts=[]):
    """Remove from our dictionary the words from the base dicts.

    This can be useful for migrating from a version of scspell that did
    not support the --base-dicts option.

    """
    dict_file = find_dict_file(override_dictionary)
    with CorporaFile(dict_file, base_dicts, None) as dicts:
        dicts.filter_out_base_dicts()


def merge_file_ids(merge_from, merge_to,
                   override_dictionary=None, base_dicts=[], relative_to=None):
    """Merge the file IDs specified by merge_to and merge_from.

    Combine the wordlists in the specified dictionary, and their file ID map
    entries.  They each may be either a file ID, or a filename.  If a filename,
    the file ID corresponding to it is the one merged.

    Use merge_to for the result, discarding merge_from.

    """
    dict_file = find_dict_file(override_dictionary)

    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        dicts.merge_file_ids(merge_from, merge_to)


def copy_file(copy_from, copy_to,
              override_dictionary=None, base_dicts=[], relative_to=None):
    """Set up the file copy_to to use the same per-file dictionary as
    copy_from."""
    dict_file = find_dict_file(override_dictionary)

    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        dicts.copy_file(copy_from, copy_to)


def rename_file(rename_from, rename_to,
                override_dictionary=None, base_dicts=[], relative_to=None):
    """Rename the file rename_from to rename_to.

    This is with respect to the file ID mappings.

    """
    dict_file = find_dict_file(override_dictionary)

    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        dicts.rename_file(rename_from, rename_to)


def add_to_dict(dictionary_type, word, files=[],
                override_dictionary=None, base_dicts=[], relative_to=None):
    """Add word to dictionary_type.

    This is with respect to the filename ID mappings if 'file' type
    dictionary is used."""
    dict_file = find_dict_file(override_dictionary)

    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        if dictionary_type[0] == 'n':
            dicts.add_natural(word)

        elif dictionary_type[0] == 'f':
            fq_filename = os.path.normcase(os.path.realpath(files[0]))
            file_id = dicts.file_id_of_file(fq_filename)
            if not file_id:
                file_id = get_new_file_id()
                print('New file ID {0} for {1}'.format(file_id, files[0]),
                      file=sys.stderr)
                dicts.new_file_and_file_id(fq_filename, file_id)
            dicts.add_by_file_id(word, file_id)

        elif dictionary_type[0] == 'p':
            ext = re.sub(r'.*\.', '.', '.{}'.format(files[0].lower()))
            if not dicts.add_by_extension(word, ext):
                print("Dictionary for file extension '{}' not found."
                      .format(ext), file=sys.stderr)

        else:
            print("Dictionary type '{}' not recognized."
                  .format(dictionary_type), file=sys.stderr)


def delete_files(delete_files,
                 override_dictionary=None, base_dicts=[], relative_to=None):
    """Remove all trace of delete_file."""
    dict_file = find_dict_file(override_dictionary)
    with CorporaFile(dict_file, base_dicts, relative_to) as dicts:
        for file in delete_files:
            dicts.delete_file(file)


def main():
    parser = argparse.ArgumentParser(description=__doc__, prog='scspell')

    dict_group = parser.add_argument_group('dictionary file management')
    spell_group = parser.add_argument_group('spell-check control')
    test_group = parser.add_argument_group('testing options')

    spell_group.add_argument(
        '--report-only', dest='report', action='store_true',
        help='non-interactive report of spelling errors')
    spell_group.add_argument(
        '--no-c-escapes', dest='c_escapes',
        action='store_false', default=True,
        help='treat \\label as label, for e.g. LaTeX')

    dict_group.add_argument(
        '--override-dictionary', dest='override_filename',
        help='set location of dictionary to FILE, for current session only',
        metavar='FILE', action='store')
    dict_group.add_argument(
        '--set-dictionary', dest='dictionary',
        help='permanently set location of dictionary to FILE', metavar='FILE',
        action='store')
    dict_group.add_argument(
        '--export-dictionary', dest='export_filename',
        help='export current dictionary to FILE', metavar='FILE',
        action='store')
    dict_group.add_argument(
        '--base-dict', dest='base_dicts', action='append', default=[],
        metavar='BASE_DICT',
        help="Match words from BASE_DICT, but don't modify it.")
    dict_group.add_argument(
        '--use-builtin-base-dict', dest='base_dicts',
        action='append_const', const=SCSPELL_BUILTIN_DICT,
        help="Use scspell's default wordlist as a base dictionary ({0})"
        .format(SCSPELL_BUILTIN_DICT))
    dict_group.add_argument(
        '--filter-out-base-dicts', action='store_true',
        help='Remove from the dictionary file '
             'all the words from the base dicts')
    dict_group.add_argument(
        '--relative-to', dest='relative_to',
        help='use file paths relative to here in file ID map.  '
             'This is required to enable use of the file ID map',
        action='store')
    dict_group.add_argument(
        '-i', '--gen-id', dest='gen_id', action='store_true',
        help='generate a unique file-id string')
    dict_group.add_argument(
        '--merge-file-ids', nargs=2,
        metavar=('FROM_ID', 'TO_ID'),
        help='merge these two file IDs, keeping TO_ID and discarding FROM_ID; '
             'combine their word lists in the dictionary, and the filenames '
             'associated with them in the file ID map; TO_ID and FROM_ID may '
             'be given as file IDs, or as filenames in which case the file '
             'IDs corresponding to those files are operated on; does NOT look '
             'for or consider any file IDs embedded in to-be-spell-checked '
             'files; if your filenames look like file IDs, do it by hand')
    dict_group.add_argument(
        '--copy-file', nargs=2,
        metavar=('FROM_FILE', 'TO_FILE'),
        help='inform scspell that TO_FILE is a copy of FROM_FILE; '
             'effectively, set up TO_FILE to use the same per-file dictionary '
             'as FROM_FILE')
    dict_group.add_argument(
        '--rename-file', nargs=2,
        metavar=('FROM_FILE', 'TO_FILE'),
        help='inform scspell that FROM_FILE has been renamed TO_FILE; '
             'if an entry in the file ID mapping references FROM_FILE, it '
             'will be modified to reference TO_FILE instead')
    dict_group.add_argument(
        '--delete-files', action='store_true', default=False,
        help='inform scspell that the listed files have been deleted; all '
             'file ID mappings for the files will be removed; if all uses of '
             'that file ID have been removed, the corresponding file-private '
             'dictionary will be removed; this will not spell check the '
             'files')
    dict_group.add_argument(
        '--add-to-dict', nargs=2,
        metavar=('DICT_TYPE', 'WORD'),
        help="Add WORD to DICT_TYPE dictionary. If adding to 'file' or "
             "'programming' dictionary then file argument is also required. "
             'Possible DICT_TYPE values are n[atural], p[rogramming], f[ile]')

    #  Testing option to allow scspell to read stdin from a non-tty
    test_group.add_argument(
        '--test-input', action='store_true', default=False,
        help=argparse.SUPPRESS)

    parser.add_argument(
        '-D', '--debug', dest='debug', action='store_true',
        help='print extra debugging information')
    parser.add_argument(
        '--version', action='version',
        version='%(prog)s ' + __version__)
    parser.add_argument(
        'files', nargs='*', help='files to check')

    args = parser.parse_args()

    if args.debug:
        set_verbosity(VERBOSITY_MAX)

    if args.gen_id:
        print('scspell-id: %s' % get_new_file_id())
    elif args.dictionary is not None:
        set_dictionary(args.dictionary)
    elif args.export_filename is not None:
        export_dictionary(args.export_filename, args.base_dicts)
        print("Exported dictionary to '{}'".format(args.export_filename),
              file=sys.stderr)
    elif args.merge_file_ids is not None:
        merge_file_ids(args.merge_file_ids[0], args.merge_file_ids[1],
                       args.override_filename,
                       args.base_dicts, args.relative_to)
    elif args.copy_file is not None:
        copy_file(args.copy_file[0], args.copy_file[1],
                  args.override_filename,
                  args.base_dicts, args.relative_to)
    elif args.rename_file is not None:
        rename_file(args.rename_file[0], args.rename_file[1],
                    args.override_filename,
                    args.base_dicts, args.relative_to)
    elif args.delete_files:
        if len(args.files) < 1:
            parser.error('No files specified for delete')
        delete_files(args.files,
                     args.override_filename,
                     args.base_dicts, args.relative_to)
    elif args.add_to_dict is not None:
        dictionary_type = str(args.add_to_dict[0])
        if dictionary_type in ['p', 'programming'] and len(args.files) < 1:
            parser.error('No file (or extension) specified')
        elif dictionary_type in ['f', 'file'] and len(args.files) < 1:
            parser.error('No file specified')
        elif dictionary_type in ['f', 'file'] and not args.relative_to:
            parser.error("--relative-to is required in order to use '{}' "
                         'dictionary type'.format(dictionary_type))
        elif dictionary_type not in ['p', 'programming',
                                     'f', 'file', 'n', 'natural']:
            parser.error("Dictionary type '{}' not found."
                         .format(dictionary_type))

        add_to_dict(args.add_to_dict[0], args.add_to_dict[1],
                    args.files,
                    args.override_filename,
                    args.base_dicts,
                    args.relative_to)
    elif args.filter_out_base_dicts:
        filter_out_base_dicts(args.override_filename, args.base_dicts)
    elif len(args.files) < 1:
        parser.error('No files specified')
    else:
        okay = spell_check(args.files,
                           args.override_filename,
                           args.base_dicts,
                           args.relative_to,
                           args.report,
                           args.c_escapes,
                           args.test_input)
        return 0 if okay else 1
