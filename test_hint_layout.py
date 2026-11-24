"""Check the visible terminal layout, including narrow and short viewports."""

import curses
import unittest

from command_complete import Completion, Match, draw, cell_width


class Screen:
    def __init__(self, height=14, width=46):
        self.height, self.width = height, width
        self.erase()

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.writes = []

    def addstr(self, row, column, text, style=0):
        assert 0 <= row < self.height
        assert column + sum(map(cell_width, text)) < self.width
        self.writes.append((row, column, text, style))

    def move(self, *args):
        pass

    def refresh(self):
        pass


class HintLayoutTests(unittest.TestCase):
    def test_cc_wraps_the_entire_description_and_keeps_the_flag_colored(self):
        screen = Screen()
        hint = 'Send probes to the peer before declaring the remote host unreachable.'
        draw(screen, 'nc -L', 5, Completion([Match('-L', 3, 5, hint)]), 0, 0, 'help', 123)
        description = ' '.join(text for row, column, text, _ in screen.writes if row >= 2 and column > 0)
        self.assertEqual(description, hint)
        flag = next(write for write in screen.writes if write[0] >= 2 and '-L' in write[2])
        self.assertEqual(flag[3], curses.A_REVERSE | 123)

    def test_selected_wrapped_entry_is_visible_without_overlapping_footer(self):
        screen = Screen(height=9)
        matches = [Match('-' + str(i), 0, 0, 'One two three four five six seven eight nine ten.') for i in range(8)]
        draw(screen, '', 0, Completion(matches), 7, 0, 'footer')
        self.assertTrue(any('> -7' in text for _, _, text, _ in screen.writes))
        self.assertTrue(any('nine ten.' in text for _, column, text, _ in screen.writes if column))
        self.assertEqual([text for row, _, text, _ in screen.writes if row == 8], ['footer'])

    def test_unicode_wrap_keeps_wide_and_combining_characters(self):
        from command_complete import wrap_cells
        self.assertEqual(wrap_cells('界界界 e\u0301clair tail', 5), ['界界', '界', 'e\u0301clai', 'r', 'tail'])
        self.assertEqual(wrap_cells('one two three', 0), [])

    def test_oversized_hint_can_be_paged_to_its_last_line(self):
        from command_complete import HintList
        screen = Screen(height=7, width=40)
        view = HintList()
        items = [('-L', ' '.join(['probe'] * 50) + ' LASTWORD')]
        def render():
            screen.erase()
            view.draw(lambda row, text, style=0, column=0: screen.addstr(row, column, text, style),
                      items, 0, 1, 4, 40)
        render()
        self.assertFalse(any('LASTWORD' in text for _, _, text, _ in screen.writes))
        for _ in range(20):
            if not view.page(1):
                break
            render()
        self.assertTrue(any('LASTWORD' in text for _, _, text, _ in screen.writes))
        self.assertTrue(view.page(-1))

    def test_two_column_reference_wraps_without_crossing_the_other_cell(self):
        from command_complete import HintList
        screen = Screen(height=20, width=100)
        HintList().draw(lambda row, text, style=0, column=0: screen.addstr(row, column, text, style),
                        [('-a', 'Display all interfaces including inactive ones.'),
                         ('-b', 'Display the broadcast address for this interface.')],
                        1, 1, 17, 100, columns=2)
        left = ' '.join(text for _, column, text, _ in screen.writes if 0 < column < 50)
        right = ' '.join(text for _, column, text, _ in screen.writes if column > 50)
        self.assertEqual(left, 'Display all interfaces including inactive ones.')
        self.assertEqual(right, 'Display the broadcast address for this interface.')

    def test_large_lazy_result_set_only_reads_entries_near_the_viewport(self):
        from command_complete import HintList
        class Results:
            reads = 0
            def __len__(self):
                return 1000000
            def __getitem__(self, index):
                self.reads += 1
                if self.reads > 50:
                    raise AssertionError('rendering must not scan the search results')
                return str(index), 'A brief description.'
        screen = Screen()
        results = Results()
        HintList().draw(lambda row, text, style=0, column=0: screen.addstr(row, column, text, style),
                        results, 999999, 1, 10, 46)
        self.assertTrue(any('999999' in text for _, _, text, _ in screen.writes))

    def test_very_narrow_list_stacks_hint_below_the_command(self):
        from command_complete import HintList
        screen = Screen(height=20, width=20)
        HintList().draw(lambda row, text, style=0, column=0: screen.addstr(row, column, text, style),
                        [('-a', 'Show all active network interfaces.')], 0, 1, 17, 20)
        hint = ' '.join(text for _, column, text, _ in screen.writes if column == 1)
        self.assertEqual(hint, 'Show all active network interfaces.')


if __name__ == '__main__':
    unittest.main()
