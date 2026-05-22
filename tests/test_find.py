import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

import md_reader.app as app_module
from md_reader.app import MarkdownWindow, find_match_spans, find_status_text, next_match_index


class FindHelperTests(unittest.TestCase):
    def test_find_match_spans_are_case_insensitive_by_default(self):
        self.assertEqual(
            [(0, 6), (7, 13), (14, 20)],
            find_match_spans("Needle needle NEEDLE", "needle", case_sensitive=False),
        )

    def test_find_match_spans_can_match_case_sensitively(self):
        self.assertEqual(
            [(7, 13)],
            find_match_spans("Target target TARGET", "target", case_sensitive=True),
        )

    def test_next_match_index_wraps_forward_and_backward(self):
        matches = [(2, 4), (8, 10), (15, 17)]

        self.assertEqual(0, next_match_index(matches, cursor_position=0, backwards=False))
        self.assertEqual(1, next_match_index(matches, cursor_position=4, backwards=False))
        self.assertEqual(0, next_match_index(matches, cursor_position=20, backwards=False))
        self.assertEqual(2, next_match_index(matches, cursor_position=20, backwards=True))
        self.assertEqual(0, next_match_index(matches, cursor_position=8, backwards=True))
        self.assertEqual(2, next_match_index(matches, cursor_position=0, backwards=True))

    def test_find_status_text_reports_current_match_and_empty_states(self):
        self.assertEqual("", find_status_text("", total=0, active_index=-1))
        self.assertEqual("No matches", find_status_text("missing", total=0, active_index=-1))
        self.assertEqual("2 of 4", find_status_text("needle", total=4, active_index=1))


class FindBarWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])

    def setUp(self) -> None:
        self._original_webengine_view = app_module.QWebEngineView
        app_module.QWebEngineView = None

    def tearDown(self) -> None:
        app_module.QWebEngineView = self._original_webengine_view

    def test_find_text_shows_persistent_bar_and_updates_count(self):
        window = MarkdownWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window._set_editor_text("alpha beta alpha")

        self.assertFalse(window.find_bar.isVisible())
        window.find_text()
        window.find_input.setText("alpha")
        self.app.processEvents()

        self.assertTrue(window.find_bar.isVisible())
        self.assertTrue(window.find_input.hasFocus())
        self.assertEqual("1 of 2", window.find_status.text())

    def test_hide_find_bar_dismisses_without_clearing_query(self):
        window = MarkdownWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window.find_text()
        window.find_input.setText("alpha")

        window.hide_find_bar()

        self.assertFalse(window.find_bar.isVisible())
        self.assertEqual("alpha", window.find_input.text())

    def test_find_bar_stays_compact_when_visible(self):
        window = MarkdownWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        window.find_text()
        self.app.processEvents()

        self.assertLessEqual(window.find_bar.maximumHeight(), 52)
        self.assertLessEqual(window.find_bar.sizeHint().height(), 52)

    def test_preview_mode_uses_native_webengine_search(self):
        class FakePage:
            def __init__(self) -> None:
                self.calls = []

            def findText(self, term, flags=None, callback=None):
                self.calls.append((term, flags))
                if callback:
                    callback(True)

        class FakePreview:
            def __init__(self) -> None:
                self.fake_page = FakePage()

            def page(self):
                return self.fake_page

        window = MarkdownWindow()
        self.addCleanup(window.close)
        preview = FakePreview()
        window.preview = preview
        window.view_mode = "preview"
        app_module.QWebEngineView = FakePreview
        window.find_input.setText("needle")

        window.perform_find(reset=True)

        self.assertEqual("needle", preview.fake_page.calls[-1][0])
        self.assertEqual("Found", window.find_status.text())


if __name__ == "__main__":
    unittest.main()
