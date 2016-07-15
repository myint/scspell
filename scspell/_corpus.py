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

from collections import OrderedDict
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

MATCH_NATURAL = 0x1
MATCH_FILETYPE = 0x2
MATCH_FILEID = 0x4


class CorporaFile(object):

    """The CorporaFile manages a single file containing multiple corpora.

    May include filename<->file ID mapping file too."""

    def __init__(self, filename, base_dicts, relative_to):
        """Construct an instance from the file with the given filename.

        If there are any base_dicts, load them for checking against,
        but don't modify them or write them out.

        relative_to is the directory to consider paths relative to wrt
        the file ID mapping.

        """
        self._base_corpora_files = []
        for fn in base_dicts:
            self._base_corpora_files.append(
                CorporaFile(fn, [], relative_to))

        self._filename = filename

        # Empty defaults
        self._natural_dict = None     # Natural language dictionary
        self._filetype_dicts = []     # File-type-specific dictionaries
        self._file_id_dicts = []      # File-specific dictionaries
        self._extensions = {}
        # Associates each extension with a file-type dictionary
        self._file_ids = {}
        # Associates each file-id with a file-specific dictionary

        self._relative_to = None
        if relative_to is not None:
            self._relative_to = os.path.normcase(os.path.realpath(relative_to))
        self._file_id_mapping = {}
        self._file_id_mapping_is_dirty = False
        # mapping of file ID -> list-of-filenames for file IDs not
        # stored in the source files.
        self._reverse_file_id_mapping = {}
        # Reverse map of the above, individual filename -> file ID

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
                try:
                    self._file_id_mapping = json.load(mf)
                    _util.mutter(_util.VERBOSITY_DEBUG,
                                 "got file ID mapping:\n{0}"
                                 .format(self._file_id_mapping))
                except ValueError as e:
                    # Error during file creation might leave an empty file
                    # here.  Not necessarily fatal, but report it.
                    _util.mutter(_util.VERBOSITY_NORMAL,
                                 "Couldn't load file ID mapping from {0}: {1}"
                                 .format(mapping_file, e))
        except IOError as e:
            if e.errno == errno.ENOENT:
                _util.mutter(_util.VERBOSITY_DEBUG,
                             "No file ID mappings file {0}".format(
                                 mapping_file))
            else:
                raise SystemExit(
                    "Can't read file ID mappings file {0}: {1}: {2}".format(
                        mapping_file, e.errno, e.strerror))

        # Build reverse map
        for k, v in self._file_id_mapping.items():
            for f in v:
                self._reverse_file_id_mapping[f] = k

    def match(self, token, filename, file_id,
              match_in=MATCH_NATURAL | MATCH_FILETYPE | MATCH_FILEID):
        """Return True if the token matches any of the applicable corpora.

        :param token: string being matched
        :param filename: name of file containing token
        :param file_id: unique identifier for current file
        :type  file_id: string or None
        :param match_in: Limit the corpora we search
        :returns: True if token matches a dictionary

        """
        for bc in self._base_corpora_files:
            if bc.match(token, filename, file_id, match_in):
                return True

        if match_in & MATCH_NATURAL and self._natural_dict.match(token):
            return True

        if match_in & MATCH_FILETYPE:
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

        if match_in & MATCH_FILEID and file_id is not None:
            try:
                corpus = self._file_ids[file_id]
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

    def token_is_in_base_dict(self, token, filename, file_id,
                              match_in=MATCH_NATURAL | MATCH_FILETYPE |
                              MATCH_FILEID):
        for bc in self._base_corpora_files:
            if bc.match(token, filename, file_id, match_in):
                return True

    def filter_out_base_dicts(self):
        # For each of our corpora, for each word, if that word is in a
        # base dict, remove it from the corpora.
        #
        # Only remove it when the base dict match was at least as
        # general as the corpora we're processing.  E.g., only remove
        # from our natural_dict when the word was in the natural_dict
        # of some base_dict; not if it was in a filetype or file ID dict.
        # Similarly, only remove from our filetype dict if the word was
        # in a natural_dict or the filetype dict with the same extension.
        new_tokens = []
        for t in self._natural_dict._tokens:
            if self.token_is_in_base_dict(t, None, None, MATCH_NATURAL):
                # Going to change the dict, so mark it dirty
                self._natural_dict._mark_dirty()
            else:
                new_tokens.append(t)
        self._natural_dict._tokens = new_tokens

        for ext in self._extensions:
            # Generate a fake file name to use to query the base dicts.
            # Since we aren't using MATCH_FILEID, the basename won't be
            # used, only the extension.
            fake_filename = "fake." + ext
            file_type_corp = self._extensions[ext]
            new_tokens = []
            for t in file_type_corp._tokens:
                if self.token_is_in_base_dict(t, fake_filename, None,
                                              MATCH_NATURAL | MATCH_FILETYPE):
                    file_type_corp._mark_dirty()
                else:
                    new_tokens.append(t)
            file_type_corp._tokens = new_tokens

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

    def add_by_file_id(self, token, file_id):
        """Add the token to a file-specific corpus.

        If there is no corpus for the given file_id, a new one is created.

        """
        try:
            corpus = self._file_ids[file_id]
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
            self._file_id_dicts.append(corpus)
            self._file_ids[file_id] = corpus
            corpus.add(token)

    def _make_relative_filename(self, fq_filename):
        """return fq_filename relative to self._relative_to"""
        if not fq_filename.startswith(self._relative_to):
            raise SystemExit("File {0} not within --relative-to {1}".
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

    def _fn_to_rel(self, filename):
        """Given a filename relative to ".", return the filename
           relative to the --relative-to path"""
        fq_filename = os.path.normcase(os.path.realpath(filename))
        rel_filename = self._make_relative_filename(fq_filename)
        return rel_filename

    def new_file_and_file_id(self, fq_filename, file_id):
        """Add a mapping for this filename and file_id"""

        if self._relative_to is None:
            raise AssertionError("new_file_and_file_id called without "
                                 "--relative-to")
        rel_filename = self._make_relative_filename(fq_filename)
        if rel_filename in self._reverse_file_id_mapping:
            raise AssertionError("{0} already has file_id {1}".format(
                rel_filename, self._reverse_file_id_mapping[rel_filename]))
        self._reverse_file_id_mapping[rel_filename] = file_id
        if file_id not in self._file_id_mapping:
            self._file_id_mapping[file_id] = []
        if rel_filename not in self._file_id_mapping[file_id]:
            self._file_id_mapping[file_id].append(rel_filename)
            self._file_id_mapping[file_id] = sorted(
                self._file_id_mapping[file_id])
            self._file_id_mapping_is_dirty = True

    def file_id_of_rel_file(self, rel_filename):
        try:
            return self._reverse_file_id_mapping[rel_filename]
        except:
            return None

    def file_id_of_file(self, fq_filename):
        if self._relative_to is None:
            return None
        rel_filename = self._make_relative_filename(fq_filename)
        return self.file_id_of_rel_file(rel_filename)

    def file_id_exists(self, file_id):
        if file_id in self._file_id_mapping:
            return True
        return False

    def merge_file_ids(self, merge_from, merge_to):
        if self.file_id_exists(merge_to):
            id_to = merge_to
        else:
            filename_to = merge_to
            if self._relative_to is not None:
                filename_to = self._fn_to_rel(filename_to)
            id_to = self.file_id_of_rel_file(filename_to)
            if id_to is None:
                raise SystemExit("Can't find merge_to {0} as file ID or file".
                                 format(merge_to))

        if self.file_id_exists(merge_from):
            id_from = merge_from
        else:
            filename_from = merge_from
            if self._relative_to is not None:
                filename_from = self._fn_to_rel(filename_from)
            id_from = self.file_id_of_rel_file(filename_from)
            if id_from is None:
                raise SystemExit("Can't find merge_from {0} as file ID or file"
                                 "".format(id_from))

        _util.mutter(_util.VERBOSITY_DEBUG,
                     "Going to merge {id_from} into {id_to}".format(
                         id_from=id_from, id_to=id_to))

        # merge wordlists
        from_corpus = self._file_ids[id_from]
        to_corpus = self._file_ids[id_to]
        for t in from_corpus._tokens:
            to_corpus.add(t)
        del self._file_ids[id_from]
        self._file_id_dicts.remove(from_corpus)

        # Add id_from's files to id_to
        from_files = self._file_id_mapping[id_from]
        to_files = self._file_id_mapping[id_to]
        for f in from_files:
            to_files.append(f)
            self._reverse_file_id_mapping[f] = id_to
        self._file_id_mapping[id_to] = sorted(to_files)
        self._file_id_mapping_is_dirty = True

    def delete_file(self, filename):
        rel_filename = self._fn_to_rel(filename)
        try:
            id = self._reverse_file_id_mapping[rel_filename]
        except:
            if filename == rel_filename:
                report_str = filename
            else:
                report_str = "{0} ({1})".format(filename, rel_filename)
            _util.mutter(_util.VERBOSITY_NORMAL,
                         "No file ID for {0}".format(report_str))
            return
        _util.mutter(_util.VERBOSITY_NORMAL,
                     "Removing {0} <-> {1} mappings".format(
                         filename, id))
        del self._reverse_file_id_mapping[rel_filename]
        fns = self._file_id_mapping[id]
        fns.remove(rel_filename)
        if len(fns) == 0:
            # No remaining files use this file ID.  Remove all trace of it.
            del self._file_id_mapping[id]

            # remove file ID-private dictionary from corpus.
            corpus = self._file_ids[id]
            self._file_id_dicts.remove(corpus)
            del self._file_ids[id]
        self._file_id_mapping_is_dirty = True

    def rename_file(self, rename_from, rename_to):
        from_rel = self._fn_to_rel(rename_from)
        to_rel = self._fn_to_rel(rename_to)
        if from_rel not in self._reverse_file_id_mapping:
            _util.mutter(_util.VERBOSITY_NORMAL,
                         "No file ID for " + rename_from)
            return

        if to_rel in self._reverse_file_id_mapping:
            self.delete_file(to_rel)

        id_from = self._reverse_file_id_mapping[from_rel]

        _util.mutter(_util.VERBOSITY_NORMAL,
                     "Switching file ID {0} from {1} to {2}".format(
                         id_from, from_rel, to_rel))

        fns = self._file_id_mapping[id_from]
        fns.remove(from_rel)
        fns.append(to_rel)
        self._file_id_mapping[id_from] = sorted(fns)

        self._reverse_file_id_mapping[to_rel] = id_from
        del self._reverse_file_id_mapping[from_rel]
        self._file_id_mapping_is_dirty = True

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

    def is_dirty(self):
        dirty = (
            self._natural_dict.is_dirty() if self._natural_dict is not None
            else False
        )
        for corpus in self._filetype_dicts:
            dirty = dirty or corpus.is_dirty()
        for corpus in self._file_id_dicts:
            dirty = dirty or corpus.is_dirty()
        dirty = dirty or self._file_id_mapping_is_dirty
        return dirty

    def close(self):
        """Update the corpus file iff the contents were modified."""
        if self.is_dirty():
            try:
                with _util.open_with_encoding(self._filename, mode='w') as f:
                    for corpus in self._filetype_dicts:
                        corpus.write(f)
                    for corpus in self._file_id_dicts:
                        corpus.write(f)
                    # Natural language dict goes at the end for readability...
                    # it is typically much bigger than the other dictionaries
                    self._natural_dict.write(f)
            except IOError as e:
                print("Warning: unable to write dictionary file '{}' "
                      '(reason: {})'.format(self._filename, e))

        if self._file_id_mapping_is_dirty:
            if self._relative_to is None:
                raise AssertionError("file ID mapping is dirty but " +
                                     "relative_to is None")

            # Build an OrderedDict sorted by first filename of id, so the
            # mapping file is more reader-friendly.  It will also be
            # more stable, so it will result in less churn if it's checked
            # into git.
            od = OrderedDict()
            copied_ids = set({})
            sorted_filenames = sorted(self._reverse_file_id_mapping)
            for fn in sorted_filenames:
                id = self._reverse_file_id_mapping[fn]
                if id in copied_ids:
                    continue
                copied_ids.add(id)
                od[id] = sorted(self._file_id_mapping[id])

            mapping_file = self._filename + ".fileids.json"
            try:
                with io.open(mapping_file, mode='w', encoding='utf-8') as mf:
                    # http://stackoverflow.com/questions/36003023/json-dump-failing-with-must-be-unicode-not-str-typeerror
                    json_str = json.dumps(od, ensure_ascii=False,
                                          indent=2, separators=(',', ': '))
                    if isinstance(json_str, str):
                        # Apply py2 workaround only on py2
                        if sys.version_info[0] == 2:
                            json_str = json_str.decode("utf-8")
                    mf.write(json_str)
                self._file_id_mapping_is_dirty = False
            except IOError as e:
                print("Warning: unable to write file ID mapping file '{0}' "
                      "(reason: {1})".format(mapping_file, e))

        # Since we add words only to this, not to any base corpora
        # file, there's nothing to do for the base files now.  But it
        # seems like good form to call close() on them since we've
        # "opened" them.  But be sure we won't actually end up writing
        # any changes out.
        for bc in self._base_corpora_files:
            if bc.is_dirty():
                raise AssertionError("_base_corpora_file is dirty")
            bc.close()

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
            self._file_id_dicts.append(corpus)
            self._file_ids[metadata] = corpus
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
            if metadata in self._file_ids:
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
