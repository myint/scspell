**scspell** is a spell checker for source code.  It does not try to be
particularly smart--rather, it does the simplest thing that can possibly
work:

    1. All alphanumeric strings (strings of letters, numbers, and
       underscores) are spell-checked tokens.
    2. Each token is split into one or more subtokens.  Underscores and
       digits always divide tokens, and capital letters will begin new
       subtokens.  In other words, ``some_variable`` and
       ``someVariable`` will both generate the subtoken list {``some``,
       ``variable``}.
    3. All subtokens longer than three characters are matched against a
       set of dictionaries, and a match failure prompts the user for
       action.  When matching against the included English dictionary,
       *prefix matching* is employed; this choice permits the use of
       truncated words like ``dict`` as subtokens.

When applied to code written in a modern programming language using
typical naming conventions, this algorithm will catch many errors
without an annoying false positive rate.

**scspell** matches subtokens against four distinct dictionaries:

    1. A read-only (American) English dictionary is provided with
       **scspell**.
    2. A programming language keyword dictionary is provided with
       **scspell**.  New keywords may be added to the dictionary,
       and a team of developers may share a common keyword dictionary.
    3. A custom dictionary is created at runtime for each user, so each
       user may exclude certain words without affecting other developers.
    4. A custom per-file dictionary is created for each user for each
       new file, so that special keywords may be excluded on a per-file
       basis.

Usage
=====

To begin the spell checker, run ::

    $ scspell source_file1 source_file2 ...

For each match failure, you will see output much like this::

    filename.c:27: Unmatched 'someMispeldVaraible' -> {mispeld, varaible}
    
In other words, the token "``someMispeldVaraible``" was found on line 27
of ``filename.c``, and it contains subtokens "``mispeld``" and
"``varaible``" which both failed the spell-checking algorithm.  You will
be prompted for an action to take:
    
    (i)gnore
        Skip to the next match failure, without taking any action.

    (I)gnore all
        Skip over this token every time it is encountered, for the
        remainder of this spell check session.
        
    (r)eplace
        Prompt the user for some text to use as a replacement for this
        token.

    (R)eplace all
        Prompt the user for some text to use as a replacement for this
        token, and replace every occurrence of the token until the end
        of the current file.

    (a)dd to dictionary
        Add one or more tokens to one of the dictionaries (see below).

    show (c)ontext
        Print out some lines of context surrounding this match failure.

If you accidentally select a replacement operation, enter an empty
string to cancel.

If you select the ``(a)dd to dictionary`` option, then you will be
prompted with the following options for every subtoken:

    (i)gnore
        Skip to the next subtoken, without taking any action.

    add to (c)ustom dictionary
        Adds this subtoken to your custom dictionary.

    add to per-(f)ile custom dictionary
        Adds this subtoken to your custom dictionary which is associated
        with the current file.

    add to (k)eyword dictionary
        Adds this subtoken to the programming language keyword
        dictionary (which may be shared with other developers).


Sharing a Keyword Dictionary
----------------------------

A team of developers working on the same source tree may wish to share a
common keyword dictionary.  You can set the location of a shared keyword
dictionary by executing ::

    $ scspell --set-keyword-dictionary=/path/to/dictionary_file.txt

The keyword dictionary is formatted as a simple newline-separated list of
words, so it can easily be managed by a version control system if
desired.

The current keyword dictionary can be saved to a file by executing ::

    $ scspell --export-keyword-dictionary=/path/to/dictionary_file.txt


Installation
============

If you have `setuptools <http://pypi.python.org/pypi/setuptools>`_
installed, then you can install **scspell** via::

    $ easy_install scspell

Alternatively, download and unpack the source archive, switch to the
archive root directory, and run the installation script::

    $ python setup.py install

On a UNIX-like system, you may need to use ``sudo`` if installing to a
directory that requires root privileges::

    $ sudo python setup.py install


License
=======

**scspell** is Free Software, licensed under Version 2 of the GNU General
Public License; see ``COPYING.txt`` for details.

The English dictionary distributed with scspell is derived from the
`SCOWL word lists <http://wordlist.sourceforge.net>`_ .  See
``SCOWL-LICENSE.txt`` for the myriad licenses that apply to that file.


Bugs, etc.
============

**scspell** is `hosted on Launchpad <http://launchpad.net/scspell>`_; 
this would be a great place to file bug reports and feature requests or
track development via `bzr <http://bazaar-vcs.org>`_.

If that's not your style, just send an email to
Paul Pelzl <pelzlpj at gmail dot com> .
