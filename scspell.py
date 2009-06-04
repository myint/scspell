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


import sys
from optparse import OptionParser
import scspell_lib


parser = OptionParser(usage="""\
%prog [options] <source files>

Performs spell-checking on all of the <source files>.""",
version = """\
%%prog v%s
Copyright (C) 2009 Paul Pelzl

%%prog comes with ABSOLUTELY NO WARRANTY.  This is free software, and
you are welcome to redistribute it under certain conditions; for details,
see COPYING.txt as distributed with the program.
""" % scspell_lib.VERSION)
parser.add_option('--set-keyword-dictionary', dest='keyword_dict',
        help='set location of keyword dictionary to FILE', metavar='FILE',
		action='store')
parser.add_option('--export-keyword-dictionary', dest='keyword_export_filename',
        help='export current keyword dictionary to FILE', metavar='FILE',
		action='store')


(opts, args) = parser.parse_args()
if opts.keyword_dict is not None:
	scspell_lib.set_keyword_dict(opts.keyword_dict)
elif opts.keyword_export_filename is not None:
	scspell_lib.export_keyword_dict(opts.keyword_export_filename)
	print 'Exported keyword dictionary to "%s".' % opts.keyword_export_filename
elif len(args) < 1:
    parser.print_help()
    sys.exit(1)
else:
	scspell_lib.spell_check(args)
   

