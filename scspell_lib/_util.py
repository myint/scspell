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
_util -- utility functions which may be useful across the source tree.
"""

# Settings for this session
VERBOSITY_NORMAL = 1
VERBOSITY_DEBUG  = 2
VERBOSITY_MAX    = VERBOSITY_DEBUG
SETTINGS = {'verbosity' : VERBOSITY_NORMAL}

def mutter(level, text):
    """Print text to the console, if the level is not higher than the
    current verbosity setting."""
    if level <= SETTINGS['verbosity']:
        print text


def set_verbosity(value):
    """Set the verbosity level to a given integral value.  The constants
    VERBOSITY_* are good choices."""
    SETTINGS['verbosity'] = value


# scspell-id: b114984a-c7aa-40a8-9a53-b54fb6a52582

