"""Inert single-line editing shared by both terminal interfaces."""

import curses
import locale


def configure_unicode_terminal():
    """Keep get_wch Unicode-aware even when the invoking shell uses locale C."""
    encoding = locale.nl_langinfo(locale.CODESET).upper().replace('-', '')
    if encoding in ('UTF8', 'UTF_8'):
        return
    for candidate in ('C.UTF-8', 'en_US.UTF-8'):
        try:
            locale.setlocale(locale.LC_CTYPE, candidate)
            return
        except locale.Error:
            continue


def character_cursor(line, byte_cursor):
    encoded = line.encode('utf-8')
    if not 0 <= byte_cursor <= len(encoded):
        raise ValueError('cursor is outside the input')
    return len(encoded[:byte_cursor].decode('utf-8'))


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
