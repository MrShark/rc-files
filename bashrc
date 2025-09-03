# .bashrc
# shellcheck shell=bash 

# Source global definitions
if [ -f /etc/bashrc ]; then
	. /etc/bashrc
fi

# Force umask
umask 0002

# don't put duplicate lines or lines starting with space in the history.
# See bash(1) for more options
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize


# User specific PATH
if ! [[ "$PATH" == *"$HOME/.local/bin"* ]]
then
    PATH="$HOME/.local/bin:$PATH"
fi
if ! [[ "$PATH" == *"$HOME/bin:"* ]]
then
    PATH="$HOME/bin:$PATH"
fi
export PATH

# Command prompt

if [ -f /usr/share/doc/git/contrib/completion/git-prompt.sh ]; then
	. /usr/share/doc/git/contrib/completion/git-prompt.sh
fi
PS1='\w$(__git_ps1 " (%s)") \$ '

# Activate direnv
export PYENV_ROOT="$HOME/lib/pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Activate direnv
eval "$(direnv hook bash)"

# Source local definitions
if [ -f ~/.bashrc_local ]; then
	. ~/.bashrc_local
fi