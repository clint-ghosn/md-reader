import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import md_reader.app as app_module
from md_reader.app import (
    APP_NAME,
    MarkdownWindow,
    ReaderSettings,
    load_reader_settings,
    render_markdown,
    save_reader_settings,
)


class ReaderSettingsTests(unittest.TestCase):
    def test_first_run_defaults_to_system_appearance_and_preview_mode(self):
        settings = load_reader_settings({})

        self.assertEqual("system", settings.appearance_mode)
        self.assertEqual("preview", settings.default_view_mode)
        self.assertEqual("preview", settings.last_used_view_mode)
        self.assertEqual("preview", settings.open_view_mode())

    def test_invalid_stored_reader_settings_fall_back_to_safe_defaults(self):
        settings = load_reader_settings(
            {
                "appearanceMode": "sepia",
                "defaultViewMode": "source",
                "lastUsedViewMode": "dual",
            }
        )

        self.assertEqual(ReaderSettings(), settings)
        self.assertEqual("preview", settings.open_view_mode())

    def test_last_used_default_opens_with_most_recent_view_mode(self):
        settings = load_reader_settings(
            {
                "appearanceMode": "dark",
                "defaultViewMode": "last-used",
                "lastUsedViewMode": "split",
            }
        )

        self.assertEqual("dark", settings.appearance_mode)
        self.assertEqual("split", settings.open_view_mode())

    def test_reader_settings_persist_to_qsettings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            QSettings.setDefaultFormat(QSettings.IniFormat)
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, temp_dir)
            store = QSettings("MDReaderTest", APP_NAME)
            store.clear()

            save_reader_settings(
                store,
                ReaderSettings(
                    appearance_mode="dark",
                    default_view_mode="last-used",
                    last_used_view_mode="raw",
                ),
            )
            store.sync()

            loaded = load_reader_settings(store)

        self.assertEqual("dark", loaded.appearance_mode)
        self.assertEqual("last-used", loaded.default_view_mode)
        self.assertEqual("raw", loaded.last_used_view_mode)

    def test_render_markdown_can_force_dark_and_light_reader_themes(self):
        dark_document = render_markdown("# Title", appearance_mode="dark")
        light_document = render_markdown("# Title", appearance_mode="light")

        self.assertIn("data-md-reader-theme=\"dark\"", dark_document)
        self.assertIn("background: #0d1117", dark_document)
        self.assertIn(":focus-visible", dark_document)
        self.assertIn("data-md-reader-theme=\"light\"", light_document)
        self.assertIn("background: #ffffff", light_document)


class MarkdownWindowViewModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, self.temp_dir.name)
        app_module.QWebEngineView = None
        QSettings("MDReader", APP_NAME).clear()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def cleanup_window(self, window: MarkdownWindow) -> None:
        window.hide()
        window.deleteLater()

    def test_window_defaults_to_preview_mode_and_hides_raw_editor(self):
        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)

        self.assertEqual("preview", window.view_mode)
        self.assertFalse(window.editor.isVisibleTo(window.main_splitter))
        self.assertTrue(window.preview_container.isVisibleTo(window.main_splitter))
        self.assertTrue(window.preview_mode_action.isChecked())

    def test_switching_view_modes_updates_layout_and_preserves_unsaved_text(self):
        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)
        window.editor.setPlainText("# Draft\n\nUnsaved")

        window.set_view_mode("raw")
        self.assertTrue(window.editor.isVisibleTo(window.main_splitter))
        self.assertFalse(window.preview_container.isVisibleTo(window.main_splitter))

        window.set_view_mode("split")
        self.assertTrue(window.editor.isVisibleTo(window.main_splitter))
        self.assertTrue(window.preview_container.isVisibleTo(window.main_splitter))

        window.set_view_mode("preview")
        self.assertEqual("# Draft\n\nUnsaved", window.editor.toPlainText())
        self.assertFalse(window.editor.isVisibleTo(window.main_splitter))
        self.assertTrue(window.preview_container.isVisibleTo(window.main_splitter))

    def test_appearance_and_view_mode_changes_are_saved(self):
        store = QSettings("MDReader", APP_NAME)
        store.clear()
        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)

        window.set_appearance_mode("dark")
        window.set_view_mode("raw")
        window.save_settings()

        reloaded = load_reader_settings(QSettings("MDReader", APP_NAME))

        self.assertEqual("dark", reloaded.appearance_mode)
        self.assertEqual("preview", reloaded.default_view_mode)
        self.assertEqual("raw", reloaded.last_used_view_mode)

    def test_default_view_mode_setting_controls_new_window_mode(self):
        store = QSettings("MDReader", APP_NAME)
        store.clear()
        save_reader_settings(
            store,
            ReaderSettings(
                appearance_mode="system",
                default_view_mode="raw",
                last_used_view_mode="preview",
            ),
        )
        store.sync()

        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)

        self.assertEqual("raw", window.view_mode)
        self.assertTrue(window.editor.isVisibleTo(window.main_splitter))
        self.assertFalse(window.preview_container.isVisibleTo(window.main_splitter))
        self.assertTrue(window.default_raw_action.isChecked())

    def test_small_width_split_mode_falls_back_to_vertical_panes(self):
        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)
        window.resize(520, 700)

        window.set_view_mode("split")

        self.assertEqual("split", window.view_mode)
        self.assertEqual(app_module.Qt.Vertical, window.main_splitter.orientation())

    def test_table_row_and_column_commands_use_preview_when_preview_is_visible(self):
        class FakePage:
            def __init__(self) -> None:
                self.scripts: list[str] = []

            def runJavaScript(self, script: str) -> None:
                self.scripts.append(script)

        class FakePreview:
            def __init__(self) -> None:
                self.fake_page = FakePage()

            def page(self):
                return self.fake_page

        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)
        preview = FakePreview()
        window.preview = preview
        window.view_mode = "preview"
        window.set_active_edit_surface("editor")
        app_module.QWebEngineView = FakePreview

        window.add_table_row()
        window.add_table_column()

        self.assertIn('window.mdReaderApplyFormat("add-table-row", {});', preview.fake_page.scripts)
        self.assertIn('window.mdReaderApplyFormat("add-table-column", {});', preview.fake_page.scripts)

    def test_open_supported_drop_urls_opens_files_from_child_widget_drop_handlers(self):
        dropped_file = Path(self.temp_dir.name) / "dropped.md"
        dropped_file.write_text("# Dropped", encoding="utf-8")
        window = MarkdownWindow()
        self.addCleanup(self.cleanup_window, window)

        self.assertTrue(window.open_supported_drop_urls([app_module.QUrl.fromLocalFile(str(dropped_file))]))

        self.assertEqual(dropped_file, window.current_file)
        self.assertEqual("# Dropped", window.editor.toPlainText())


if __name__ == "__main__":
    unittest.main()
