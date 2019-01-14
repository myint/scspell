import os

from scspell import Report
from scspell import spell_check


def test_additional_extensions():
    source_filenames = [os.path.join(
        os.path.dirname(__file__), 'fileidmap', 'inputfile.txt')]
    report = Report(('soem', 'other'))
    result = spell_check(source_filenames, report_only=report)
    assert result is False

    # 'other' was not found in the input
    assert report.found_known_words == {'soem'}
    assert report.unknown_words == {'wrods', 'finially'}
