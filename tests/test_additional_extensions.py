import os

from scspell import spell_check


def test_additional_extensions():
    source_filenames = [os.path.join(
        os.path.dirname(__file__), 'fileidmap', 'custom.ext')]
    result = spell_check(source_filenames, report_only=True)
    assert result is False

    result = spell_check(
        source_filenames, report_only=True,
        additional_extensions=[('.ext', 'Python')])
    assert result is True
