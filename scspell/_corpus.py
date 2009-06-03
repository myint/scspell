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
from bisect import bisect_left


class Corpus(object):
    """Base class for various types of (textual) dictionary-like objects."""

    def __init__(self):
        self._dirty = False

    def _mark_dirty(self):
        self._dirty = True

    def _mark_clean(self):
        self._dirty = False

    def _is_dirty(self):
        return self._dirty

    def match(self, word):
        """Returns True if the word matches an entry in this Corpus.
        The matching method is Corpus-specific.
        """
        raise NotImplementedError

    def add(self, word):
        """Adds the specified word to this Corpus."""
        raise NotImplementedError

    def close(self):
        """Closes this corpus, saving its state as appropriate."""
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class FileStoredCorpus(Corpus):
    """A FileStoredCorpus is a Corpus stored as a list of words in an ordinary file."""

    def __init__(self, filename):
        """Loads the word list from the specified file."""
        Corpus.__init__(self)
        self._filename = filename
        try:
            with open(filename, 'rb') as f:
                self._words = [word.strip('\r\n') for word in f.readlines()]
                # The word list *should* be sorted already, but someone could have
                # corrupted it...
                self._words.sort()
        except IOError:
            print 'Warning: can\'t read dictionary file "%s".' % filename
            print 'Continuing with empty dictionary.'
            print
            self._words = []


    def match(self, word):
        """Returns True if the word is present in this Corpus."""
        insertion_point = bisect_left(self._words, word)
        if insertion_point < len(self._words):
            return self._words[insertion_point] == word
        else:
            return False

    def add(self, word):
        """Adds the specified word to this Corpus."""
        insertion_point = bisect_left(self._words, word)
        if insertion_point >= len(self._words) or self._words[insertion_point] != word:
            self._words.insert(insertion_point, word)
            self._mark_dirty()

    def close(self):
        """Closes this corpus, writing back any updates."""
        if self._is_dirty():
            try:
                with open(self._filename, 'wb') as f:
                    f.writelines([w + '\n' for w in self._words])
                self._mark_clean()
            except IOError:
                print 'Warning: unable to write dictionary file "%s".' % self._filename


class SetCorpus(Corpus):
    """A SetCorpus is a Corpus that uses matching by equality."""

    def __init__(self):
        Corpus.__init__(self)
        self._words = set()

    def match(self, word):
        """Returns True if the word is present in this Corpus."""
        return word in self._words

    def add(self, word):
        """Adds the specified word to this Corpus."""
        if word not in self._words:
            self._words.add(word)
            self._mark_dirty()

    def close(self):
        pass


class DictStoredSetCorpus(SetCorpus):
    """A DictStoredCorpus is a Corpus stored as a set() in a dictionary entry."""

    def __init__(self, db, key):
        """Loads the corpus from dictionary <db>, using the <key> for lookup."""
        Corpus.__init__(self)
        self._db  = db
        self._key = key
        try:
            self._words = db[key]
        except KeyError:
            self._words = set()

    def close(self):
        """Closes this corpus, writing back any updates."""
        if self._is_dirty():
            self._db[self._key] = self._words
            self._mark_clean()


class PrefixMatchingCorpus(FileStoredCorpus):
    """A PrefixMatchingCorpus is based on a sorted list of words.  A
    token matches against the word list if the token is a prefix of any
    word in the list."""

    def match(self, word):
        """Returns True if the word is a prefix of any word in this
        dictionary.
        """
        insertion_point = bisect_left(self._words, word)
        if insertion_point < len(self._words):
            return self._words[insertion_point].startswith(word)
        else:
            return False


