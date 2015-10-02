#!/usr/bin/env python

import ast
import os
from distutils.core import setup
from distutils import log
import distutils.command.install_scripts
import distutils.command.bdist_wininst


disable_rename = False


def get_version():
    """Return version string."""
    with open('scspell/__init__.py') as input_file:
        for line in input_file:
            if line.startswith('__version__'):
                return ast.parse(line).body[0].value.s


class ScriptInstaller(distutils.command.install_scripts.install_scripts):

    """Override distutils' ``install_scripts``, causing it to elide the .py
    script extension when installing on POSIX platforms."""

    def run(self):
        distutils.command.install_scripts.install_scripts.run(self)
        if os.name == 'posix' and not disable_rename:
            for script in self.get_outputs():
                base, ext = os.path.splitext(script)
                if ext == '.py':
                    log.info('Renaming %s to %s', script, base)
                    if not self.dry_run:
                        os.rename(script, base)


class WinInstCreator(distutils.command.bdist_wininst.bdist_wininst):

    """Disables the ScriptInstaller override when generating a Windows
    installer while using a POSIX platform."""

    def run(self):
        global disable_rename
        disable_rename = True
        distutils.command.bdist_wininst.bdist_wininst.run(self)


with open('README.rst', 'r') as readme_file:
    descr = readme_file.read()

setup(
    name='scspell3k',
    version=get_version(),
    description='A conservative interactive spell checker for source code.',
    long_description=descr,
    url='https://github.com/myint/scspell',
    packages=['scspell'],
    scripts=['scspell.py'],
    package_data={'scspell': ['data/*']},
    cmdclass={
        'install_scripts': ScriptInstaller,
        'bdist_wininst': WinInstCreator},
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
