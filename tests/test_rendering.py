import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from md_reader.app import (
    PREVIEW_RENDER_DEBOUNCE_MS,
    cache_paths_for_restart,
    configure_qt_application_identity,
    default_reader_settings,
    editor_scroll_value_for_source_line,
    extract_markdown_headings,
    fenced_code_languages,
    is_allowed_external_link,
    is_supported_drop_file,
    mermaid_script_tag,
    normalize_appearance_mode,
    normalize_default_view_mode,
    normalize_view_mode,
    prepare_markdown_for_preview,
    render_markdown,
    supported_drop_path,
)
from PySide6.QtCore import QUrl


class FakeQtApplication:
    def __init__(self):
        self.organization_name = None
        self.application_name = None
        self.application_display_name = None

    def setOrganizationName(self, value):
        self.organization_name = value

    def setApplicationName(self, value):
        self.application_name = value

    def setApplicationDisplayName(self, value):
        self.application_display_name = value


class RenderingTests(unittest.TestCase):
    def test_rendered_preview_script_is_valid_javascript(self):
        document = render_markdown("# Title\n\n## Section\n\nNeedle text")
        script_start = document.rfind("<script>")
        script_end = document.rfind("</script>")
        self.assertGreater(script_start, -1)
        self.assertGreater(script_end, script_start)
        script = document[script_start + len("<script>"):script_end]
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            script_path = Path(handle.name)
            handle.write(script)
        self.addCleanup(script_path.unlink, missing_ok=True)

        try:
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                text=True,
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            self.skipTest("node is not available for preview script syntax checking")

        self.assertEqual("", result.stderr, result.stderr)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_render_markdown_marks_preview_editable_and_adds_copy_controls(self):
        document = render_markdown("# Title\n\nA paragraph.\n\n```python\nprint('x')\n```")

        self.assertIn('<main id="preview-content" contenteditable="true"', document)
        self.assertIn("installCopyButtons", document)
        self.assertIn("copy-block-button", document)
        self.assertIn('.copy-block-button, .md-reader-collapse-toggle', document)
        self.assertIn("copySelection", document)
        self.assertIn("previewScrolled", document)
        self.assertIn("visibleSourceLine", document)
        self.assertIn("window.mdReaderCopySelection = copySelection", document)
        self.assertIn("codehilite", document)
        self.assertIn('data-code-language="python"', document)

    def test_reader_settings_defaults_are_reader_focused(self):
        self.assertEqual("system", default_reader_settings()["appearanceMode"])
        self.assertEqual("preview", default_reader_settings()["defaultViewMode"])
        self.assertEqual("preview", default_reader_settings()["lastUsedViewMode"])

    def test_invalid_reader_settings_fall_back_to_safe_defaults(self):
        self.assertEqual("system", normalize_appearance_mode("solarized"))
        self.assertEqual("preview", normalize_view_mode("source"))
        self.assertEqual("preview", normalize_default_view_mode("dual"))
        self.assertEqual("last-used", normalize_default_view_mode("last-used"))

    def test_extract_markdown_headings_uses_stable_unique_slugs_and_ignores_code(self):
        headings = extract_markdown_headings(
            "# Project Overview\n\n"
            "```md\n"
            "# Not a heading\n"
            "```\n\n"
            "## Project Overview\n\n"
            "## Project Overview\n"
        )

        self.assertEqual(
            [
                {"id": "project-overview", "level": 1, "text": "Project Overview", "source_line": 1},
                {"id": "project-overview-2", "level": 2, "text": "Project Overview", "source_line": 7},
                {"id": "project-overview-3", "level": 2, "text": "Project Overview", "source_line": 9},
            ],
            headings,
        )

    def test_render_markdown_adds_document_navigator_controls(self):
        document = render_markdown("# Title\n\n## One\n\nText\n\n## Two\n\nText")

        self.assertIn("md-reader-navigator", document)
        self.assertIn("mdReaderDocumentHeadings", document)
        self.assertIn("mdReaderInstallNavigator", document)
        self.assertIn('id="one"', document)
        self.assertIn('id="two"', document)
        self.assertIn("mdreader-contents-button", document)
        self.assertIn('aria-controls="mdreader-contents-overlay"', document)
        self.assertIn('role="dialog"', document)
        self.assertIn('href="#two"', document)
        self.assertIn("mdreader-section-toggle", document)
        self.assertIn('aria-expanded="true"', document)
        self.assertIn("Collapse all", document)
        self.assertIn("Expand all", document)

    def test_render_markdown_hides_toc_and_minimap_when_document_has_fewer_than_two_headings(self):
        document = render_markdown("# Solo\n\nText")

        self.assertIn("mdreader-section-toggle", document)
        self.assertNotIn('class="mdreader-contents-button"', document)
        self.assertNotIn('class="mdreader-minimap"', document)

    def test_render_markdown_adds_hidden_minimap_shell_for_long_document_detection(self):
        document = render_markdown("# Guide\n\n## Section\n\n" + "\n\n".join(["Long text"] * 80))

        self.assertIn("mdreader-minimap", document)
        self.assertIn("mdreader-minimap-canvas", document)
        self.assertIn("mdreader-minimap-tooltip", document)
        self.assertIn("document.documentElement.scrollHeight >= window.innerHeight * 2.5", document)
        self.assertNotIn("if (headings.length < 5)", document)

    def test_document_navigator_binds_existing_static_collapse_buttons(self):
        document = render_markdown("# Guide\n\n## Section\n\nText")

        self.assertIn("mdreaderCollapseReady", document)
        self.assertIn('heading.querySelector(".md-reader-collapse-toggle")', document)
        self.assertIn('button.addEventListener("click"', document)

    def test_render_markdown_adds_minimap_for_long_heading_rich_documents(self):
        document = render_markdown(
            "\n\n".join(
                [
                    "# Guide",
                    "## One\n\nText",
                    "## Two\n\nText",
                    "## Three\n\nText",
                    "## Four\n\nText",
                    "## Five\n\nText",
                ]
            )
        )

        self.assertIn("mdreader-minimap", document)
        self.assertIn("mdreader-minimap-marker", document)
        self.assertIn("mdreader-minimap-line", document)
        self.assertNotIn("mdreader-minimap-viewport", document)
        self.assertIn('data-heading-id="five"', document)
        self.assertIn("data-minimap-label", document)
        self.assertIn('title="Five"', document)

    def test_document_navigator_script_contains_collapse_toc_current_section_and_minimap_behaviors(self):
        document = render_markdown("# A\n\n## B\n\nText\n\n## C\n\nText\n\n## D\n\nText\n\n## E\n\nText")

        self.assertIn("installDocumentNavigator", document)
        self.assertIn("setNavigatorMode", document)
        self.assertIn("mdreader-nav-mode", document)
        self.assertIn('const nextMode = mode === "toc" || mode === "minimap" ? mode : "none";', document)
        self.assertIn('setNavigatorMode("none")', document)
        self.assertIn('mdReaderNavigatorMode === "minimap" ? "none" : "minimap"', document)
        self.assertIn("toggleSection", document)
        self.assertIn("mdreader-section-hidden", document)
        self.assertIn("IntersectionObserver", document)
        self.assertIn("mdreader-current-section", document)
        self.assertIn("mdreader-minimap-tooltip", document)
        self.assertIn("md-reader-minimap-canvas", document)
        self.assertIn("miniMapClassForElement", document)
        self.assertIn("miniMapLabelForElement", document)
        self.assertNotIn('document.addEventListener("mousedown"', document)
        self.assertIn("Ctrl+K", document)

    def test_minimap_hover_labels_use_content_snippets_and_generic_block_names(self):
        document = render_markdown(
            "\n\n".join(
                [
                    "# Guide",
                    "Intro paragraph before any subsection.",
                    "| Name | Value |\n| --- | --- |\n| One | Two |",
                    "![Alt text](image.png)",
                    "## Details",
                    "- standalone list item",
                ]
            )
        )

        self.assertIn("miniMapLabelForElement", document)
        self.assertIn('data-minimap-label="Guide"', document)
        self.assertIn('line.setAttribute("data-minimap-label", miniMapLabelForElement(element, currentHeadingLabel));', document)
        self.assertIn('return "Table";', document)
        self.assertIn('return "Image";', document)
        self.assertIn('if (tag === "li") {', document)
        self.assertIn('return compactMiniMapText(element.innerText || element.textContent) || "Content";', document)

    def test_navigator_controls_are_top_right_and_panels_share_anchor(self):
        document = render_markdown("# A\n\n## B\n\nText\n\n## C\n\nText")

        self.assertIn("top: 16px;", document)
        self.assertIn("right: 20px;", document)
        self.assertIn("top: 42px;", document)
        self.assertIn("width: min(250px, calc(100vw - 40px));", document)
        self.assertIn("top: 58px;", document)
        self.assertIn("right: 20px;", document)
        self.assertNotIn("bottom: 20px;", document)
        self.assertNotIn("bottom: 44px;", document)

    def test_render_markdown_adds_persistent_preview_find_hooks(self):
        document = render_markdown("# Title\n\nNeedle text")

        self.assertIn("mdReaderFind", document)
        self.assertIn("md-reader-find-mark", document)
        self.assertIn("mdReaderClearFind", document)

    def test_render_markdown_preserves_tables(self):
        document = render_markdown("| A | B |\n| --- | --- |\n| 1 | 2 |")

        self.assertIn("<table>", document)
        self.assertIn("<th>A</th>", document)
        self.assertIn("<td>1</td>", document)

    def test_render_markdown_adds_preview_table_row_and_column_commands(self):
        document = render_markdown("| A | B |\n| --- | --- |\n| 1 | 2 |")

        self.assertIn("add-table-row", document)
        self.assertIn("addTableRow", document)
        self.assertIn("add-table-column", document)
        self.assertIn("addTableColumn", document)
        self.assertIn("activeTable", document)

    def test_render_markdown_renders_task_markers_as_checkboxes(self):
        document = render_markdown("- [ ] First\n- [x] Second")

        self.assertIn('type="checkbox"', document)
        self.assertIn('class="mdreader-task-checkbox"', document)
        self.assertIn('data-task-marker="[ ]"', document)
        self.assertIn('data-task-marker="[x]" checked', document)
        self.assertIn("installTaskCheckboxes", document)

    def test_preview_serialization_supports_task_checkbox_state(self):
        document = render_markdown("- [ ] First")

        self.assertIn('tag === "input"', document)
        self.assertIn('node.classList.contains("mdreader-task-checkbox")', document)
        self.assertIn('node.checked ? "[X] " : "[ ] "', document)

    def test_preview_scroll_to_source_line_falls_forward_before_previous_anchor(self):
        document = render_markdown("# Title\n\nParagraph")

        self.assertIn("findNearestSourceAnchor", document)
        self.assertIn("line + offset", document)
        self.assertIn("line - offset", document)

    def test_fenced_code_languages_ignores_mermaid_blocks(self):
        languages = fenced_code_languages("```python\nprint('x')\n```\n\n```mermaid\ngraph TD\n```")

        self.assertEqual(["python"], languages)

    def test_render_markdown_escapes_raw_script_tags_from_input(self):
        document = render_markdown("# Title\n\n<script>alert('owned')</script>")

        self.assertNotIn("<script>alert('owned')</script>", document)
        self.assertIn("&lt;script&gt;alert('owned')&lt;/script&gt;", document)

    def test_render_markdown_strips_unsafe_link_protocols(self):
        document = render_markdown("[x](javascript:alert(1))\n\n![x](data:image/svg+xml,<svg></svg>)")

        self.assertNotIn('href="javascript:', document.lower())
        self.assertNotIn('src="data:', document.lower())

    def test_preview_navigation_allows_only_external_link_schemes(self):
        self.assertTrue(is_allowed_external_link(QUrl("https://example.com")))
        self.assertTrue(is_allowed_external_link(QUrl("file:///C:/docs/readme.md")))
        self.assertFalse(is_allowed_external_link(QUrl("javascript:alert(1)")))
        self.assertFalse(is_allowed_external_link(QUrl("data:text/html,<script></script>")))
        self.assertFalse(is_allowed_external_link(QUrl("qrc:///qtwebchannel/qwebchannel.js")))

    def test_supported_drop_file_accepts_markdown_and_text_files_only(self):
        fixture_dir = Path(__file__).resolve().parent / "fixtures"
        markdown_file = fixture_dir / "markdown_showcase.md"
        uppercase_markdown_file = fixture_dir / "drop-note.MARKDOWN"
        text_file = fixture_dir / "drop-note.txt"
        uppercase_markdown_file.write_text("# uppercase suffix", encoding="utf-8")
        text_file.write_text("plain text", encoding="utf-8")
        self.addCleanup(uppercase_markdown_file.unlink)
        self.addCleanup(text_file.unlink)

        self.assertTrue(is_supported_drop_file(markdown_file))
        self.assertTrue(is_supported_drop_file(uppercase_markdown_file))
        self.assertTrue(is_supported_drop_file(text_file))
        self.assertFalse(is_supported_drop_file(fixture_dir))
        self.assertFalse(is_supported_drop_file(markdown_file.with_suffix(".html")))

    def test_supported_drop_path_selects_first_supported_local_path(self):
        fixture_dir = Path(__file__).resolve().parent / "fixtures"
        unsupported_file = fixture_dir / "drop-note.html"
        text_file = fixture_dir / "drop-note.txt"
        unsupported_file.write_text("<p>ignored</p>", encoding="utf-8")
        text_file.write_text("plain text", encoding="utf-8")
        self.addCleanup(unsupported_file.unlink)
        self.addCleanup(text_file.unlink)

        self.assertEqual(
            text_file,
            supported_drop_path(
                [
                    QUrl("https://example.com/readme.md"),
                    QUrl.fromLocalFile(str(unsupported_file)),
                    QUrl.fromLocalFile(str(text_file)),
                ]
            ),
        )
        self.assertEqual(fixture_dir, supported_drop_path([QUrl.fromLocalFile(str(fixture_dir))]))
        self.assertIsNone(supported_drop_path([QUrl.fromLocalFile(str(unsupported_file))]))

    def test_render_markdown_strips_dangerous_raw_html_tags(self):
        document = render_markdown("<iframe src='https://example.com'></iframe>\n\n<object></object>")

        self.assertNotIn("<iframe", document.lower())
        self.assertNotIn("<object", document.lower())

    def test_render_markdown_does_not_load_mermaid_from_remote_cdn(self):
        document = render_markdown("```mermaid\ngraph TD\n  A-->B\n```")

        self.assertNotIn("cdn.jsdelivr.net", document)
        self.assertNotIn("unpkg.com", document)
        self.assertNotIn("mermaid.ink", document)

    def test_mermaid_script_tag_uses_local_asset(self):
        tag = mermaid_script_tag()

        self.assertIn("mermaid.min.js", tag)
        self.assertIn("file:///", tag)

    def test_render_markdown_adds_source_line_anchor_to_mermaid_blocks(self):
        document = render_markdown("# Title\n\n```mermaid\ngraph TD\n  A-->B\n```")

        self.assertIn('<div id="source-line-3" class="mermaid"', document)
        self.assertIn('data-source-line="3"', document)

    def test_prepare_markdown_for_preview_adds_source_line_anchors(self):
        prepared = prepare_markdown_for_preview("# Title\n\nParagraph")

        self.assertIn('<span id="source-line-1"', prepared)
        self.assertIn('<span id="source-line-3"', prepared)

    def test_prepare_markdown_for_preview_converts_mermaid_fences(self):
        prepared = prepare_markdown_for_preview("```mermaid\ngraph TD\n  A-->B\n```")

        self.assertIn('<div id="source-line-1" class="mermaid" data-source-line="1"', prepared)
        self.assertIn('data-mermaid-source="graph TD', prepared)
        self.assertIn("A--&gt;B", prepared)
        self.assertNotIn("```mermaid", prepared)

    def test_cache_paths_for_restart_targets_qt_and_app_caches(self):
        paths = cache_paths_for_restart(Path("C:/Users/Test/AppData/Local"), "MDReader", "MD Reader")
        path_text = [path.as_posix() for path in paths]

        self.assertIn("C:/Users/Test/AppData/Local/MDReader/MD Reader/WebEngine", path_text)
        self.assertNotIn("C:/Users/Test/AppData/Local/QtWebEngine/Default", path_text)

    def test_qt_application_identity_is_configured_before_cache_paths_are_used(self):
        app = FakeQtApplication()

        configure_qt_application_identity(app)

        self.assertEqual("MDReader", app.organization_name)
        self.assertEqual("MD Reader", app.application_name)
        self.assertEqual("MD Reader", app.application_display_name)

    def test_build_script_clears_mdreader_cache_and_blocks_running_dist_app(self):
        script = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("Assert-MDReaderNotRunning", script)
        self.assertIn("Remove-MDReaderCache", script)
        self.assertIn("MDReader\\MD Reader\\cache\\WebEngine", script)
        self.assertIn("cache\\WebEngine", script)
        self.assertIn("Close these processes before rebuilding", script)

    def test_editor_scroll_value_for_source_line_preserves_view_anchor(self):
        self.assertEqual(0, editor_scroll_value_for_source_line(1, visible_lines=20, maximum=100))
        self.assertEqual(46, editor_scroll_value_for_source_line(51, visible_lines=20, maximum=100))
        self.assertEqual(100, editor_scroll_value_for_source_line(200, visible_lines=20, maximum=100))

    def test_editor_preview_render_debounce_is_short_but_noticeable(self):
        self.assertGreaterEqual(PREVIEW_RENDER_DEBOUNCE_MS, 200)
        self.assertLessEqual(PREVIEW_RENDER_DEBOUNCE_MS, 500)

    def test_packaging_includes_vendored_mermaid_assets(self):
        root = Path(__file__).resolve().parents[1]
        build_script = (root / "build.ps1").read_text(encoding="utf-8")
        spec = (root / "MDReader.spec").read_text(encoding="utf-8")

        self.assertIn("mermaid.min.js", build_script)
        self.assertIn("mermaid.LICENSE.txt", build_script)
        self.assertIn("mermaid.min.js", spec)
        self.assertIn("mermaid.LICENSE.txt", spec)


if __name__ == "__main__":
    unittest.main()
