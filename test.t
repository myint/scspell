Test scspell.

    $ SCSPELL="$TESTDIR/scspell.py --report-only"

Run once in case .scspell is not yet created.

    $ echo 'ignore' > ignore.txt
    $ $SCSPELL ignore.txt >& /dev/null

Test spelling mistake.

    $ echo 'This is blabbb.' > bad.txt
    $ $SCSPELL bad.txt
    bad.txt:1: 'blabbb' not found in dictionary (from token 'blabbb')

Test okay file.

    $ echo 'This is okay.' > good.txt
    $ $SCSPELL good.txt
