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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

"""Defines methods for storing dictionaries and performing searches against
them."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import errno
import io
import json
import os
import re
import sys
from bisect import bisect_left
from . import _util


DICT_TYPE_NATURAL = 'NATURAL'       # Identifies natural language dictionary
DICT_TYPE_FILETYPE = 'FILETYPE'      # Identifies file-type-specific dictionary
DICT_TYPE_FILEID = 'FILEID'        # Identifies file-specific dictionary


# Valid file ID strings take this form
FILE_ID_REGEX = re.compile(r'[a-zA-Z0-9_\-]+')


class ParsingError(Exception):

    """An error occurred when parsing the dictionary file."""


class Corpus(object):

    """Base class for various types of (textual) dictionary-like objects."""

    def __init__(self, dict_type, metadata):
        self._dirty = False
        self._dict_type = dict_type
        self._metadata = metadata

    def _mark_dirty(self):
        self._dirty = True

    def _mark_clean(self):
        self._dirty = False

    def is_dirty(self):
        return self._dirty

    def get_name(self):
        """Get the descriptive name of this dictionary."""
        assert self._dict_type == DICT_TYPE_FILETYPE
        (name, _) = self._metadata
        return name

    def get_extensions(self):
        """Get the list of extensions associated with this dictionary."""
        assert self._dict_type == DICT_TYPE_FILETYPE
        (_, extensions) = self._metadata
        return extensions

    def add_extension(self, extension):
        """Append the extension to the list of extensions associated with this
        dictionary."""
        assert self._dict_type == DICT_TYPE_FILETYPE
        (_, extensions) = self._metadata
        extensions.append(extension)

    def match(self, token):
        """Return True if the token is present in this Corpus.

        The matching method is Corpus-specific.

        """
        raise NotImplementedError

    def add(self, token):
        """Add the specified token to this Corpus."""
        raise NotImplementedError

    def write(self, f):
        """Write the contents of this Corpus to f, a file-like object."""
        raise NotImplementedError

    def _write_header(self, f):
        """Write the corpus header to f, a file-like object."""
        if self._dict_type == DICT_TYPE_NATURAL:
            f.write('%s:\n' % DICT_TYPE_NATURAL)
        elif self._dict_type == DICT_TYPE_FILETYPE:
            (name, extensions) = self._metadata
            f.write(
                '%s: %s; %s\n' % (
                    DICT_TYPE_FILETYPE,
                    name,
                    ', '.join(
                        extensions)))
        elif self._dict_type == DICT_TYPE_FILEID:
            f.write('%s: %s\n' % (DICT_TYPE_FILEID, self._metadata))
        else:
            raise AssertionError('Unknown dict_type "%s".' % self._dict_type)


class ExactMatchCorpus(Corpus):

    """A token matches against an ExactMatchCorpus iff it is present in the
    corpus."""

    def __init__(self, dict_type, metadata, tokens):
        """Construct an instance from a sequence of tokens, giving it the
        specified dictionary type and associated metadata."""
        Corpus.__init__(self, dict_type, metadata)
        self._tokens = set(tokens)

    def match(self, token):
        """Return True if the token is present in this Corpus."""
        return token in self._tokens

    def add(self, token):
        """Add the specified token to this Corpus."""
        if token not in self._tokens:
            self._tokens.add(token)
            self._mark_dirty()

    def write(self, f):
        """Write the contents of this Corpus to f, a file-like object."""
        self._write_header(f)
        for token in sorted(list(self._tokens)):
            f.write(token + '\n')
        f.write('\n')
        self._mark_clean()


class PrefixMatchCorpus(Corpus):

    """A token matches against a PrefixMatchCorpus iff the token is a prefix of
    any item in the corpus."""

    def __init__(self, dict_type, metadata, tokens):
        """Construct an instance from a sequence of tokens, giving it the
        specified dictionary type and associated metadata."""
        Corpus.__init__(self, dict_type, metadata)
        self._tokens = sorted(tokens)

    def match(self, token):
        """Return True if the token is a prefix of an item in this Corpus."""
        insertion_point = bisect_left(self._tokens, token)
        if insertion_point < len(self._tokens):
            return self._tokens[insertion_point].startswith(token)
        else:
            return False

    def add(self, token):
        """Add the specified token to this Corpus."""
        insertion_point = bisect_left(self._tokens, token)
        if (insertion_point >= len(self._tokens) or
                self._tokens[insertion_point] != token):
            self._tokens.insert(insertion_point, token)
            self._mark_dirty()

    def write(self, f):
        """Write the contents of this Corpus to f, a file-like object."""
        self._write_header(f)
        for token in self._tokens:
            f.write(token + '\n')
        f.write('\n')
        self._mark_clean()


class CorporaFile(object):

    """The CorporaFile manages a single file containing multiple corpora.

    May include filename<->fileid mapping file too."""

    def __init__(self, filename, relative_to):
        """Construct an instance from the file with the given filename.

        relative_to is the directory to consider paths relative to wrt
        the fileid mapping.

        """
        self._filename = filename

        # Empty defaults
        self._natural_dict = None     # Natural language dictionary
        self._filetype_dicts = []       # File-type-specific dictionaries
        self._fileid_dicts = []       # File-specific dictionaries
        self._extensions = {}
        # Associates each extension with a file-type dictionary
        self._fileids = {}
        # Associates each file-id with a file-specific dictionary

        self._relative_to = None
        if relative_to is not None:
            self._relative_to = os.path.normcase(os.path.realpath(relative_to))
        self._fileid_mapping = {}
        self._fileid_mapping_is_dirty = False
        # mapping of fileid -> list-of-filenames for fileids not stored in the
        # source files.

        try:
            with _util.open_with_encoding(filename, mode='r') as f:
                lines = [line.strip(' \r\n') for line in f.readlines()]
            self._parse(lines)
        except IOError as e:
            print(
                'Warning: unable to read dictionary file '
                "'{}' (reason: {})".format(filename, e),
                file=sys.stderr)
        except ParsingError as e:
            raise SystemExit(
                "Error while parsing dictionary file '{}': {}".format(
                    filename, e))

        if self._natural_dict is None:
            print('Continuing with empty natural dictionary\n',
                  file=sys.stderr)
            self._natural_dict = PrefixMatchCorpus(DICT_TYPE_NATURAL, '', [])

        if not self._relative_to:
            return
        mapping_file = self._filename + ".fileids.json"
        try:
            with io.open(mapping_file, mode='r', encoding='utf-8') as mf:
                self._fileid_mapping = json.load(mf)
                _util.mutter(_util.VERBOSITY_DEBUG,
                             "got fileid mapping:\n{0}".format(self._fileid_mapping))
        except IOError as e:
            if e.errno == errno.ENOENT:
                _util.mutter(_util.VERBOSITY_DEBUG,
                             "No fileid mappings file {0}".format(
                                 mapping_file))
            else:
                raise SystemExit(
                    "Can't read fileid mappings file {0}: {1}: {2}".format(
                        mapping_file, e.errno, e.strerror))


    def match(self, token, filename, file_id):
        """Return True if the token matches any of the applicable corpora.

        :param token: string being matched
        :param filename: name of file containing token
        :param file_id: unique identifier for current file
        :type  file_id: string or None
        :returns: True if token matches a dictionary

        """
        if self._natural_dict.match(token):
            return True

        (_, ext) = os.path.splitext(filename.lower())
        try:
            corpus = self._extensions[ext]
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Matching against filetype "%s".)' %
                corpus.get_name())
            if corpus.match(token):
                return True
        except KeyError:
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(No filetype match for extension "%s".)' %
                ext)

        if file_id is not None:
            try:
                corpus = self._fileids[file_id]
                _util.mutter(
                    _util.VERBOSITY_DEBUG,
                    '(Matching against file-id "%s".)' %
                    file_id)
                if corpus.match(token):
                    return True
            except KeyError:
                _util.mutter(
                    _util.VERBOSITY_DEBUG,
                    '(No file-id match for "%s".)' %
                    file_id)

        return False

    def add_natural(self, token):
        """Add the token to the natural language corpus."""
        self._natural_dict.add(token)

    def add_by_extension(self, token, extension):
        """Add the token to a programming language-specific corpus associated
        with the extension.

        Returns True if the add was successful, False if there is no corpus
        with a matching filename extension.

        """
        try:
            corpus = self._extensions[extension]
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Adding to filetype "%s".)' %
                corpus.get_name())
            corpus.add(token)
            return True
        except KeyError:
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(No filetype match for extension "%s".)' %
                extension)
            return False

    def add_by_fileid(self, token, file_id):
        """Add the token to a file-specific corpus.

        If there is no corpus for the given file_id, a new one is created.

        """
        try:
            corpus = self._fileids[file_id]
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Adding to file-id "%s".)' %
                file_id)
            corpus.add(token)
        except KeyError:
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(No file-id match for "%s"; creating new.)' %
                file_id)
            corpus = ExactMatchCorpus(DICT_TYPE_FILEID, file_id, [])
            self._fileid_dicts.append(corpus)
            self._fileids[file_id] = corpus
            corpus.add(token)

    def _make_relative_filename(self, fq_filename):
        """return fq_filename relative to self._relative_to"""
        rt_len = len(self._relative_to)
        if not fq_filename.startswith(self._relative_to):
            raise SystemExit("Processing file {0} not within --relative-to {1}".
                             format(fq_filename, self._relative_to))
        rfn = fq_filename[len(self._relative_to):]

        # if relative_to doesn't end in /, we want to make sure we
        # trim the leading / (or /'es) from rfn
        while len(rfn) > 0 and rfn[0] == '/':
            rfn = rfn[1:]
        if len(rfn) == 0:
            raise SystemExit("Making {0} relative to {1}: There's nothing "
                             "left!".format(fq_filename, self._relative_to))
        return rfn

    def new_file_and_fileid(self, fq_filename, file_id):
        """Add a mapping for this filename and file_id"""

        if self._relative_to is None:
            raise AssertionError("new_file_and_fileid called without "
                                 "--relative-to")
        relfn = self._make_relative_filename(fq_filename)
        for (fid,fnames) in self._fileid_mapping.items():
            for fname in fnames:
                if fname == relfn:
                    raise AssertionError("{0} already has file_id {1}".format(
                        fname, fid))
        if file_id not in self._fileid_mapping:
            self._fileid_mapping[file_id] = []
        if relfn not in self._fileid_mapping[file_id]:
            # todo: maintain mapping[file_id] as sorted list
            # for more friendly human-editing
            self._fileid_mapping[file_id].append(relfn)
            self._fileid_mapping_is_dirty = True

    def fileid_of_file(self, fq_filename):
        # should really build the inverse hash for this lookup...
        if self._relative_to is None:
            return None
        relfn = self._make_relative_filename(fq_filename)
        for fileid,files in self._fileid_mapping.items():
            if relfn in files:
                file_id = fileid
                _util.mutter(
                    _util.VERBOSITY_DEBUG,
                    '(fileid_mapping contains id "{0}".)'.format(file_id))
                return file_id
        return None

    def get_filetypes(self):
        """Get a list of file types with type-specific corpora."""
        return [corpus.get_name() for corpus in self._filetype_dicts]

    def new_filetype(self, type_descr, extensions):
        """Add a new file-type corpus with the given description, associated
        with the given set of extensions."""
        assert type_descr not in self.get_filetypes()
        for ext in extensions:
            assert ext not in self._extensions

        corpus = ExactMatchCorpus(
            DICT_TYPE_FILETYPE,
            (type_descr,
             extensions),
            [])
        self._filetype_dicts.append(corpus)
        for ext in extensions:
            self._extensions[ext] = corpus

    def register_extension(self, extension, type_descr):
        """Associate the extension with the file-type that has the given
        description."""
        assert extension not in self._extensions
        for corpus in self._filetype_dicts:
            if corpus.get_name() == type_descr:
                self._extensions[extension] = corpus
                corpus.add_extension(extension)
                return
        raise AssertionError('type_descr "%s" not present.' % type_descr)

    def close(self):
        """Update the corpus file iff the contents were modified."""
        dirty = (
            self._natural_dict.is_dirty() if self._natural_dict is not None
            else False
        )
        for corpus in self._filetype_dicts:
            dirty = dirty or corpus.is_dirty()
        for corpus in self._fileid_dicts:
            dirty = dirty or corpus.is_dirty()
        if dirty:
            try:
                with _util.open_with_encoding(self._filename, mode='w') as f:
                    for corpus in self._filetype_dicts:
                        corpus.write(f)
                    for corpus in self._fileid_dicts:
                        corpus.write(f)
                    # Natural language dict goes at the end for readability...
                    # it is typically much bigger than the other dictionaries
                    self._natural_dict.write(f)
            except IOError as e:
                print("Warning: unable to write dictionary file '{}' "
                      '(reason: {})'.format(self._filename, e))

        if self._fileid_mapping_is_dirty:
            if self._relative_to is None:
                raise AssertionError("fileid mapping is dirty but " +
                                     "relative_to is None")
            mapping_file = self._filename + ".fileids.json"
            try:
                with io.open(mapping_file, mode='w', encoding='utf-8') as mf:
                    # http://stackoverflow.com/questions/36003023/json-dump-failing-with-must-be-unicode-not-str-typeerror
                    tstr = json.dumps(self._fileid_mapping, ensure_ascii=False,
                                      indent=2)
                    if isinstance(tstr, str):
                        tstr = tstr.decode("utf-8")
                    mf.write(tstr)
                self._fileid_mapping_is_dirty = False
            except IOError as e:
                print("Warning: unable to write fileid mapping file '{0}' "
                      "(reason: {1})".format(mapping_file, e))

    def _parse(self, lines):
        """Parse the lines into a set of corpora."""
        offset = 0
        while offset < len(lines):
            offset = self._parse_corpus(lines, offset)

    def _parse_corpus(self, lines, offset):
        """Parse a single corpus starting at an offset into lines."""
        (dict_type, metadata) = self._parse_header_line(
            lines[offset], offset + 1)
        (offset, tokens) = _read_corpus_tokens(offset, lines)

        if dict_type == DICT_TYPE_NATURAL:
            self._natural_dict = PrefixMatchCorpus(
                DICT_TYPE_NATURAL, metadata, tokens)
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Loaded natural language dictionary with %u tokens.)' %
                len(tokens))
            return offset

        if dict_type == DICT_TYPE_FILETYPE:
            (type_descr, extensions) = metadata
            corpus = ExactMatchCorpus(DICT_TYPE_FILETYPE, metadata, tokens)
            self._filetype_dicts.append(corpus)
            for ext in extensions:
                self._extensions[ext] = corpus
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Loaded file-type dictionary "%s" with %u tokens.)' %
                (type_descr, len(tokens)))
            return offset

        if dict_type == DICT_TYPE_FILEID:
            corpus = ExactMatchCorpus(DICT_TYPE_FILEID, metadata, tokens)
            self._fileid_dicts.append(corpus)
            self._fileids[metadata] = corpus
            _util.mutter(
                _util.VERBOSITY_DEBUG,
                '(Loaded file-id dictionary "%s" with %u tokens.)' %
                (metadata, len(tokens)))
            return offset

        raise AssertionError('Unknown dict_type "%s".' % dict_type)

    def _parse_header_line(self, line, line_num):
        """Parse a dictionary header line.

        Headers take the form

            <DICTIONARY TYPE>: <type-specific metadata>

            * If the dictionary type is ``NATURAL`` then the metadata shall be
              empty. The following word list is a natural-language dictionary.

            * If the dictionary type is ``FILETYPE``, then the metadata shall
              take the form "<descriptive name>; <comma-separated extensions
              list>". The name shall be a human-readable description of the
              file type (e.g. the name of the programming language), and the
              extensions list shall be a list of extensions to associate with
              this file type.

            * If the dictionary type is ``FILEID``, then the metadata shall be
              a unique identifier string associated with a particular file

        The return value is the tuple (dictionary type, metadata), where the
        metadata returned is of a type appropriate for the type of dictionary.

        """
        try:
            (raw_dict_type, raw_metadata) = line.split(':')
        except ValueError:
            raise ParsingError('Syntax error in header on line %u.' % line_num)

        dict_type = raw_dict_type.strip()
        metadata = raw_metadata.strip()

        if dict_type == DICT_TYPE_NATURAL:
            if metadata != '':
                raise ParsingError(
                    'Dictionary header "%s" on line %u has nonempty '
                    'metadata.' % (DICT_TYPE_NATURAL, line_num))
            if self._natural_dict is not None:
                raise ParsingError(
                    'Duplicate dictionary type "%s" on line %u.' %
                    (DICT_TYPE_NATURAL, line_num))
            return (dict_type, None)

        if dict_type == DICT_TYPE_FILETYPE:
            try:
                (raw_descr, raw_extensions) = metadata.split(';')
            except ValueError:
                raise ParsingError(
                    'Syntax error in %s dictionary header on line %u.' %
                    (DICT_TYPE_FILETYPE, line_num))

            descr = raw_descr.strip()
            extensions = [
                ext.strip().lower()
                for ext in raw_extensions.split(',')]
            extensions = [ext for ext in extensions if ext != '']

            if descr == '':
                raise ParsingError(
                    'File type-description on line %u is empty.' %
                    line_num)
            for corpus in self._filetype_dicts:
                if corpus.get_name() == descr:
                    raise ParsingError(
                        'Duplicate file-type description "%s" on line %u.' %
                        (descr, line_num))
            if extensions == []:
                raise ParsingError(
                    'Missing extensions list in %s dictionary header on line '
                    '%u.' % (DICT_TYPE_FILETYPE, line_num))
            for ext in extensions:
                if not ext.startswith('.'):
                    raise ParsingError(
                        'Extension "%s" on line %u does not begin with a '
                        'period.' % (ext, line_num))
                if ext in self._extensions:
                    raise ParsingError(
                        'Duplicate extension "%s" on line %u.' %
                        (ext, line_num))
            return (dict_type, (descr, extensions))

        if dict_type == DICT_TYPE_FILEID:
            if FILE_ID_REGEX.match(metadata) is None:
                raise ParsingError(
                    '%s metadata string "%s" on line %u is not a valid file '
                    'ID.' % DICT_TYPE_FILEID, metadata, line_num)
            if metadata in self._fileids:
                raise ParsingError(
                    'Duplicate file ID string "%s" on line %u.' %
                    (metadata, line_num))
            return (dict_type, metadata)

        raise ParsingError(
            'Unrecognized dictionary type "%s" on line %u.' %
            (dict_type, line_num))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()
        return False


def _read_corpus_tokens(offset, lines):
    """Read the set of tokens for the corpus which begins at the given offset.

    Returns the tuple (next offset, tokens).

    """
    tokens = []
    for i, line in enumerate(lines[offset + 1:]):
        if ':' in line:
            return (offset + i + 1, tokens)
        elif line != '':
            tokens.append(line)
    return (len(lines), tokens)
