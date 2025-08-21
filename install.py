#!/usr/bin/env python

from os.path import abspath, dirname, join, lexists, islink, realpath
from os.path import exists
from os import symlink, environ, walk, mkdir
from subprocess import check_output

CONFIGDIR = abspath(dirname(__file__))
HOME = environ["HOME"]

DOTFILES_TO_INSTALL = (
    "bashrc",
    "ipython",
    "pylintrc",
    "skeleton",
    "vim",
    "vimoutliner",
    "vimoutlinerrc",
    "vimrc",
    "wgetrc",
    "foodplan",
    "passwdwords",
    "virtualenvs/get_env_details",
    "virtualenvs/initialize",
    "virtualenvs/postactivate",
    "virtualenvs/postdeactivate",
    "virtualenvs/postmkvirtualenv",
    "virtualenvs/postrmvirtualenv",
    "virtualenvs/preactivate",
    "virtualenvs/predeactivate",
    "virtualenvs/premkvirtualenv",
    "virtualenvs/prermvirtualenv",
)


DIRS_TO_INSTALL_RECURSIVLY = (
    "bin",
)

DEB_PACKAGES = (
    "bash-completion",
    "ipython",
    "less",
    "lynx",
    "mercurial",
    "pylint",
    "python-argparse",
    "python-pip",
    "python-virtualenv",
    "python-dev",
    "vim",
)

def install_link(src, dst):
    """
    Create a link from src to dst if it does not exist
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


def get_installed_packages():
    """Return a list of the names of all installed packages"""
    return check_output(["dpkg-query", "-f", "${binary:Package}\n", "-W"]).splitlines()


for f in DOTFILES_TO_INSTALL:
    target = join(HOME, "."+f)
    source = join(CONFIGDIR, f)
    install_link(source, target)


for f in DIRS_TO_INSTALL_RECURSIVLY:
    sourcedir = join(CONFIGDIR, f)
    for (d, dirs, files) in walk(sourcedir, topdown=True):
        targetdir = join(HOME, d.lstrip(CONFIGDIR))
        if not lexists(targetdir):
            mkdir(targetdir)
        for f in files:
            target_name = f
            if target_name.endswith(".py"):
                target_name = target_name[:-3]
            install_link(join(d, f), join(targetdir, target_name))

installed_packages = get_installed_packages()
missing_packages = []
for pkg in DEB_PACKAGES:
    if pkg not in installed_packages:
        missing_packages.append(pkg)

if missing_packages:
    print("The following packages are missing:", " ".join(missing_packages))
    print("To fix, please run:")
    print("sudo apt-get install", " ".join(missing_packages))
