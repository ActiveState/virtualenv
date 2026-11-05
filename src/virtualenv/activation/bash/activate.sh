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

    if [ -n "${_OLD_VIRTUAL_PSVAR+x}" ] ; then
        psvar[9]="$_OLD_VIRTUAL_PSVAR"
        unset _OLD_VIRTUAL_PSVAR
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
    if [ -n "${BASH_VERSION-}" ]; then
        # bash decodes its prompt escapes on every draw and expands the result when promptvars is on or in posix
        # mode; both can change after activation and an exported PS1 reaches child shells, so the value gets escaped
        # for both passes whatever the state is now. The escapes are built by concatenation because the replacement
        # in ${var//pat/rep} loses backslashes depending on the bash version, BASH_COMPAT and patsub_replacement
        _VIRTUAL_REST=$VIRTUAL_ENV_PROMPT
        _VIRTUAL_PROMPT=
        while [ -n "$_VIRTUAL_REST" ]; do
            _VIRTUAL_CHAR=${_VIRTUAL_REST%"${_VIRTUAL_REST#?}"}
            _VIRTUAL_REST=${_VIRTUAL_REST#?}
            case $_VIRTUAL_CHAR in
                \\) _VIRTUAL_PROMPT="$_VIRTUAL_PROMPT\\\\\\\\" ;;
                \$ | \`) _VIRTUAL_PROMPT="$_VIRTUAL_PROMPT\\$_VIRTUAL_CHAR" ;;
                *) _VIRTUAL_PROMPT="$_VIRTUAL_PROMPT$_VIRTUAL_CHAR" ;;
            esac
        done
        unset _VIRTUAL_REST _VIRTUAL_CHAR
    else
        # zsh inserts a psvar entry into the prompt as data under every prompt option, so the value needs no
        # escaping, and the %9v reference holds nothing for another shell to expand when PS1 is exported. The guard
        # above keeps POSIX shells such as dash away from the array assignment
        _OLD_VIRTUAL_PSVAR="${psvar[9]-}"
        psvar[9]="$VIRTUAL_ENV_PROMPT"
        _VIRTUAL_PROMPT='%9v'
    fi
    PS1="(${_VIRTUAL_PROMPT}) ${PS1-}"
    unset _VIRTUAL_PROMPT
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
