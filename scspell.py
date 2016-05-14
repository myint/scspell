#!/usr/bin/env python

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

"""An interactive, conservative spell-checker for source code."""

from __future__ import absolute_import
from __future__ import print_function

import argparse
import sys
import uuid

import scspell


def main():
    parser = argparse.ArgumentParser(description=__doc__, prog='scspell')

    parser.add_argument(
        '--override-dictionary', dest='override_filename',
        help='set location of dictionary to FILE, for current session only',
        metavar='FILE', action='store')
    parser.add_argument('--report-only', dest='report', action='store_true',
                        help='non-interactive report of spelling errors')
    parser.add_argument(
        '--set-dictionary', dest='dictionary',
        help='permanently set location of dictionary to FILE', metavar='FILE',
        action='store')
    parser.add_argument(
        '--export-dictionary', dest='export_filename',
        help='export current dictionary to FILE', metavar='FILE',
        action='store')
    parser.add_argument('-i', '--gen-id', dest='gen_id', action='store_true',
                        help='generate a unique file-id string')
    parser.add_argument('--no-c-escapes', dest='c_escapes',
                        action='store_false', default=True,
                        help="treat \\label as label, for e.g. LaTeX")
    parser.add_argument('-D', '--debug', dest='debug', action='store_true',
                        help='print extra debugging information')
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + scspell.__version__)
    parser.add_argument('files', nargs='+', help='files to check')

    args = parser.parse_args()

    if args.debug:
        scspell.set_verbosity(scspell.VERBOSITY_MAX)

    if args.gen_id:
        print('scspell-id: %s' % str(uuid.uuid1()))
    elif args.dictionary is not None:
        scspell.set_dictionary(args.dictionary)
    elif args.export_filename is not None:
        scspell.export_dictionary(args.export_filename)
        print("Exported dictionary to '{}'".format(args.export_filename),
              file=sys.stderr)
    elif len(args.files) < 1:
        parser.error('No files specified')
    else:
        okay = scspell.spell_check(args.files,
                                   args.override_filename,
                                   args.report,
                                   args.c_escapes)
        return 0 if okay else 1


if __name__ == '__main__':
    sys.exit(main())
