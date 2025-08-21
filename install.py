#!/usr/bin/env python

from os import environ, mkdir, symlink, walk
from os.path import abspath, dirname, exists, islink, join, lexists, realpath

CONFIGDIR = abspath(dirname(__file__))
HOME = environ["HOME"]

DOTFILES_TO_INSTALL = (
    "bashrc",
    "passwdwords",
)


DIRS_TO_INSTALL_RECURSIVLY = ("bin",)


def install_link(src, dst):
    """Create a link from src to dst if it does not exist
    else warn if dst exists but isn't a link to src
    """
    if lexists(dst):
        if not islink(dst):
            print("%s exists, but is not a link" % dst)
        elif realpath(dst) != src:
            print("%s is a link, but not to %s" % (dst, src))
    else:
        if not exists(dirname(dst)):
            mkdir(dirname(dst))
            print("Created dir %s" % dirname(dst))
        symlink(src, dst)
        print("Created link %s -> %s" % (dst, src))


for f in DOTFILES_TO_INSTALL:
    target = join(HOME, "." + f)
    source = join(CONFIGDIR, f)
    install_link(source, target)


for f in DIRS_TO_INSTALL_RECURSIVLY:
    sourcedir = join(CONFIGDIR, f)
    for d, dirs, files in walk(sourcedir, topdown=True):
        targetdir = join(HOME, d.lstrip(CONFIGDIR))
        if not lexists(targetdir):
            mkdir(targetdir)
        for f in files:
            target_name = f
            target_name = target_name.removesuffix(".py")
            install_link(join(d, f), join(targetdir, target_name))
