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
corpus.py

Defines methods for storing dictionaries and performing searches against them.
"""


from __future__ import with_statement
import os, sys
from bisect import bisect_left
from _util import *


# String identifying natural language dictionary
CATEGORY_NATURAL = 'NATURAL'


class ParsingError(Exception):
    """An error occurred when parsing the dictionary file."""


class Corpus(object):
    """Base class for various types of (textual) dictionary-like objects."""

    def __init__(self, name, extensions):
        self._dirty      = False
        self._name       = name
        self._extensions = extensions

    def _mark_dirty(self):
        self._dirty = True

    def _mark_clean(self):
        self._dirty = False

    def is_dirty(self):
        return self._dirty

    def get_name(self):
        """Return the name of this Corpus."""
        return self._name

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
        """Writes the corpus header to f, a file-like object."""
        f.write(self.get_name() + ': ' + ', '.join(self._extensions) + '\n')


class ExactMatchCorpus(Corpus):
    """A token matches against an ExactMatchCorpus iff it is present in the corpus."""

    def __init__(self, name, extensions, tokens):
        """Construct an instance from a sequence of tokens, giving it
        the specified category name and list of extensions.
        """
        Corpus.__init__(self, name, extensions)
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
        self._mark_clean()


class PrefixMatchCorpus(Corpus):
    """A token matches against a PrefixMatchCorpus iff the token is a prefix of
    any item in the corpus.
    """

    def __init__(self, name, extensions, tokens):
        """Construct an instance from a sequence of tokens, giving it
        the specified category name and list of extensions.
        """
        Corpus.__init__(self, name, extensions)
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
        if insertion_point >= len(self._tokens) or self._tokens[insertion_point] != token:
            self._tokens.insert(insertion_point, token)
            self._mark_dirty()

    def write(self, f):
        """Write the contents of this Corpus to f, a file-like object."""
        self._write_header(f)
        for token in self._tokens:
            f.write(token + '\n')
        self._mark_clean()


class CorporaFile(object):
    """The CorporaFile manages a single file containing multiple corpora."""

    def __init__(self, filename):
        """Construct an instance from the file with the given filename."""
        self._filename = filename
        try:
            with open(filename, 'rb') as f:
                lines = [line.strip('\r\n') for line in f.readlines()]
            return self._parse(lines)
        except IOError, e:
            print 'Warning: unable to read dictionary file "%s". (Reason: %s)' % (filename, str(e))
            print 'Continuing with empty dictionary.\n'
            self._natural     = PrefixMatchCorpus([])
            self._programming = []
        except ParsingError, e:
            print 'Error while parsing dictionary file "%s": %s' % (filename, str(e))
            sys.exit(1)

    def match(self, token, filename):
        """Return true if the token matches any of the applicable corpora."""
        if self._natural.match(token):
            return True
        (_, ext) = os.path.splitext(filename)
        try:
            corpus = self._extensions[ext]
            mutter(VERBOSITY_DEBUG, '(Matching against filetype "%s".)' % corpus.get_name())
            return corpus.match(token)
        except KeyError:
            mutter(VERBOSITY_DEBUG, '(No filetype match for extension "%s".)' % ext)
            return False

    def add_natural(self, token):
        """Add the token to the natural language corpus."""
        self._natural.add(token)

    def add_programming(self, token, filename):
        """Add the token to a programming language-specific corpus.

        Returns True if the add was successful, False if there is no corpus
        with a matching filename extension.
        """
        (_, ext) = os.path.splitext(filename)
        try:
            corpus = self._extensions[ext]
            mutter(VERBOSITY_DEBUG, '(Adding to filetype "%s".)' % corpus.get_name())
            corpus.add(token)
            return True
        except KeyError:
            mutter(VERBOSITY_DEBUG, '(No filetype match for extension "%s".)' % ext)
            return False
        
    def close(self):
        """Update the corpus file iff the contents were modified."""
        dirty = self._natural.is_dirty() if self._natural is not None else False
        for corpus in self._programming:
            dirty = dirty or corpus.is_dirty()
        if dirty:
            try:
                with open(self._filename, 'wb') as f:
                    self._natural.write(f)
                    for corpus in self._programming:
                        corpus.write(f)
            except IOError, e:
                print ('Warning: unable to write dictionary file "%s". (Reason: %s)' %
                        (filename, str(e)))

    def _parse(self, lines):
        """Parses the lines into a set of corpora."""
        # Empty defaults
        self._natural     = None
        self._programming = []
        self._extensions  = {}

        offset = 0
        while offset < len(lines):
            offset = self._parse_corpus(lines, offset)
    
    def _parse_corpus(self, lines, offset):
        """Parses a single corpus starting at offset within lines."""
        category, extensions = self._parse_header_line(lines[offset], offset+1)
        if category == '':
            raise ParsingError('Dictionary header on line %u must have nonempty category name.' %
                    offset+1)
        elif category == CATEGORY_NATURAL:
            if self._natural is not None:
                raise ParsingError('Duplicate dictionary category "%s" on line %u.' %
                        (CATEGORY_NATURAL, offset+1))
            if extensions != []:
                raise ParsingError('Dictionary category "%s" on line %u should have no extensions.' %
                        (CATEGORY_NATURAL, offset+1))
            (offset, tokens) = self._read_corpus_tokens(offset, lines)
            self._natural = PrefixMatchCorpus(CATEGORY_NATURAL, extensions, tokens)
            return offset
        else:
            if extensions == []:
                extensions = ['']
            if category in [corpus.get_name() for corpus in self._programming]:
                raise ParsingError('Duplicate category name "%s" in header on line %u.' %
                        (category, offset+1))
            for ext in extensions:
                if self._extensions.has_key(ext):
                    raise ParsingError('Duplicate extension "%s" in header on line %u.' %
                        (ext, offset+1))
            (offset, tokens) = self._read_corpus_tokens(offset, lines)
            corpus = ExactMatchCorpus(category, extensions, tokens)
            self._programming.append(corpus)
            for ext in extensions:
                self._extensions[ext] = corpus
            return offset

    def _parse_header_line(self, line, line_num):
        """Parse a dictionary header line.

        Headers take the form

            <category>: <comma-separated list of extensions>

        The return value is the tuple (category, extension list).
        """
        try:
            (raw_category, raw_extensions) = line.split(':')
        except ValueError:
            raise ParsingError('Syntax error in header on line %u.' % line_num)

        category   = raw_category.strip()
        extensions = [ext.strip() for ext in raw_extensions.split(',')]
        extensions = [ext for ext in extensions if ext != '']
        for ext in extensions:
            if not ext.startswith('.'):
                raise ParsingError('Extension "%s" on line %u does not begin with a period.' % 
                        (ext, line_num))
        return category, extensions

    def _read_corpus_tokens(self, offset, lines):
        """Read the set of tokens for the corpus which begins at the given offset.

        Returns the tuple (next offset, tokens).
        """
        tokens = []
        for i, line in enumerate(lines[offset+1:]):
            if ':' in line:
                return (offset + i + 1, tokens)
            else:
                tokens.append(line)
        return len(lines), tokens

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()
        return False

