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

import scspell


def main():
    parser = argparse.ArgumentParser(description=__doc__, prog='scspell')

    dict_group = parser.add_argument_group("dictionary file management")
    spell_group = parser.add_argument_group("spell-check control")

    spell_group.add_argument(
        '--report-only', dest='report', action='store_true',
        help='non-interactive report of spelling errors')
    spell_group.add_argument(
        '--no-c-escapes', dest='c_escapes',
        action='store_false', default=True,
        help="treat \\label as label, for e.g. LaTeX")

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
        '--relative-to', dest='relative_to',
        help='use file paths relative to here in file ID map; '
             'this is required to enable use of the fileid map',
        action='store')
    dict_group.add_argument(
        '-i', '--gen-id', dest='gen_id', action='store_true',
        help='generate a unique file-id string')
    dict_group.add_argument(
        '--merge-fileids', nargs=2,
        metavar=('FROM_ID', 'TO_ID'),
        help='merge these two file IDs, keeping TO_ID and discarding FROM_ID; '
             'combine their word lists in the dictionary, and the filenames '
             'associated with them in the fileid map; TO_ID and FROM_ID may '
             'be given as fileids, or as filenames in which case the fileids '
             'corresponding to those files are operated on; does NOT look '
             'for or consider any fileids embedded in to-be-spell-checked '
             'files; if your filenames look like fileids, do it by hand')
    dict_group.add_argument(
        '--rename-file', nargs=2,
        metavar=('FROM_FILE', 'TO_FILE'),
        help='inform scspell that FROM_FILE has been renamed TO_FILE; '
             'if an entry in the fileid mapping references FROM_FILE, it will '
             'be modified to reference TO_FILE instead')
    dict_group.add_argument(
        '--delete-files', action='store_true', default=False,
        help='inform scspell that the listed files have been deleted; all '
             'fileid mappings for the files will be removed; if all uses of '
             'that fileid have been removed, the corresponding file-private '
             'dictionary will be removed; this will not spell check the '
             'files')

    parser.add_argument(
        '-D', '--debug', dest='debug', action='store_true',
        help='print extra debugging information')
    parser.add_argument(
        '--version', action='version',
        version='%(prog)s ' + scspell.__version__)
    parser.add_argument(
        'files', nargs='*', help='files to check')

    args = parser.parse_args()

    if args.debug:
        scspell.set_verbosity(scspell.VERBOSITY_MAX)

    if args.gen_id:
        print('scspell-id: %s' % scspell.get_new_fileid())
    elif args.dictionary is not None:
        scspell.set_dictionary(args.dictionary)
    elif args.export_filename is not None:
        scspell.export_dictionary(args.export_filename)
        print("Exported dictionary to '{}'".format(args.export_filename),
              file=sys.stderr)
    elif args.merge_fileids is not None:
        scspell.merge_fileids(args.merge_fileids[0], args.merge_fileids[1],
                              args.override_filename, args.relative_to)
    elif args.rename_file is not None:
        scspell.rename_file(args.rename_file[0], args.rename_file[1],
                            args.override_filename, args.relative_to)
    elif args.delete_files:
        if len(args.files) < 1:
            parser.error('No files specified for delete')
        scspell.delete_files(args.files,
                             args.override_filename, args.relative_to)
    elif len(args.files) < 1:
        parser.error('No files specified')
    else:
        okay = scspell.spell_check(args.files,
                                   args.override_filename,
                                   args.relative_to,
                                   args.report,
                                   args.c_escapes)
        return 0 if okay else 1


if __name__ == '__main__':
    sys.exit(main())
