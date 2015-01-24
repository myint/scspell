scspell
=======

.. image:: https://travis-ci.org/myint/scspell.svg?branch=master
    :target: https://travis-ci.org/myint/scspell
    :alt: Build status

**scspell** is a spell checker for source code. This is an unofficial fork (of
https://launchpad.net/scspell) that runs on both Python 2 and 3.

**scspell** does not try to be particularly smart--rather, it does the simplest
thing that can possibly work:

    1. All alphanumeric strings (strings of letters, numbers, and
       underscores) are spell-checked tokens.
    2. Each token is split into one or more subtokens. Underscores and digits
       always divide tokens, and capital letters will begin new subtokens. In
       other words, ``some_variable`` and ``someVariable`` will both generate
       the subtoken list {``some``, ``variable``}.
    3. All subtokens longer than three characters are matched against a set of
       dictionaries, and a match failure prompts the user for action. When
       matching against the included English dictionary, *prefix matching* is
       employed; this choice permits the use of truncated words like ``dict``
       as valid subtokens.

When applied to code written in most popular programming languages while using
typical naming conventions, this algorithm will usually catch many errors
without an annoying false positive rate.

In an effort to catch more spelling errors, **scspell** is able to check each
file against a set of dictionary words selected *specifically for that file*. Up
to three different sub-dictionaries may be searched for any given file:

    1. A natural language dictionary. (**scspell** provides an American
       English dictionary as the default.)
    2. A programming language-specific dictionary, intended to contain
       oddly-spelled keywords and APIs associated with that language.
       (**scspell** provides small default dictionaries for a number of popular
       programming languages.)
    3. A file-specific dictionary, intended to contain uncommon strings which
       are not likely to be found in more than a handful of unique files.

Usage
-----

To begin the spell checker, run ::

    $ scspell source_file1 source_file2 ...

For each spell check failure, you will see output much like this::

    filename.c:27: Unmatched 'someMispeldVaraible' -> {mispeld, varaible}

In other words, the token "``someMispeldVaraible``" was found on line 27
of ``filename.c``, and it contains subtokens "``mispeld``" and
"``varaible``" which both failed the spell-checking algorithm. You will
be prompted for an action to take:

    (i)gnore
        Skip to the next unmatched token, without taking any action.

    (I)gnore all
        Skip over this token every time it is encountered, for the
        remainder of this spell check session.

    (r)eplace
        Enter some text to use as a replacement for this token, and replace
        only the token at this point in the file.

    (R)eplace all
        Enter some text to use as a replacement for this token, and replace
        every occurrence of the token until the end of the current file.

    (a)dd to dictionary
        Add one or more tokens to one of the dictionaries (see below).

    show (c)ontext
        Print out some lines of context surrounding the unmatched token.

If you accidentally select a replacement operation, enter an empty
string to cancel.

If you select the ``(a)dd to dictionary`` option, then you will be
prompted with the following options for every subtoken:

    (b)ack
        Return to the previous menu, without taking any action.

    (i)gnore
        Skip to the next subtoken, without taking any action.

    add to (p)rogramming language dictionary
        Add this subtoken to the dictionary associated with the
        programming language of the current file. **scspell** uses the
        file extension to determine the language, so you will only
        see this option for files which have an extension.

    add to (f)ile-specific dictionary
        Add this subtoken to the dictionary associated with the
        current file. **scspell** identifies unique files by scanning
        for an embedded ID string, so you will only see this option
        for files which have such an ID. See `Creating File IDs`
        for details.

    add to (n)atural language dictionary
        Add this subtoken to the natural language dictionary.

Creating File IDs
-----------------

If you would like **scspell** to be able to uniquely identify a file, thus
enabling the creation of a file-specific dictionary, then you must insert a
unique ID somewhere in the contents of that file. **scspell** will scan each
file for a string of the following form::

    scspell-id: <unique ID>

The unique ID must consist only of letters, numbers, underscores, and dashes.
**scspell** can generate suitable unique ID strings using the ``--gen-id`` option::

    $ scspell --gen-id
    scspell-id: e497803c-523a-11de-ae42-0017f2ee0f37

(Most likely you will want to place a file's unique ID inside a source code comment.)

Sharing a Dictionary
--------------------

A team of developers working on the same source tree may wish to share a common
dictionary. You can permanently set the location of a shared dictionary by
executing ::

    $ scspell --set-dictionary=/path/to/dictionary_file.txt

The dictionary is formatted as a simple newline-separated list of words, so it
can easily be managed by a version control system if desired.

The current dictionary can be saved to a file by executing ::

    $ scspell --export-dictionary=/path/to/output_file.txt

You can also override the dictionary location for a single spell check session,
by using the ``--override-dictionary`` option::

    $ scspell --override-dictionary=/path/to/dictionary_file.txt source_file1 ...

Installation
------------

Install **scspell** via pip::

    $ pip install scspell3k

Alternatively, download and unpack the source archive, switch to the
archive root directory, and run the installation script::

    $ python setup.py install

On a UNIX-like system, you may need to use ``sudo`` if installing to a
directory that requires root privileges::

    $ sudo python setup.py install

License
-------

**scspell** is Free Software, licensed under Version 2 of the GNU General
Public License; see ``COPYING.txt`` for details.

The English dictionary distributed with scspell is derived from the
`SCOWL word lists <http://wordlist.sourceforge.net>`_ . See
``SCOWL-LICENSE.txt`` for the myriad licenses that apply to that dictionary.
