# This file must be used with "source bin/activate" *from bash*
# you cannot run it directly


if [ "${BASH_SOURCE-}" = "$0" ]; then
    echo "You must source this script: \$ source $0" >&2
    exit 33
fi

deactivate () {
    unset -f pydoc >/dev/null 2>&1 || true

    # reset old environment variables
    # ! [ -z ${VAR+_} ] returns true if VAR is declared at all
    if ! [ -z "${_OLD_VIRTUAL_PATH:+_}" ] ; then
        PATH="$_OLD_VIRTUAL_PATH"
        export PATH
        unset _OLD_VIRTUAL_PATH
    fi
    if ! [ -z "${_OLD_VIRTUAL_PYTHONHOME+_}" ] ; then
        PYTHONHOME="$_OLD_VIRTUAL_PYTHONHOME"
        export PYTHONHOME
        unset _OLD_VIRTUAL_PYTHONHOME
    fi

    # The hash command must be called to get it to forget past
    # commands. Without forgetting past commands the $PATH changes
    # we made may not be respected
    hash -r 2>/dev/null

    if ! [ -z "${_OLD_VIRTUAL_PS1+_}" ] ; then
        PS1="$_OLD_VIRTUAL_PS1"
        export PS1
        unset _OLD_VIRTUAL_PS1
    fi

    unset VIRTUAL_ENV
    unset VIRTUAL_ENV_PROMPT
    if [ ! "${1-}" = "nondestructive" ] ; then
    # Self destruct!
        unset -f deactivate
    fi
}

# unset irrelevant variables
deactivate nondestructive

VIRTUAL_ENV=__VIRTUAL_ENV__
if ([ "$OSTYPE" = "cygwin" ] || [ "$OSTYPE" = "msys" ]) && $(command -v cygpath &> /dev/null) ; then
    VIRTUAL_ENV=$(cygpath -u "$VIRTUAL_ENV")
fi
export VIRTUAL_ENV

_OLD_VIRTUAL_PATH="$PATH"
PATH="$VIRTUAL_ENV/"__BIN_NAME__":$PATH"
export PATH

# unset PYTHONHOME if set
if ! [ -z "${PYTHONHOME+_}" ] ; then
    _OLD_VIRTUAL_PYTHONHOME="$PYTHONHOME"
    unset PYTHONHOME
fi

if [ "x"__VIRTUAL_PROMPT__ != x ] ; then
    VIRTUAL_ENV_PROMPT=__VIRTUAL_PROMPT__
else
    VIRTUAL_ENV_PROMPT=$(basename "$VIRTUAL_ENV")
fi
export VIRTUAL_ENV_PROMPT

if [ -z "${VIRTUAL_ENV_DISABLE_PROMPT-}" ] &&
    { [ -n "${BASH_VERSION-}" ] || [ -n "${ZSH_VERSION-}" ]; }; then
    _OLD_VIRTUAL_PS1="${PS1-}"
    # The prompt text (from --prompt or the environment directory name) must never be interpreted by the shell.
    # bash expands PS1 after decoding its prompt escapes when promptvars is on or in posix mode, so the prompt holds a
    # reference to the variable and its value never reaches that expansion; otherwise only the decode runs and
    # backslashes need doubling. zsh re-expands backslashes, dollar signs and backticks under PROMPT_SUBST, which a
    # user can set after activation, and reads % as a prompt escape. The guards keep the substitutions away from
    # POSIX shells such as dash, which reject them with "Bad substitution".
    if [ -n "${BASH_VERSION-}" ] && { shopt -q promptvars || shopt -qo posix; }; then
        PS1='(${VIRTUAL_ENV_PROMPT-}) '"${PS1-}"
    else
        _VIRTUAL_PROMPT="${VIRTUAL_ENV_PROMPT//\\/\\\\}"
        if [ -n "${ZSH_VERSION-}" ]; then
            _VIRTUAL_PROMPT="${_VIRTUAL_PROMPT//\$/\\\$}"
            _VIRTUAL_PROMPT="${_VIRTUAL_PROMPT//\`/\\\`}"
            _VIRTUAL_PROMPT="${_VIRTUAL_PROMPT//\%/%%}"
        fi
        PS1="(${_VIRTUAL_PROMPT}) ${PS1-}"
        unset _VIRTUAL_PROMPT
    fi
    export PS1
fi

# Make sure to unalias pydoc if it's already there
alias pydoc 2>/dev/null >/dev/null && unalias pydoc || true

pydoc () {
    python -m pydoc "$@"
}

# The hash command must be called to get it to forget past
# commands. Without forgetting past commands the $PATH changes
# we made may not be respected
hash -r 2>/dev/null
