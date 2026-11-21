# Source from an interactive zsh or Bash 5+ session.
if ! [ -t 0 ] || ! [ -t 1 ]; then
    printf '%s\n' 'command-complete: source this file at a terminal prompt.' >&2
    return 1
fi

if [ -n "${ZSH_VERSION-}" ]; then
    # ZLE redirects widget stdin to /dev/null.
    if [ -z "${_command_complete_input_fd-}" ]; then
        exec {_command_complete_input_fd}<&0 || return
    fi
    _command_complete_widget() {
        local draft
        zle -I
        if draft=$(command command-complete --cursor "$CURSOR" --result-fd 3 -- "$BUFFER" \
                3>&1 <&"$_command_complete_input_fd" >&4) 4>&1; then
            BUFFER=$draft
            CURSOR=${#BUFFER}
        fi
        zle reset-prompt
    }
    zle -N command-complete-draft _command_complete_widget
    bindkey '^G' command-complete-draft
elif [ -n "${BASH_VERSION-}" ] && [ "${BASH_VERSINFO[0]}" -ge 5 ]; then
    _command_complete_widget() {
        local draft
        if {
            draft=$(command command-complete --cursor "$READLINE_POINT" --result-fd 3 -- "$READLINE_LINE" \
                3>&1 <&5 >&4)
        } 4>&1 5<&0; then
            READLINE_LINE=$draft
            READLINE_POINT=${#READLINE_LINE}
        fi
    }
    bind -x '"\C-g":_command_complete_widget'
else
    printf '%s\n' 'command-complete: use zsh or Bash 5+ for editable prompt handoff.' >&2
    return 1
fi
