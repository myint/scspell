"""
portable -- contains functions for hiding differences between platforms.
"""
import os


# Cross-platform version of getch()
try:
    import msvcrt
    def getch():
        return msvcrt.getch()

except ImportError:
    import sys, tty, termios
    def getch():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


def get_data_dir(progname):
    """Retrieves a platform-appropriate data directory for the specified program."""
    if sys.platform == 'win32':
        parent_dir = os.getenv('APPDATA')
        prog_dir   = progname
    else:
        parent_dir = os.getenv('HOME')
        prog_dir   = '.' + progname
    return os.path.normpath(os.path.join(parent_dir, prog_dir))


