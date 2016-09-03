#!/usr/bin/env python

import ast

import setuptools


def get_version():
    """Return version string."""
    with open('scspell/__init__.py') as input_file:
        for line in input_file:
            if line.startswith('__version__'):
                return ast.parse(line).body[0].value.s


with open('README.rst', 'r') as readme_file:
    description = readme_file.read()


setuptools.setup(
    name='scspell3k',
    version=get_version(),
    description='A conservative interactive spell checker for source code.',
    long_description=description,
    url='https://github.com/myint/scspell',
    packages=['scspell'],
    entry_points={
        'console_scripts': ['scspell = scspell:main']},
    package_data={'scspell': ['data/*']},
    license='GPL 2',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development',
        'Topic :: Text Processing :: Linguistic',
        'Topic :: Utilities'],
    platforms=['any']
)
