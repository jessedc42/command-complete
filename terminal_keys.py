"""Inert single-line editing shared by both terminal interfaces."""

import curses


def edit_text(line, cursor, key):
    if key in (curses.KEY_LEFT, '\x02'):
        cursor = max(0, cursor - 1)
    elif key in (curses.KEY_RIGHT, '\x06'):
        cursor = min(len(line), cursor + 1)
    elif key in (curses.KEY_HOME, '\x01'):
        cursor = 0
    elif key in (curses.KEY_END, '\x05'):
        cursor = len(line)
    elif key in (curses.KEY_BACKSPACE, '\x7f', '\b') and cursor:
        line = line[:cursor - 1] + line[cursor:]
        cursor -= 1
    elif key == curses.KEY_DC:
        line = line[:cursor] + line[cursor + 1:]
    elif key == '\x15':
        line, cursor = line[cursor:], 0
    elif key == '\x0b':
        line = line[:cursor]
    elif isinstance(key, str) and key.isprintable():
        line = line[:cursor] + key + line[cursor:]
        cursor += len(key)
    return line, cursor
