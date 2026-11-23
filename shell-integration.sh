# Source from an interactive zsh or Bash 5+ session.
if ! [ -t 0 ] || ! [ -t 1 ]; then
    printf '%s\n' 'command-complete: source this file at a terminal prompt.' >&2
    return 1
fi

if [ -n "${ZSH_VERSION-}" ]; then
    _command_complete_directory=${${(%):-%x}:A:h}
    # ZLE redirects widget stdin to /dev/null.
    if [ -z "${_command_complete_input_fd-}" ]; then
        exec {_command_complete_input_fd}<&0 || return
    fi
    _command_draft_widget() {
        local draft cursor_option=--cursor encoding_probe='é'
        [ "${#encoding_probe}" -gt 1 ] && cursor_option=--cursor-bytes
        zle -I
        if draft=$(command "$1" "$cursor_option" "$CURSOR" --result-fd 3 -- "$BUFFER" \
                3>&1 <&"$_command_complete_input_fd" >&4) 4>&1; then
            BUFFER=$draft
            CURSOR=${#BUFFER}
        fi
        zle reset-prompt
    }
    _command_complete_cli=${COMMAND_COMPLETE_EXECUTABLE:-"$_command_complete_directory/command_complete.py"}
    _command_search_cli=${COMMAND_SEARCH_EXECUTABLE:-"$_command_complete_directory/command_search.py"}
    _command_complete_widget() { _command_draft_widget "$_command_complete_cli"; }
    _command_search_widget() { _command_draft_widget "$_command_search_cli"; }
    zle -N command-complete-draft _command_complete_widget
    zle -N command-search-draft _command_search_widget
    bindkey '^G' command-complete-draft
    bindkey "${COMMAND_SEARCH_KEY_BINDING:-^X^G}" command-search-draft
elif [ -n "${BASH_VERSION-}" ] && [ "${BASH_VERSINFO[0]}" -ge 5 ]; then
    _command_complete_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    _command_complete_cli=${COMMAND_COMPLETE_EXECUTABLE:-"$_command_complete_directory/command_complete.py"}
    _command_search_cli=${COMMAND_SEARCH_EXECUTABLE:-"$_command_complete_directory/command_search.py"}
    _command_draft_widget() {
        local draft cursor_option=--cursor encoding_probe='é'
        [ "${#encoding_probe}" -gt 1 ] && cursor_option=--cursor-bytes
        if {
            draft=$(command "$1" "$cursor_option" "$READLINE_POINT" --result-fd 3 -- "$READLINE_LINE" \
                3>&1 <&5 >&4)
        } 4>&1 5<&0; then
            READLINE_LINE=$draft
            READLINE_POINT=${#READLINE_LINE}
        fi
    }
    _command_complete_widget() { _command_draft_widget "$_command_complete_cli"; }
    _command_search_widget() { _command_draft_widget "$_command_search_cli"; }
    _command_search_key_binding=${COMMAND_SEARCH_KEY_BINDING:-'\C-x\C-g'}
    if [[ -o vi && $_command_search_key_binding == '\C-x'* ]]; then
        # vi-insert otherwise retains self-insert as the timed-out prefix's
        # fallback. Remove the old sequence first so re-sourcing is safe too.
        bind -r "$_command_search_key_binding"
        bind -r '\C-x'
    fi
    bind -x '"\C-g":_command_complete_widget'
    bind -x "\"$_command_search_key_binding\":_command_search_widget"
else
    printf '%s\n' 'command-complete: use zsh or Bash 5+ for editable prompt handoff.' >&2
    return 1
fi
