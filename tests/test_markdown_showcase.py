import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from md_reader.app import render_markdown


class MarkdownShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_path = Path(__file__).resolve().parent / "fixtures" / "markdown_showcase.md"
        cls.markdown_text = cls.fixture_path.read_text(encoding="utf-8")
        cls.document = render_markdown(cls.markdown_text, cls.fixture_path)

    def test_showcase_fixture_exists_and_covers_core_sections(self):
        self.assertIn("# Markdown Showcase", self.markdown_text)
        self.assertIn("## Tables", self.markdown_text)
        self.assertIn("## Mermaid", self.markdown_text)
        self.assertIn("## Unsafe HTML Samples", self.markdown_text)

    def test_showcase_renders_core_markdown_elements(self):
        document = self.document

        self.assertIn("<h1", document)
        self.assertIn("<h6", document)
        self.assertIn("<strong>bold text</strong>", document)
        self.assertIn("<em>italic text</em>", document)
        self.assertIn("<code>inline code</code>", document)
        self.assertIn("<blockquote>", document)
        self.assertIn("<ol>", document)
        self.assertIn("<ul>", document)
        self.assertIn("<hr>", document)

    def test_showcase_renders_tables_as_html_tables(self):
        document = self.document

        self.assertIn("<table>", document)
        self.assertIn("<thead>", document)
        self.assertIn("<tbody>", document)
        self.assertIn("<th>Feature</th>", document)
        self.assertIn("<td>Headings</td>", document)
        self.assertNotIn("| Feature | Status | Notes |", document)

    def test_showcase_preserves_code_and_mermaid_metadata(self):
        document = self.document

        self.assertIn("codehilite", document)
        self.assertIn('data-code-language="python"', document)
        self.assertIn('class="mermaid"', document)
        self.assertIn('data-mermaid-source=', document)
        self.assertIn("mermaid.min.js", document)
        self.assertNotIn("cdn.jsdelivr.net", document)
        self.assertNotIn("unpkg.com", document)

    def test_showcase_preview_controls_and_sanitization_are_present(self):
        document = self.document.lower()

        self.assertIn('contenteditable="true"', document)
        self.assertIn("copy-block-button", document)
        self.assertIn('if (tag === "hr")', self.document)
        self.assertNotIn("<script>window.__mdreader_unsafe_script_executed", document)
        self.assertNotIn("<iframe", document)
        self.assertNotIn("<object", document)
        self.assertNotIn('href="javascript:', document)
        self.assertNotIn('src="data:', document)


if __name__ == "__main__":
    unittest.main()
