#!/usr/bin/env python

import sys

import scspell


if __name__ == '__main__':
    try:
        sys.exit(scspell.main())
    except KeyboardInterrupt:
        sys.exit(2)
