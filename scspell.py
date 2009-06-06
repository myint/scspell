#!/usr/bin/env python
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
scspell -- an interactive, conservative spell-checker for source code.
"""


import sys, uuid
from optparse import OptionParser
import scspell_lib


parser = OptionParser(usage="""\
%prog [options] [source files]

Performs spell checking on all of the [source files].""",
version = """\
%%prog v%s
Copyright (C) 2009 Paul Pelzl

%%prog comes with ABSOLUTELY NO WARRANTY.  This is free software, and
you are welcome to redistribute it under certain conditions; for details,
see COPYING.txt as distributed with the program.
""" % scspell_lib.VERSION)
parser.add_option('--override-dictionary', dest='override_filename',
        help='set location of dictionary to FILE, for current session only',
        metavar='FILE', action='store')
parser.add_option('--set-dictionary', dest='dictionary',
        help='permanently set location of dictionary to FILE', metavar='FILE',
		action='store')
parser.add_option('--export-dictionary', dest='export_filename',
        help='export current dictionary to FILE', metavar='FILE',
		action='store')
parser.add_option('-i', '--gen-id', dest='gen_id', action='store_true',
        help='generate a unique file-id string')
parser.add_option('-D', '--debug', dest='debug', action='store_true',
        help='print extra debugging information')


(opts, args) = parser.parse_args()
if opts.debug:
    scspell_lib.set_verbosity(scspell_lib.VERBOSITY_MAX)

if opts.gen_id:
    print 'scspell-id: %s' % str(uuid.uuid1())
elif opts.dictionary is not None:
	scspell_lib.set_dictionary(opts.dictionary)
elif opts.export_filename is not None:
	scspell_lib.export_dictionary(opts.export_filename)
	print 'Exported dictionary to "%s".' % opts.export_filename
elif len(args) < 1:
    parser.print_help()
    sys.exit(1)
else:
	scspell_lib.spell_check(args, opts.override_filename)
   

# scspell-id: 285634e7-e5de-4e95-accc-ba639be2834e

