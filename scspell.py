#!/usr/bin/env python
"""
scspell -- an interactive, conservative spell-checker for source code.
"""

import sys
from optparse import OptionParser
from scspell.scspell import spell_check


VERSION = '0.9'


parser = OptionParser(usage="""\
%prog [options] <source files>

Performs spell-checking on all of the <source files>.  Tokens are matched
against four separate dictionaries:

    1) the (American) English dictionary distributed with scspell
    2) a programming language "keyword" dictionary, distributed with scspell
        and updated by users
    3) a "custom" dictionary, created from scratch for each user
    4) a "custom per-file" dictionary, created from scratch for each user
        for each new file

The spell-check algorithm locates alphanumeric tokens and splits them into
alphabetical subtokens.  CamelCase-style tokens are split into subtokens along
capital-letter boundaries.  For example, the token "someVariable__Name104"
generates the subtoken list {some, variable, name}.  Each subtoken is
individually matched against the dictionaries, and a match failure will
prompt the user for action.  The possible actions are

    (N)ext token:           find the next token which fails spell-check
    (I)gnore all:           ignore additional instances of this token for the
                                remainder of the session
    (A)dd to dictionary:    add one or more subtokens to one of the dictionaries
    show (C)ontext:         print out some lines of source surrounding this token

If "(A)dd to dictionary" is selected, then the following actions may be taken
for each subtoken:

    (N)ext subtoken:        no action--move on to the next subtoken
    (C)ustom dictionary:    adds this subtoken to the user's general-purpose
                                custom dictionary
    per-(F)ile dictionary:  adds this subtoken to the user's custom dictionary
                                associated with the current file
    (K)eyword dictionary:   adds this subtoken to the keyword dictionary,
                                which may be shared with other users

The matching algorithm is designed to overlook common abbreviations used
in programming.  Subtokens shorter than four characters are always ignored,
and a subtoken need only be a prefix of an English word to match that word.
""", version = """\
scspell v%s
Copyright (C) 2009 Paul Pelzl

scspell comes with ABSOLUTELY NO WARRANTY.  This is free software, and
you are welcome to redistribute it under certain conditions; for details,
see the COPYING file distributed with the program.
""" % VERSION)


(opts, args) = parser.parse_args()
if len(args) < 1:
    parser.print_help()
    sys.exit(1)
spell_check(args)
   

