#!/usr/bin/env python

from __future__ import with_statement

import os
from distutils.core import setup
from distutils import log
import distutils.command.install_scripts
import distutils.command.bdist_wininst

from scspell_lib import VERSION


disable_rename = False


class ScriptInstaller(distutils.command.install_scripts.install_scripts):
    """Override distutils' ``install_scripts``, causing it
    to elide the .py script extension when installing on POSIX
    platforms.
    """
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
    """Disables the ScriptInstaller override when generating a
    Windows installer while using a POSIX platform.
    """
    def run(self):
        global disable_rename
        disable_rename = True
        distutils.command.bdist_wininst.bdist_wininst.run(self)


app_name = 'scspell'
with open('README.txt', 'r') as readme_file:
    descr = readme_file.read()

setup(
    name=app_name,
    version=VERSION,
    description='A conservative interactive spell checker for source code.',
    long_description=descr,
    author='Paul Pelzl',
    author_email='pelzlpj@gmail.com',
    url='http://launchpad.net/%s' % app_name,

    packages=['scspell_lib'],
    scripts=['scspell.py'],
    package_data={'scspell_lib': ['data/*']},

    cmdclass={
        'install_scripts': ScriptInstaller,
        'bdist_wininst': WinInstCreator},

    license='http://www.gnu.org/licenses/old-licenses/gpl-2.0.html',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.5',
        'Topic :: Software Development',
        'Topic :: Text Processing :: Linguistic',
        'Topic :: Utilities'],
    platforms=['any']
)


# scspell-id: 2f47a8a0-18e4-4f7a-91ef-74ad909cf415
