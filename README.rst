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
        current file. You will see this option only for files which
        have such an embedded ID or which have an entry in the file ID
        mapping.  See `Creating File IDs`_ for details.

    add to (N)ew file-specific dictionary
        Create a new file ID for the current file, record the new
        file ID in the file ID mapping, and add this subtoken to a new
        file-specific dictionary associated with that file ID.  You will
        see this option only for files which have neither an embedded ID nor
        an entry in the file ID mapping, and only if the ``--relative-to``
	option is given.  See `Creating File IDs`_ for details.

    add to (n)atural language dictionary
        Add this subtoken to the natural language dictionary.


Spell-checking Options
----------------------

--report-only\ 
 This option causes **scspell** to report to stderr a report of the
 subtokens that it considers to be in error, instead of offering the
 interactive menu described above.  For each subtoken, the report
 includes the filename, line number, and full token.  **scspell** will
 exit with an exit code of 1 if any errors are found, or 0 if the run
 was clean.

 The format of the reported errors is different than the interactive
 mode reports them.  With ``--report-only``, the above one would appear
 like this::

    filename.c:27: 'mispeld', 'varaible' were not found in the dictionary (from token 'someMispeldVaraible')


--no-c-escapes\ 
 By default, **scspell** treats files as if they contain C-style
 character escapes.  That is, given ``printf("Hello\nworld.")``, it will
 consider the tokens "``hello``" and "``world``", not "``nworld``".

 The ``--no-c-escapes`` option causes **scspell** to not treat ``\`` as a
 special character, for e.g. LaTeX files where you might write
 ``\Alpha\beta\gamma\delta``.  Without this option, **scspell** would
 see the tokens "``lpha``", "``eta``", "``amma``", and "``elta``".


Creating File IDs
-----------------

If you would like **scspell** to be able to uniquely identify a file,
thus enabling the creation of a file-specific dictionary, then
**scspell** must be able to find a file ID to identify both the file
an the file-specific dictionary.  There are two ways **scspell** can
find the file ID:

1. The file ID may be embedded directly in the file, using a string of
   the following form::

      scspell-id: <unique ID>

2. An entry in the file ID mapping file ties a filename to a file ID.

The unique ID must consist only of letters, numbers, underscores, and dashes.
**scspell** can generate suitable unique ID strings using the ``--gen-id`` option::

    $ scspell --gen-id
    scspell-id: e497803c-523a-11de-ae42-0017f2ee0f37

(Most likely you will want to place a file's unique ID inside a source code comment.)

During interactive use, the ``(a)dd to dictionary`` -> ``add to (N)ew
file-specific dictionary`` option will create a new File ID for the
current file, and add it to the file ID mapping file.


--relative-to RELATIVE_TO\ 
 The filenames stored in the file ID mapping are relative paths.  This
 option specifies what they're relative to.  If this option is not
 specified, the file ID mapping will not be consulted, and the ``add to (N)ew
 file-specific dictionary`` option will not be offered.



Managing File IDs
-----------------

These options direct **scspell** to manipulate the file ID mapping.
(These can all be accomplished by editing the file ID mapping
manually).  These have no effect on file IDs embedded in files.

--rename-file FROM_FILE TO_FILE
   Changes the filename that a File ID maps to.  After renaming a file
   that has a file-specific dictionary and an entry in the file ID
   mapping, you can use this option to have the entry "follow" the file.

--delete-files\ 
   Remove filenames from the file ID mapping.  If it was the only
   filename for a given File ID, removes the File ID from the mapping and
   its wordlist from the dictionary.

--merge-file-ids FROM_ID TO_ID
  Combines the file-specific dictionaries referenced by the two File
  IDs.  All words from FROM_IDs list are moved to TO_IDs.  The FROM_ID
  File ID is removed from the mapping, and any files using it are
  changed to use TO_ID.  Either FROM_ID or TO_ID may be given as a filename
  instead, in which case that file's File ID is used for that parameter.


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

--base-dict BASE_DICT\
   A *base dictionary* is consulted for its words, but is not modified
   at runtime.  By using

    $ scspell --base-dict ~/.dict --override-dictionary proj/.dict source...

   words added at runtime will be added to ``proj/.dict``, and
   ``~/.dict`` will be left alone.  This way ``proj/.dict`` may be
   limited only to the words added for ``proj/``.  This may be more
   convenient when ``proj/.dict`` is committed to source control and
   shared by many users.

--use-builtin-base-dict\
   Use the dictionary file shipped with scspell as a base dictionary.

--filter-out-base-dicts\
   Read the dictionary specified by the normal dictionary selection
   options, called the ``project dict`` here.  Read the base
   dictionaries specified by the base-dict options.  Remove from the
   project dict all the words from the base dicts, and write the
   project dict back out.

   This may be useful when a project dict has been generated with an
   older version of **scspell** that did not support base dicts.


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
