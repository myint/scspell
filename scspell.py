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

"""scspell -- an interactive, conservative spell-checker for source code."""

from __future__ import absolute_import
from __future__ import print_function

import optparse
import sys
import uuid

import scspell


def main():
    parser = optparse.OptionParser(usage="""\
    %prog [options] [source files]

    Performs spell checking on all of the [source files].""",
                                   version="""\
    %%prog v%s
    Copyright (C) 2009 Paul Pelzl

    %%prog comes with ABSOLUTELY NO WARRANTY.  This is free software, and
    you are welcome to redistribute it under certain conditions; for details,
    see COPYING.txt as distributed with the program.
    """ % scspell.__version__)

    spell_group = optparse.OptionGroup(parser, 'Spell Checking')
    spell_group.add_option(
        '--override-dictionary', dest='override_filename',
        help='set location of dictionary to FILE, for current session only',
        metavar='FILE', action='store')
    spell_group.add_option('--report-only', dest='report', action='store_true',
                           help='Non-interactive report of spelling errors')
    parser.add_option_group(spell_group)

    config_group = optparse.OptionGroup(parser, 'Configuration')
    config_group.add_option(
        '--set-dictionary', dest='dictionary',
        help='permanently set location of dictionary to FILE', metavar='FILE',
        action='store')
    config_group.add_option(
        '--export-dictionary', dest='export_filename',
        help='export current dictionary to FILE', metavar='FILE',
        action='store')
    parser.add_option_group(config_group)

    parser.add_option('-i', '--gen-id', dest='gen_id', action='store_true',
                      help='generate a unique file-id string')
    parser.add_option('-D', '--debug', dest='debug', action='store_true',
                      help='print extra debugging information')

    (opts, files) = parser.parse_args()
    if opts.debug:
        scspell.set_verbosity(scspell.VERBOSITY_MAX)

    if opts.gen_id:
        print('scspell-id: %s' % str(uuid.uuid1()))
    elif opts.dictionary is not None:
        scspell.set_dictionary(opts.dictionary)
    elif opts.export_filename is not None:
        scspell.export_dictionary(opts.export_filename)
        print("Exported dictionary to '{}'".format(opts.export_filename),
              file=sys.stderr)
    elif len(files) < 1:
        parser.error('No files specified')
    else:
        okay = scspell.spell_check(files, opts.override_filename, opts.report)
        return 0 if okay else 1


if __name__ == '__main__':
    sys.exit(main())
