from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import markdown
from pygments.formatters import HtmlFormatter
from PySide6.QtCore import QEvent, QObject, QPoint, QSettings, QStandardPaths, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from md_reader import __version__

try:
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel
except Exception:  # pragma: no cover - depends on optional QtWebEngine availability
    QWebEngineSettings = None
    QWebEngineProfile = None
    QWebEnginePage = None
    QWebEngineView = None
    QWebChannel = None


APP_NAME = "MD Reader"
MARKDOWN_FILTERS = ["*.md", "*.markdown", "*.mdown", "*.mkd"]
DROPPABLE_FILE_SUFFIXES = {".md", ".markdown", ".txt"}
MAX_RECENT_FILES = 8
PREVIEW_RENDER_DEBOUNCE_MS = 300
APPEARANCE_MODES = {"system", "light", "dark"}
MARKDOWN_VIEW_MODES = {"preview", "raw", "split"}
DEFAULT_VIEW_MODE_OPTIONS = MARKDOWN_VIEW_MODES | {"last-used"}
SMALL_SPLIT_WIDTH = 700
APPEARANCE_MODES = {"system", "light", "dark"}
MARKDOWN_VIEW_MODES = {"preview", "raw", "split"}
DEFAULT_VIEW_MODE_OPTIONS = MARKDOWN_VIEW_MODES | {"last-used"}

ALLOWED_PREVIEW_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
ALLOWED_PREVIEW_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "*": {"class", "id", "data-source-line", "data-mermaid-source"},
    "div": {"data-code-language"},
}
SKIP_PREVIEW_TAG_CONTENT = {"script", "style", "iframe", "object", "embed", "meta", "base"}
SAFE_LINK_PROTOCOLS = {"", "http", "https", "mailto", "file"}
SAFE_IMAGE_PROTOCOLS = {"", "file"}
EXTERNAL_LINK_PROTOCOLS = {"http", "https", "mailto", "file"}


def default_reader_settings() -> dict[str, str]:
    return {
        "appearanceMode": "system",
        "defaultViewMode": "preview",
        "lastUsedViewMode": "preview",
    }


def normalize_appearance_mode(value: object) -> str:
    return value if isinstance(value, str) and value in APPEARANCE_MODES else "system"


def normalize_view_mode(value: object) -> str:
    return value if isinstance(value, str) and value in MARKDOWN_VIEW_MODES else "preview"


def normalize_default_view_mode(value: object) -> str:
    return value if isinstance(value, str) and value in DEFAULT_VIEW_MODE_OPTIONS else "preview"


def view_mode_for_default(default_view_mode: str, last_used_view_mode: str) -> str:
    default_view_mode = normalize_default_view_mode(default_view_mode)
    if default_view_mode == "last-used":
        return normalize_view_mode(last_used_view_mode)
    return normalize_view_mode(default_view_mode)


def slugify_heading(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def unique_heading_id(text: str, used_ids: dict[str, int]) -> str:
    base = slugify_heading(text)
    used_ids[base] = used_ids.get(base, 0) + 1
    if used_ids[base] == 1:
        return base
    return f"{base}-{used_ids[base]}"


def extract_markdown_headings(markdown_text: str) -> list[dict[str, object]]:
    headings: list[dict[str, object]] = []
    used_ids: dict[str, int] = {}
    in_code_fence = False
    code_fence_marker = ""
    for line_number, line in enumerate(markdown_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_code_fence:
                in_code_fence = True
                code_fence_marker = marker
            elif marker == code_fence_marker:
                in_code_fence = False
                code_fence_marker = ""
            continue
        if in_code_fence:
            continue
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        text = html.unescape(text)
        if not text:
            continue
        headings.append(
            {
                "id": unique_heading_id(text, used_ids),
                "level": len(match.group(1)),
                "text": text,
                "source_line": line_number,
            }
        )
    return headings


def assign_heading_ids(fragment: str, headings: list[dict[str, object]]) -> str:
    heading_iter = iter(enumerate(headings))

    def replace_heading(match: re.Match[str]) -> str:
        try:
            index, heading = next(heading_iter)
        except StopIteration:
            return match.group(0)
        level = match.group(1)
        attrs = re.sub(r'\s+id="[^"]*"', "", match.group(2) or "")
        content = match.group(3)
        heading_id = html.escape(str(heading["id"]), quote=True)
        source_line = html.escape(str(heading.get("source_line", "")), quote=True)
        label = html.escape(str(heading["text"]), quote=True)
        toggle = (
            f'<button type="button" class="mdreader-section-toggle md-reader-collapse-toggle" '
            f'aria-label="Collapse section {label}" aria-expanded="true" '
            f'contenteditable="false">&#9662;</button>'
        )
        return (
            f'<h{level} id="{heading_id}" data-heading-index="{index}" '
            f'data-source-line="{source_line}"{attrs}>{toggle}{content}</h{level}>'
        )

    return re.sub(r"<h([1-6])([^>]*)>(.*?)</h\1>", replace_heading, fragment, flags=re.DOTALL)


def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def document_navigator_html(headings: list[dict[str, object]]) -> str:
    if len(headings) < 2:
        return ""

    links: list[str] = []
    markers: list[str] = []
    marker_count = max(1, len(headings) - 1)
    for index, heading in enumerate(headings):
        heading_id = html.escape(str(heading["id"]), quote=True)
        text = html.escape(str(heading["text"]))
        level = int(heading["level"])
        indent = max(0, level - 1) * 14 + 6
        links.append(
            f'<a href="#{heading_id}" data-heading-id="{heading_id}" '
            f'style="padding-left: {indent}px">{text}</a>'
        )
        top = round((index / marker_count) * 100, 2)
        markers.append(
            f'<span class="mdreader-minimap-marker md-reader-minimap-marker '
            f'mdreader-minimap-line md-reader-minimap-line is-heading" '
            f'data-heading-id="{heading_id}" title="{html.escape(str(heading["text"]), quote=True)}" '
            f'data-minimap-label="{html.escape(str(heading["text"]), quote=True)}" '
            f'data-heading-level="{level}" '
            f'style="top: {top}%"></span>'
        )

    toc = (
        '<nav class="mdreader-navigator md-reader-navigator" aria-label="Document navigation">'
        '<div class="mdreader-nav-mode md-reader-nav-mode" role="group" aria-label="Navigation view">'
        '<button type="button" class="mdreader-contents-button md-reader-contents-button" '
        'aria-expanded="false" aria-controls="mdreader-contents-overlay" '
        'aria-pressed="false" title="Ctrl+K">Contents</button>'
        '<button type="button" class="mdreader-minimap-button md-reader-minimap-button" '
        'aria-pressed="true">Minimap</button>'
        '</div>'
        '<div id="mdreader-contents-overlay" class="mdreader-contents-overlay md-reader-toc" '
        'role="dialog" aria-label="Document contents">'
        '<p class="md-reader-toc-title">Contents</p>'
        f'{"".join(links)}'
        '<div class="md-reader-section-actions mdreader-section-actions">'
        '<button type="button" class="mdreader-collapse-all md-reader-section-action">Collapse all</button>'
        '<button type="button" class="mdreader-expand-all md-reader-section-action">Expand all</button>'
        '</div>'
        '</div>'
        '</nav>'
    )
    minimap = ""
    if len(headings) >= 2:
        minimap = (
            '<div class="mdreader-minimap md-reader-minimap" aria-label="Document mini-map">'
            '<div class="mdreader-minimap-canvas md-reader-minimap-canvas">'
            f'{"".join(markers)}'
            '</div>'
            '<div class="mdreader-minimap-tooltip md-reader-minimap-tooltip" role="tooltip"></div>'
            '</div>'
        )
    return f"{toc}{minimap}"


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def app_cache_root() -> Path:
    cache_location = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    if cache_location:
        return Path(cache_location)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MDReader" / APP_NAME
    return Path(tempfile.gettempdir()) / "MDReader" / APP_NAME


def webengine_cache_root() -> Path:
    return app_cache_root() / "WebEngine"


def configure_qt_application_identity(app: QApplication) -> None:
    app.setOrganizationName("MDReader")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)


def is_safe_url(value: str, allowed_protocols: set[str]) -> bool:
    cleaned = "".join(ch for ch in html.unescape(value).strip() if ch >= " ")
    scheme = urlsplit(cleaned).scheme.lower()
    return scheme in allowed_protocols


def is_allowed_external_link(url: QUrl) -> bool:
    return url.scheme().lower() in EXTERNAL_LINK_PROTOCOLS


def is_supported_drop_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in DROPPABLE_FILE_SUFFIXES


def supported_drop_path(urls) -> Path | None:
    for url in urls:
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_dir() or is_supported_drop_file(path):
            return path
    return None


@dataclass(frozen=True)
class ReaderSettings:
    appearance_mode: str = "system"
    default_view_mode: str = "preview"
    last_used_view_mode: str = "preview"

    def open_view_mode(self) -> str:
        if self.default_view_mode == "last-used":
            return self.last_used_view_mode
        return self.default_view_mode


def _settings_value(source, key: str, default: str) -> str:
    if isinstance(source, QSettings):
        value = source.value(key, default)
    else:
        value = source.get(key, default)
    return str(value) if value is not None else default


def load_reader_settings(source) -> ReaderSettings:
    appearance_mode = _settings_value(source, "appearanceMode", "system")
    default_view_mode = _settings_value(source, "defaultViewMode", "preview")
    last_used_view_mode = _settings_value(source, "lastUsedViewMode", "preview")
    if appearance_mode not in APPEARANCE_MODES:
        appearance_mode = "system"
    if default_view_mode not in DEFAULT_VIEW_MODE_OPTIONS:
        default_view_mode = "preview"
    if last_used_view_mode not in MARKDOWN_VIEW_MODES:
        last_used_view_mode = "preview"
    return ReaderSettings(appearance_mode, default_view_mode, last_used_view_mode)


def save_reader_settings(store: QSettings, reader_settings: ReaderSettings) -> None:
    store.setValue("appearanceMode", reader_settings.appearance_mode)
    store.setValue("defaultViewMode", reader_settings.default_view_mode)
    store.setValue("lastUsedViewMode", reader_settings.last_used_view_mode)


class PreviewHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in SKIP_PREVIEW_TAG_CONTENT:
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return
        if tag not in ALLOWED_PREVIEW_TAGS:
            return
        clean_attrs = self._clean_attrs(tag, attrs)
        attrs_text = "".join(
            f' {name}="{html.escape(value, quote=True)}"'
            for name, value in clean_attrs
        )
        self.parts.append(f"<{tag}{attrs_text}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in ALLOWED_PREVIEW_TAGS and not self.skip_stack:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if tag == self.skip_stack[-1]:
                self.skip_stack.pop()
            return
        if tag in ALLOWED_PREVIEW_TAGS and tag not in {"br", "hr", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.skip_stack:
            self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(f"&#{name};")

    def _clean_attrs(self, tag: str, attrs) -> list[tuple[str, str]]:
        allowed = ALLOWED_PREVIEW_ATTRS.get("*", set()) | ALLOWED_PREVIEW_ATTRS.get(tag, set())
        clean_attrs: list[tuple[str, str]] = []
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if name not in allowed:
                continue
            if name == "href" and not is_safe_url(value, SAFE_LINK_PROTOCOLS):
                continue
            if name == "src" and not is_safe_url(value, SAFE_IMAGE_PROTOCOLS):
                continue
            clean_attrs.append((name, value))
        return clean_attrs


def sanitize_preview_html(fragment: str) -> str:
    sanitizer = PreviewHtmlSanitizer()
    sanitizer.feed(fragment)
    sanitizer.close()
    return "".join(sanitizer.parts)


def is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped or "-" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def is_markdown_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and is_markdown_table_separator(lines[index + 1])
    )


def is_markdown_blockquote_line(line: str) -> bool:
    return line.lstrip().startswith(">")


def is_markdown_thematic_break(line: str) -> bool:
    return re.fullmatch(r"\s{0,3}([-*_])(?:\s*\1){2,}\s*", line) is not None


BASE_CSS = """
:root {
  color-scheme: light dark;
}
body {
  margin: 0;
  padding: 32px;
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.55;
  color: #1f2933;
  background: #ffffff;
}
main {
  max-width: 920px;
  margin: 0 auto;
}
h1, h2, h3, h4, h5, h6 {
  line-height: 1.25;
  margin: 1.45em 0 0.45em;
  color: #111827;
}
h1 {
  margin-top: 0;
  padding-bottom: 0.25em;
  border-bottom: 1px solid #d8dee4;
}
a {
  color: #0969da;
}
blockquote {
  margin: 1em 0;
  padding: 0 1em;
  color: #57606a;
  border-left: 4px solid #d0d7de;
}
pre {
  overflow: auto;
  padding: 14px 16px;
  border-radius: 6px;
  background: #f6f8fa;
}
code {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 0.92em;
}
:not(pre) > code {
  padding: 0.12em 0.35em;
  border-radius: 4px;
  background: #eff1f3;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
}
th, td {
  border: 1px solid #d0d7de;
  padding: 6px 10px;
}
th {
  background: #f6f8fa;
}
img {
  max-width: 100%;
}
hr {
  border: 0;
  border-top: 1px solid #d8dee4;
  margin: 2em 0;
}
:focus-visible {
  outline: 3px solid #0969da;
  outline-offset: 2px;
}
body[data-md-reader-theme="light"] {
  color: #1f2933;
  background: #ffffff;
}
body[data-md-reader-theme="dark"] {
  color: #d0d7de;
  background: #0d1117;
}
body[data-md-reader-theme="dark"] h1,
body[data-md-reader-theme="dark"] h2,
body[data-md-reader-theme="dark"] h3,
body[data-md-reader-theme="dark"] h4,
body[data-md-reader-theme="dark"] h5,
body[data-md-reader-theme="dark"] h6 {
  color: #f0f6fc;
}
body[data-md-reader-theme="dark"] h1,
body[data-md-reader-theme="dark"] th,
body[data-md-reader-theme="dark"] td,
body[data-md-reader-theme="dark"] hr {
  border-color: #30363d;
}
body[data-md-reader-theme="dark"] a {
  color: #58a6ff;
}
body[data-md-reader-theme="dark"] blockquote {
  color: #8b949e;
  border-color: #30363d;
}
body[data-md-reader-theme="dark"] pre,
body[data-md-reader-theme="dark"] th,
body[data-md-reader-theme="dark"] :not(pre) > code {
  background: #161b22;
}
body[data-md-reader-theme="dark"] :focus-visible {
  outline-color: #79c0ff;
}
@media (prefers-color-scheme: dark) {
  body[data-md-reader-theme="system"] {
    color: #d0d7de;
    background: #0d1117;
  }
  body[data-md-reader-theme="system"] h1,
  body[data-md-reader-theme="system"] h2,
  body[data-md-reader-theme="system"] h3,
  body[data-md-reader-theme="system"] h4,
  body[data-md-reader-theme="system"] h5,
  body[data-md-reader-theme="system"] h6 {
    color: #f0f6fc;
  }
  body[data-md-reader-theme="system"] h1,
  body[data-md-reader-theme="system"] th,
  body[data-md-reader-theme="system"] td,
  body[data-md-reader-theme="system"] hr {
    border-color: #30363d;
  }
  body[data-md-reader-theme="system"] a {
    color: #58a6ff;
  }
  body[data-md-reader-theme="system"] blockquote {
    color: #8b949e;
    border-color: #30363d;
  }
  body[data-md-reader-theme="system"] pre,
  body[data-md-reader-theme="system"] th,
  body[data-md-reader-theme="system"] :not(pre) > code {
    background: #161b22;
  }
  body[data-md-reader-theme="system"] :focus-visible {
    outline-color: #79c0ff;
  }
}
"""

def mermaid_script_tag() -> str:
    mermaid_path = resource_path("assets/mermaid.min.js")
    if not mermaid_path.exists():
        return ""
    return f'<script src="{html.escape(mermaid_path.resolve().as_uri(), quote=True)}"></script>'


PREVIEW_SCRIPT = """
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
(function () {
  let bridge = null;
  let syncTimer = null;
  let scrollTimer = null;
  let lastReportedSourceLine = null;
  let lastActiveTable = null;
  let suppressScrollReportsUntil = 0;
  const editable = () => document.getElementById("preview-content");

  function initBridge() {
    if (typeof QWebChannel === "undefined" || !window.qt || !window.qt.webChannelTransport) {
      return;
    }
    new QWebChannel(window.qt.webChannelTransport, function (channel) {
      bridge = channel.objects.previewBridge;
    });
  }

  function textContentWithoutCopyButton(element) {
    const clone = element.cloneNode(true);
    clone.querySelectorAll(".copy-block-button, .md-reader-collapse-toggle").forEach((button) => button.remove());
    return clone.innerText || clone.textContent || "";
  }

  function installCopyButtons() {
    document.querySelectorAll(".copy-block-button").forEach((button) => button.remove());
    const blocks = document.querySelectorAll("pre, p, blockquote, li, h1, h2, h3, h4, h5, h6, .mermaid");
    blocks.forEach((block) => {
      if (block.closest(".copy-button-skip")) {
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "copy-block-button";
      button.contentEditable = "false";
      button.textContent = "Copy";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const text = textContentWithoutCopyButton(block).trimEnd();
        if (bridge && bridge.copyText) {
          bridge.copyText(text);
        } else if (navigator.clipboard) {
          navigator.clipboard.writeText(text);
        }
      });
      block.appendChild(button);
    });
  }

  function escapeMarkdownText(text) {
    return text.replace(/\u00a0/g, " ");
  }

  function inlineMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return escapeMarkdownText(node.nodeValue || "");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }
    const tag = node.tagName.toLowerCase();
    if (tag === "button" && (node.classList.contains("copy-block-button") || node.classList.contains("md-reader-collapse-toggle"))) {
      return "";
    }
    if (tag === "input" && node.classList.contains("mdreader-task-checkbox")) {
      return node.checked ? "[X] " : "[ ] ";
    }
    if (tag === "br") {
      return "\\n";
    }
    const children = Array.from(node.childNodes).map(inlineMarkdown).join("");
    if (tag === "strong" || tag === "b") {
      return `**${children}**`;
    }
    if (tag === "em" || tag === "i") {
      return `*${children}*`;
    }
    if (tag === "code") {
      return `\\`${textContentWithoutCopyButton(node)}\\``;
    }
    if (tag === "a") {
      return `[${children}](${node.getAttribute("href") || ""})`;
    }
    if (tag === "img") {
      return `![${node.getAttribute("alt") || ""}](${node.getAttribute("src") || ""})`;
    }
    return children;
  }

  function blockMarkdown(node, index) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.nodeValue.trim() ? node.nodeValue : "";
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }
    const tag = node.tagName.toLowerCase();
    if (tag === "span" && node.classList.contains("source-line-anchor")) {
      return "";
    }
    if (tag === "div" && node.classList.contains("mermaid")) {
      return "```mermaid\\n" + (node.getAttribute("data-mermaid-source") || textContentWithoutCopyButton(node)).trim() + "\\n```";
    }
    if (tag === "div" && node.classList.contains("codehilite")) {
      const code = node.querySelector("code");
      const language = node.getAttribute("data-code-language");
      const fence = language ? "```" + language : "```";
      return fence + "\\n" + (code ? textContentWithoutCopyButton(code) : textContentWithoutCopyButton(node)).trimEnd() + "\\n```";
    }
    if (/^h[1-6]$/.test(tag)) {
      return "#".repeat(Number(tag.substring(1))) + " " + inlineMarkdown(node).trim();
    }
    if (tag === "p") {
      return inlineMarkdown(node).trim();
    }
    if (tag === "pre") {
      const code = node.querySelector("code");
      const language = code && code.className.match(/language-([A-Za-z0-9_-]+)/);
      const fence = language ? "```" + language[1] : "```";
      return fence + "\\n" + textContentWithoutCopyButton(code || node).trimEnd() + "\\n```";
    }
    if (tag === "blockquote") {
      return textContentWithoutCopyButton(node).trim().split("\\n").map((line) => "> " + line).join("\\n");
    }
    if (tag === "hr") {
      return "---";
    }
    if (tag === "ul") {
      return Array.from(node.children).map((child) => "- " + inlineMarkdown(child).trim()).join("\\n");
    }
    if (tag === "ol") {
      return Array.from(node.children).map((child, childIndex) => `${childIndex + 1}. ${inlineMarkdown(child).trim()}`).join("\\n");
    }
    if (tag === "table") {
      const rows = Array.from(node.querySelectorAll("tr")).map((row) => Array.from(row.children).map((cell) => inlineMarkdown(cell).trim()));
      if (!rows.length) {
        return "";
      }
      const header = "| " + rows[0].join(" | ") + " |";
      const divider = "| " + rows[0].map(() => "---").join(" | ") + " |";
      const body = rows.slice(1).map((row) => "| " + row.join(" | ") + " |").join("\\n");
      return [header, divider, body].filter(Boolean).join("\\n");
    }
    return Array.from(node.childNodes).map(blockMarkdown).filter(Boolean).join("\\n\\n");
  }

  function documentMarkdown() {
    const root = editable();
    if (!root) {
      return "";
    }
    return Array.from(root.childNodes).map(blockMarkdown).filter((text) => text.trim()).join("\\n\\n").trimEnd() + "\\n";
  }

  function syncToEditor() {
    if (syncTimer) {
      window.clearTimeout(syncTimer);
    }
    syncTimer = window.setTimeout(() => {
      if (bridge && bridge.previewChanged) {
        bridge.previewChanged(documentMarkdown());
      }
      installCopyButtons();
      installTaskCheckboxes();
      renderMermaid();
    }, 160);
  }

  function renderMermaid() {
    if (typeof mermaid === "undefined") {
      return;
    }
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
    mermaid.run({ querySelector: ".mermaid" }).catch(function () {});
  }

  function selectedText() {
    const selection = window.getSelection();
    return selection && selection.rangeCount ? selection.toString() : "";
  }

  function visibleSourceLine() {
    const anchors = Array.from(document.querySelectorAll("[data-source-line]"));
    if (!anchors.length) {
      return null;
    }
    const targetY = Math.max(0, window.innerHeight * 0.22);
    let best = anchors[0];
    let bestDistance = Number.POSITIVE_INFINITY;
    anchors.forEach((anchor) => {
      const rect = anchor.getBoundingClientRect();
      const distance = Math.abs(rect.top - targetY);
      if (rect.bottom >= 0 && rect.top <= window.innerHeight && distance < bestDistance) {
        best = anchor;
        bestDistance = distance;
      }
    });
    return Number(best.getAttribute("data-source-line"));
  }

  function reportPreviewScroll() {
    if (Date.now() < suppressScrollReportsUntil) {
      return;
    }
    if (scrollTimer) {
      window.clearTimeout(scrollTimer);
    }
    scrollTimer = window.setTimeout(() => {
      const line = visibleSourceLine();
      if (line && line !== lastReportedSourceLine) {
        lastReportedSourceLine = line;
        if (bridge && bridge.previewScrolled) {
          bridge.previewScrolled(line);
        }
      }
    }, 80);
  }

  function copySelection() {
    const root = editable();
    const text = selectedText() || (root ? textContentWithoutCopyButton(root).trimEnd() : "");
    if (bridge && bridge.copyText) {
      bridge.copyText(text);
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
    }
  }

  function insertNodeAtSelection(node) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      editable().appendChild(node);
      return;
    }
    const range = selection.getRangeAt(0);
    range.deleteContents();
    range.insertNode(node);
    range.setStartAfter(node);
    range.setEndAfter(node);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function selectedTable() {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return null;
    }
    let node = selection.anchorNode;
    if (node && node.nodeType !== Node.ELEMENT_NODE) {
      node = node.parentElement;
    }
    return node ? node.closest("table") : null;
  }

  function activeTable() {
    return selectedTable() || lastActiveTable || document.querySelector("table");
  }

  function trackActiveTable(event) {
    const table = event.target && event.target.closest ? event.target.closest("table") : null;
    if (table) {
      lastActiveTable = table;
    }
  }

  function tableColumnCount(table) {
    const firstRow = table.querySelector("tr");
    return firstRow ? Math.max(1, firstRow.children.length) : 1;
  }

  function addTableRow() {
    const table = activeTable();
    if (!table) {
      return false;
    }
    const columnCount = tableColumnCount(table);
    let body = table.querySelector("tbody");
    if (!body) {
      body = document.createElement("tbody");
      table.appendChild(body);
    }
    const row = document.createElement("tr");
    for (let index = 0; index < columnCount; index += 1) {
      const cell = document.createElement("td");
      cell.textContent = "Value";
      row.appendChild(cell);
    }
    body.appendChild(row);
    lastActiveTable = table;
    return true;
  }

  function addTableColumn() {
    const table = activeTable();
    if (!table) {
      return false;
    }
    const columnNumber = tableColumnCount(table) + 1;
    table.querySelectorAll("tr").forEach((row, rowIndex) => {
      const cell = document.createElement(row.querySelector("th") ? "th" : "td");
      cell.textContent = rowIndex === 0 ? "Column " + columnNumber : "Value";
      row.appendChild(cell);
    });
    lastActiveTable = table;
    return true;
  }

  function wrapSelection(tagName, placeholder) {
    const selection = window.getSelection();
    const wrapper = document.createElement(tagName);
    if (selection && selection.rangeCount && !selection.isCollapsed) {
      const range = selection.getRangeAt(0);
      wrapper.appendChild(range.extractContents());
      range.insertNode(wrapper);
    } else {
      wrapper.textContent = placeholder;
      insertNodeAtSelection(wrapper);
    }
  }

  function findNearestSourceAnchor(lineNumber) {
    const line = Number(lineNumber);
    for (let offset = 0; offset <= 80; offset += 1) {
      let anchor = document.getElementById("source-line-" + (line + offset));
      if (anchor) {
        return anchor;
      }
      if (offset > 0) {
        anchor = document.getElementById("source-line-" + (line - offset));
        if (anchor) {
          return anchor;
        }
      }
    }
    return null;
  }

  window.mdReaderScrollToSourceLine = function (lineNumber) {
    const anchor = findNearestSourceAnchor(lineNumber);
    if (anchor) {
      suppressScrollReportsUntil = Date.now() + 350;
      lastReportedSourceLine = Number(anchor.getAttribute("data-source-line"));
      anchor.scrollIntoView({ block: "center", behavior: "auto" });
    }
  };

  window.mdReaderApplyFormat = function (command, options) {
    const root = editable();
    if (!root) {
      return;
    }
    root.focus();
    options = options || {};
    if (command === "heading") {
      document.execCommand("formatBlock", false, "H" + options.level);
    } else if (command === "bold") {
      document.execCommand("bold", false);
    } else if (command === "italic") {
      document.execCommand("italic", false);
    } else if (command === "inline-code") {
      wrapSelection("code", "code");
    } else if (command === "link") {
      document.execCommand("createLink", false, options.url || "https://example.com");
    } else if (command === "image") {
      document.execCommand("insertImage", false, options.source || "image.png");
    } else if (command === "bullets") {
      document.execCommand("insertUnorderedList", false);
    } else if (command === "numbers") {
      document.execCommand("insertOrderedList", false);
    } else if (command === "task") {
      document.execCommand("insertText", false, "- [ ] " + (selectedText() || "List item"));
    } else if (command === "quote") {
      document.execCommand("formatBlock", false, "BLOCKQUOTE");
    } else if (command === "code-block") {
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = selectedText() || "paste code here";
      pre.appendChild(code);
      insertNodeAtSelection(pre);
    } else if (command === "table") {
      const table = document.createElement("table");
      table.innerHTML = "<thead><tr><th>Column 1</th><th>Column 2</th></tr></thead><tbody><tr><td>Value</td><td>Value</td></tr></tbody>";
      insertNodeAtSelection(table);
      lastActiveTable = table;
    } else if (command === "add-table-row") {
      addTableRow();
    } else if (command === "add-table-column") {
      addTableColumn();
    }
    syncToEditor();
  };

  function installTaskCheckboxes() {
    document.querySelectorAll(".mdreader-task-checkbox").forEach((checkbox) => {
      if (checkbox.dataset.mdreaderTaskReady === "true") {
        return;
      }
      checkbox.dataset.mdreaderTaskReady = "true";
      checkbox.addEventListener("change", () => syncToEditor());
    });
  }

  window.mdReaderCopySelection = copySelection;

  function plainHeadingText(heading) {
    const clone = heading.cloneNode(true);
    clone.querySelectorAll(".copy-block-button, .md-reader-collapse-toggle").forEach((node) => node.remove());
    return (clone.innerText || clone.textContent || "").trim();
  }

  function currentHeadingId() {
    const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, h6"));
    let current = headings[0] || null;
    headings.forEach((heading) => {
      if (heading.getBoundingClientRect().top <= window.innerHeight * 0.28) {
        current = heading;
      }
    });
    return current ? current.id : "";
  }

  function updateCurrentSection() {
    const id = currentHeadingId();
    document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => {
      heading.classList.toggle("mdreader-current-section", heading.id === id);
    });
    document.querySelectorAll(".md-reader-toc a").forEach((link) => {
      const active = link.getAttribute("href") === "#" + id;
      link.setAttribute("aria-current", active ? "true" : "false");
    });
    document.querySelectorAll(".md-reader-minimap-marker").forEach((marker) => {
      marker.classList.toggle("mdreader-current-section", marker.getAttribute("data-heading-id") === id);
    });
  }

  function setSectionCollapsed(heading, collapsed) {
    const level = Number(heading.tagName.substring(1));
    const toggle = heading.querySelector(".md-reader-collapse-toggle");
    if (toggle) {
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      toggle.textContent = collapsed ? "▸" : "▾";
    }
    let node = heading.nextElementSibling;
    while (node) {
      if (/^H[1-6]$/.test(node.tagName) && Number(node.tagName.substring(1)) <= level) {
        break;
      }
      node.classList.toggle("md-reader-collapsed", collapsed);
      node.classList.toggle("mdreader-section-hidden", collapsed);
      node = node.nextElementSibling;
    }
  }

  function installCollapseControls() {
    document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => {
      let button = heading.querySelector(".md-reader-collapse-toggle");
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = "mdreader-section-toggle md-reader-collapse-toggle";
        button.textContent = "▾";
        button.setAttribute("aria-label", "Collapse section " + plainHeadingText(heading));
        button.setAttribute("aria-expanded", "true");
        button.contentEditable = "false";
        heading.insertBefore(button, heading.firstChild);
      }
      if (button.dataset.mdreaderCollapseReady === "true") {
        return;
      }
      button.dataset.mdreaderCollapseReady = "true";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const collapsed = button.getAttribute("aria-expanded") === "true";
        setSectionCollapsed(heading, collapsed);
      });
    });
  }

  let mdReaderNavigatorMode = "minimap";

  function setNavigatorMode(mode) {
    const nextMode = mode === "toc" || mode === "minimap" ? mode : "none";
    mdReaderNavigatorMode = nextMode;
    document.body.dataset.mdreaderNavMode = nextMode;
    const navigator = document.querySelector(".md-reader-navigator");
    const panel = navigator ? navigator.querySelector(".md-reader-toc") : null;
    const contentsButton = navigator ? navigator.querySelector(".md-reader-contents-button") : null;
    const minimapButton = navigator ? navigator.querySelector(".md-reader-minimap-button") : null;
    const minimap = document.querySelector(".md-reader-minimap");
    if (panel) {
      panel.toggleAttribute("open", nextMode === "toc");
    }
    if (contentsButton) {
      contentsButton.setAttribute("aria-expanded", nextMode === "toc" ? "true" : "false");
      contentsButton.setAttribute("aria-pressed", nextMode === "toc" ? "true" : "false");
    }
    if (minimapButton) {
      minimapButton.setAttribute("aria-pressed", nextMode === "minimap" ? "true" : "false");
    }
    if (minimap) {
      minimap.classList.toggle("is-nav-active", nextMode === "minimap");
    }
    updateCurrentSection();
  }
  window.setNavigatorMode = setNavigatorMode;

  function installToc(headings) {
    if (headings.length < 2) {
      return;
    }
    let navigator = document.querySelector(".md-reader-navigator");
    if (!navigator) {
      navigator = document.createElement("nav");
      navigator.className = "mdreader-navigator md-reader-navigator";
      navigator.setAttribute("aria-label", "Document navigation");
      navigator.innerHTML = '<div class="mdreader-nav-mode md-reader-nav-mode" role="group" aria-label="Navigation view"><button type="button" class="mdreader-contents-button md-reader-contents-button" aria-expanded="false" aria-controls="mdreader-contents-overlay" aria-pressed="false" title="Ctrl+K">Contents</button><button type="button" class="mdreader-minimap-button md-reader-minimap-button" aria-pressed="true">Minimap</button></div><div id="mdreader-contents-overlay" class="mdreader-contents-overlay md-reader-toc" role="dialog" aria-label="Document contents"><p class="md-reader-toc-title">Contents</p></div>';
      document.body.appendChild(navigator);
    }
    const button = navigator.querySelector(".md-reader-contents-button");
    const minimapButton = navigator.querySelector(".md-reader-minimap-button");
    const panel = navigator.querySelector(".md-reader-toc");
    if (!button || !panel) {
      return;
    }
    if (!panel.querySelector("a")) {
      headings.forEach((heading) => {
        const link = document.createElement("a");
        link.href = "#" + heading.id;
        link.dataset.headingId = heading.id;
        link.textContent = heading.text;
        link.style.paddingLeft = Math.max(0, (Number(heading.level) - 1) * 14 + 6) + "px";
        panel.appendChild(link);
      });
    }
    panel.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const target = document.querySelector(link.getAttribute("href"));
        if (target) {
          target.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        }
      });
    });
    const collapseAll = navigator.querySelector(".mdreader-collapse-all, .md-reader-section-action:first-of-type");
    const expandAll = navigator.querySelector(".mdreader-expand-all, .md-reader-section-action:last-of-type");
    if (collapseAll) {
      collapseAll.addEventListener("click", () => {
        document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => setSectionCollapsed(heading, true));
      });
    }
    if (expandAll) {
      expandAll.addEventListener("click", () => {
        document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => setSectionCollapsed(heading, false));
      });
    }

    function openToc(focusFirstLink) {
      setNavigatorMode("toc");
      const firstLink = panel.querySelector("a");
      if (focusFirstLink && firstLink) {
        firstLink.focus();
      }
      updateCurrentSection();
    }
    function closeToc() {
      setNavigatorMode("none");
      button.focus();
    }
    button.addEventListener("click", () => {
      setNavigatorMode(mdReaderNavigatorMode === "toc" ? "none" : "toc");
    });
    if (minimapButton) {
      minimapButton.addEventListener("click", () => setNavigatorMode(mdReaderNavigatorMode === "minimap" ? "none" : "minimap"));
    }
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (mdReaderNavigatorMode === "toc") {
          closeToc();
        } else {
          openToc(true);
        }
      } else if (event.key === "Escape" && panel.hasAttribute("open")) {
        closeToc();
      }
    });
    setNavigatorMode(mdReaderNavigatorMode);
  }

  function installMiniMap(headings) {
    if (headings.length < 2) {
      return;
    }
    let minimap = document.querySelector(".md-reader-minimap");
    if (!minimap) {
      minimap = document.createElement("div");
      minimap.className = "mdreader-minimap md-reader-minimap";
      minimap.setAttribute("aria-label", "Document mini-map");
      document.body.appendChild(minimap);
    }
    let canvas = minimap.querySelector(".md-reader-minimap-canvas");
    if (!canvas) {
      canvas = document.createElement("div");
      canvas.className = "mdreader-minimap-canvas md-reader-minimap-canvas";
      minimap.appendChild(canvas);
    }
    let tooltip = minimap.querySelector(".md-reader-minimap-tooltip");
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.className = "mdreader-minimap-tooltip md-reader-minimap-tooltip";
      tooltip.setAttribute("role", "tooltip");
      minimap.appendChild(tooltip);
    }

    function miniMapWidthForElement(element) {
      const textLength = (element.innerText || element.textContent || "").trim().length;
      const tag = element.tagName.toLowerCase();
      if (/h[1-6]/.test(tag)) {
        const level = Number(tag.substring(1));
        return Math.max(40, 86 - (level - 1) * 8);
      }
      if (tag === "table" || tag === "pre") {
        return 64;
      }
      if (tag === "li") {
        return Math.max(30, Math.min(62, textLength * 1.5));
      }
      return Math.max(26, Math.min(78, textLength * 1.2));
    }

    function miniMapLeftForElement(element) {
      const tag = element.tagName.toLowerCase();
      if (/h[1-6]/.test(tag)) {
        return 8 + (Number(tag.substring(1)) - 1) * 4;
      }
      if (tag === "li") {
        return 18;
      }
      if (tag === "blockquote") {
        return 12;
      }
      return 14;
    }

    function miniMapClassForElement(element) {
      const tag = element.tagName.toLowerCase();
      if (/h[1-6]/.test(tag)) {
        return "is-heading";
      }
      if (tag === "table") {
        return "is-table";
      }
      if (tag === "pre") {
        return "is-code";
      }
      if (tag === "li") {
        return "is-list";
      }
      if (tag === "blockquote") {
        return "is-quote";
      }
      return "is-text";
    }

    function compactMiniMapText(text) {
      const compacted = String(text || "").replace(/\s+/g, " ").trim();
      return compacted.length > 64 ? compacted.slice(0, 61) + "..." : compacted;
    }

    function miniMapLabelForElement(element, currentHeadingLabel) {
      const tag = element.tagName.toLowerCase();
      if (/h[1-6]/.test(tag)) {
        return plainHeadingText(element);
      }
      if (tag === "table") {
        return "Table";
      }
      if (tag === "pre") {
        return "Code block";
      }
      if (tag === "p" && element.querySelector("img") && compactMiniMapText(element.textContent) === "") {
        return "Image";
      }
      if (tag === "img") {
        return "Image";
      }
      if (tag === "li") {
        return compactMiniMapText(element.innerText || element.textContent) || "List item";
      }
      if (currentHeadingLabel) {
        return currentHeadingLabel;
      }
      return compactMiniMapText(element.innerText || element.textContent) || "Content";
    }

    function showMiniMapTooltip(line) {
      const label = line.getAttribute("data-minimap-label");
      if (!label) {
        return;
      }
      canvas.querySelectorAll(".md-reader-minimap-line.is-hovered").forEach((node) => node.classList.remove("is-hovered"));
      line.classList.add("is-hovered");
      tooltip.textContent = label;
      const rect = line.getBoundingClientRect();
      tooltip.style.top = Math.max(20, Math.min(window.innerHeight - 20, rect.top + rect.height / 2)) + "px";
      tooltip.classList.add("is-visible");
    }

    function hideMiniMapTooltip() {
      canvas.querySelectorAll(".md-reader-minimap-line.is-hovered").forEach((node) => node.classList.remove("is-hovered"));
      tooltip.classList.remove("is-visible");
    }

    function layoutMiniMap() {
      minimap.classList.toggle("is-visible", headings.length >= 5 || document.documentElement.scrollHeight >= window.innerHeight * 2.5);
      const mapHeight = canvas.clientHeight || minimap.clientHeight || 1;
      canvas.innerHTML = "";
      let currentHeadingLabel = "";
      Array.from(document.querySelectorAll("#preview-content > h1, #preview-content > h2, #preview-content > h3, #preview-content > h4, #preview-content > h5, #preview-content > h6, #preview-content > p, #preview-content li, #preview-content > table, #preview-content > pre, #preview-content > blockquote")).forEach((element) => {
        const line = document.createElement("span");
        const top = Math.max(0, Math.min(mapHeight - 2, (element.offsetTop / Math.max(1, document.documentElement.scrollHeight)) * mapHeight));
        const elementHeight = Math.max(2, Math.min(18, (element.offsetHeight / Math.max(1, document.documentElement.scrollHeight)) * mapHeight));
        const tag = element.tagName.toLowerCase();
        if (/h[1-6]/.test(tag)) {
          currentHeadingLabel = plainHeadingText(element);
        }
        line.className = "mdreader-minimap-line md-reader-minimap-line " + miniMapClassForElement(element);
        line.style.top = top + "px";
        line.style.left = miniMapLeftForElement(element) + "%";
        line.style.width = miniMapWidthForElement(element) + "%";
        line.style.height = (/h[1-6]/.test(tag) ? Math.max(3, elementHeight) : elementHeight) + "px";
        line.setAttribute("data-minimap-label", miniMapLabelForElement(element, currentHeadingLabel));
        if (/h[1-6]/.test(tag)) {
          line.className += " mdreader-minimap-marker md-reader-minimap-marker";
          line.dataset.headingId = element.id;
          line.dataset.headingLevel = tag.substring(1);
          line.title = plainHeadingText(element);
        }
        canvas.appendChild(line);
      });
      setNavigatorMode(mdReaderNavigatorMode);
    }

    canvas.addEventListener("mouseover", (event) => {
      const line = event.target.closest(".md-reader-minimap-line");
      if (line) {
        showMiniMapTooltip(line);
      }
    });
    canvas.addEventListener("mouseout", (event) => {
      if (!canvas.contains(event.relatedTarget)) {
        hideMiniMapTooltip();
      }
    });
    minimap.addEventListener("click", (event) => {
      const rect = minimap.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height)));
      window.scrollTo({ top: ratio * (document.documentElement.scrollHeight - window.innerHeight), behavior: "auto" });
    });
    window.addEventListener("resize", layoutMiniMap);
    window.setTimeout(layoutMiniMap, 80);
    window.setTimeout(layoutMiniMap, 360);
  }

  let findMarks = [];
  let currentFindIndex = -1;

  function clearFindMarks() {
    findMarks.forEach((mark) => {
      mark.replaceWith(document.createTextNode(mark.textContent || ""));
    });
    findMarks = [];
    currentFindIndex = -1;
    document.body.normalize();
  }

  function markTextMatches(term, caseSensitive) {
    clearFindMarks();
    if (!term) {
      return [];
    }
    const flags = caseSensitive ? "g" : "gi";
    const expression = new RegExp(term.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&"), flags);
    const walker = document.createTreeWalker(editable(), NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || !expression.test(node.nodeValue)) {
          expression.lastIndex = 0;
          return NodeFilter.FILTER_REJECT;
        }
        expression.lastIndex = 0;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }
    nodes.forEach((node) => {
      const fragment = document.createDocumentFragment();
      let lastIndex = 0;
      expression.lastIndex = 0;
      String(node.nodeValue).replace(expression, (match, offset) => {
        fragment.appendChild(document.createTextNode(String(node.nodeValue).slice(lastIndex, offset)));
        const mark = document.createElement("mark");
        mark.className = "md-reader-find-mark";
        mark.textContent = match;
        fragment.appendChild(mark);
        findMarks.push(mark);
        lastIndex = offset + match.length;
        return match;
      });
      fragment.appendChild(document.createTextNode(String(node.nodeValue).slice(lastIndex)));
      node.replaceWith(fragment);
    });
    return findMarks;
  }

  window.mdReaderClearFind = clearFindMarks;
  window.mdReaderFind = function (term, direction, caseSensitive) {
    const marks = markTextMatches(term, Boolean(caseSensitive));
    if (!marks.length) {
      return 0;
    }
    currentFindIndex = direction < 0 ? marks.length - 1 : 0;
    marks[currentFindIndex].classList.add("is-current");
    marks[currentFindIndex].scrollIntoView({ block: "center", behavior: "auto" });
    return marks.length;
  };
  window.mdReaderFindNext = function (direction) {
    if (!findMarks.length) {
      return 0;
    }
    findMarks[currentFindIndex]?.classList.remove("is-current");
    currentFindIndex = (currentFindIndex + direction + findMarks.length) % findMarks.length;
    findMarks[currentFindIndex].classList.add("is-current");
    findMarks[currentFindIndex].scrollIntoView({ block: "center", behavior: "auto" });
    return currentFindIndex + 1;
  };

  function mdReaderInstallNavigator() {
    const headings = window.mdReaderDocumentHeadings || [];
    installCollapseControls();
    installToc(headings);
    installMiniMap(headings);
    updateCurrentSection();
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(updateCurrentSection, { rootMargin: "-20% 0px -70% 0px" });
      document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => observer.observe(heading));
    } else {
      window.addEventListener("scroll", updateCurrentSection, { passive: true });
    }
  }

  const toggleSection = setSectionCollapsed;
  const installDocumentNavigator = mdReaderInstallNavigator;
  window.mdReaderInstallNavigator = mdReaderInstallNavigator;
  window.installDocumentNavigator = installDocumentNavigator;
  window.toggleSection = toggleSection;

  document.addEventListener("DOMContentLoaded", function () {
    initBridge();
    const root = editable();
    if (!root) {
      return;
    }
    root.addEventListener("focusin", function () {
      if (bridge && bridge.previewFocused) {
        bridge.previewFocused();
      }
    });
    root.addEventListener("input", syncToEditor);
    root.addEventListener("click", trackActiveTable);
    root.addEventListener("focusin", trackActiveTable);
    window.addEventListener("scroll", reportPreviewScroll, { passive: true });
    root.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
        event.preventDefault();
        copySelection();
      }
    });
    installCopyButtons();
    installTaskCheckboxes();
    mdReaderInstallNavigator();
    renderMermaid();
  });
})();
</script>
"""

PREVIEW_CSS = """
main[contenteditable="true"] {
  outline: none;
}
.source-line-anchor {
  display: inline-block;
  width: 0;
  height: 0;
  overflow: hidden;
}
.mdreader-task-checkbox {
  margin-right: 0.45em;
  vertical-align: -0.12em;
}
.mdreader-task-item {
  list-style-position: outside;
}
pre, p, blockquote, li, h1, h2, h3, h4, h5, h6, .mermaid {
  position: relative;
}
.copy-block-button {
  position: absolute;
  top: 0;
  right: 0;
  opacity: 0;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  padding: 3px 8px;
  color: #24292f;
  background: #f6f8fa;
  font-size: 12px;
  cursor: pointer;
}
pre:hover > .copy-block-button,
p:hover > .copy-block-button,
blockquote:hover > .copy-block-button,
li:hover > .copy-block-button,
h1:hover > .copy-block-button,
h2:hover > .copy-block-button,
h3:hover > .copy-block-button,
h4:hover > .copy-block-button,
h5:hover > .copy-block-button,
h6:hover > .copy-block-button,
.mermaid:hover > .copy-block-button {
  opacity: 1;
}
.mermaid {
  margin: 1em 0;
  padding: 16px;
  border-radius: 6px;
  background: #f6f8fa;
}
.md-reader-heading-row {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
}
.md-reader-collapse-toggle {
  flex: 0 0 auto;
  border: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  line-height: 1;
  cursor: pointer;
  opacity: 0.72;
}
.md-reader-collapse-toggle:focus-visible,
.md-reader-contents-button:focus-visible,
.md-reader-minimap-button:focus-visible,
.md-reader-toc a:focus-visible,
.md-reader-section-action:focus-visible {
  outline: 2px solid #0969da;
  outline-offset: 2px;
}
.md-reader-collapsed,
.mdreader-section-hidden {
  display: none !important;
}
.mdreader-current-section {
  scroll-margin-top: 14px;
}
.md-reader-navigator {
  position: fixed;
  right: 20px;
  top: 16px;
  z-index: 40;
  font-family: "Segoe UI", Arial, sans-serif;
}
.md-reader-nav-mode {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid #d0d7de;
  border-radius: 999px;
  background: rgba(246, 248, 250, 0.96);
  box-shadow: 0 8px 28px rgba(31, 41, 55, 0.16);
}
.md-reader-contents-button,
.md-reader-minimap-button,
.md-reader-section-action {
  border: 0;
  padding: 7px 12px;
  color: #24292f;
  background: transparent;
  cursor: pointer;
}
.md-reader-contents-button[aria-pressed="true"],
.md-reader-minimap-button[aria-pressed="true"] {
  color: #ffffff;
  background: #0969da;
}
.md-reader-section-action {
  border: 1px solid #d0d7de;
  border-radius: 999px;
  background: rgba(246, 248, 250, 0.96);
  box-shadow: 0 8px 28px rgba(31, 41, 55, 0.16);
}
.md-reader-toc {
  position: absolute;
  right: 0;
  top: 42px;
  display: none;
  width: min(250px, calc(100vw - 40px));
  max-height: min(56vh, 430px);
  overflow: auto;
  padding: 10px;
  border: 1px solid #d0d7de;
  border-radius: 10px;
  color: #24292f;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 48px rgba(31, 41, 55, 0.22);
}
.md-reader-toc[open] {
  display: block;
}
.md-reader-toc-title {
  margin: 0 0 6px;
  font-weight: 700;
}
.md-reader-toc a {
  display: block;
  padding: 4px 6px;
  border-radius: 6px;
  color: inherit;
  text-decoration: none;
}
.md-reader-toc a[aria-current="true"] {
  color: #0969da;
  background: #ddf4ff;
}
.md-reader-section-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.md-reader-minimap {
  position: fixed;
  top: 58px;
  right: 20px;
  display: none;
  width: 128px;
  height: min(258px, calc(100vh - 150px));
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid rgba(240, 246, 252, 0.08);
  border-radius: 2px;
  background: rgba(3, 5, 8, 0.94);
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.32);
  z-index: 35;
  cursor: pointer;
  overflow: hidden;
}
.md-reader-minimap.is-visible.is-nav-active {
  display: block;
}
.md-reader-minimap-canvas {
  position: relative;
  width: 100%;
  height: 100%;
}
.md-reader-minimap-line {
  position: absolute;
  display: block;
  min-height: 2px;
  border-radius: 1px;
  background: rgba(248, 250, 252, 0.88);
  pointer-events: auto;
}
.md-reader-minimap-line.is-heading {
  background: rgba(255, 255, 255, 0.98);
}
.md-reader-minimap-line.is-text {
  background: repeating-linear-gradient(
    to bottom,
    rgba(226, 232, 240, 0.72) 0,
    rgba(226, 232, 240, 0.72) 2px,
    transparent 2px,
    transparent 6px
  );
}
.md-reader-minimap-line.is-list {
  background: repeating-linear-gradient(
    to bottom,
    rgba(226, 232, 240, 0.8) 0,
    rgba(226, 232, 240, 0.8) 2px,
    transparent 2px,
    transparent 6px
  );
}
.md-reader-minimap-line.is-list::before {
  position: absolute;
  top: 0;
  left: -7px;
  width: 3px;
  height: 3px;
  border: 1px solid rgba(248, 250, 252, 0.9);
  border-radius: 50%;
  content: "";
}
.md-reader-minimap-line.is-table {
  min-height: 12px;
  border: 1px solid rgba(248, 250, 252, 0.9);
  background:
    linear-gradient(rgba(248, 250, 252, 0.75), rgba(248, 250, 252, 0.75)) 0 50% / 100% 1px no-repeat,
    linear-gradient(90deg, transparent 32%, rgba(248, 250, 252, 0.75) 32%, rgba(248, 250, 252, 0.75) 34%, transparent 34%, transparent 66%, rgba(248, 250, 252, 0.75) 66%, rgba(248, 250, 252, 0.75) 68%, transparent 68%);
}
.md-reader-minimap-line.is-code,
.md-reader-minimap-line.is-quote {
  background: rgba(148, 163, 184, 0.64);
}
.md-reader-minimap-marker.mdreader-current-section {
  background: #ffffff;
}
.md-reader-minimap-line.is-hovered {
  min-height: 5px;
  outline: 1px solid rgba(88, 166, 255, 0.95);
  outline-offset: 2px;
  background: #ffffff;
  z-index: 2;
}
.md-reader-minimap-tooltip {
  position: fixed;
  right: 184px;
  display: none;
  max-width: 220px;
  transform: translateY(-50%);
  padding: 6px 9px;
  border: 1px solid rgba(88, 166, 255, 0.65);
  border-radius: 6px;
  color: #f0f6fc;
  background: rgba(13, 17, 23, 0.96);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.32);
  font-size: 12px;
  line-height: 1.35;
  pointer-events: none;
  z-index: 45;
}
.md-reader-minimap-tooltip.is-visible {
  display: block;
}
.md-reader-find-mark {
  background: #fff3a3;
  color: #111827;
}
.md-reader-find-mark.is-current {
  background: #ffbf47;
}
@media (prefers-color-scheme: dark) {
  .md-reader-nav-mode {
    border-color: #30363d;
    background: rgba(22, 27, 34, 0.96);
  }
  .md-reader-contents-button,
  .md-reader-minimap-button,
  .md-reader-section-action {
    color: #f0f6fc;
    border-color: #30363d;
    background: rgba(22, 27, 34, 0.96);
  }
  .md-reader-toc {
    color: #f0f6fc;
    border-color: #30363d;
    background: rgba(13, 17, 23, 0.98);
  }
  .md-reader-toc a[aria-current="true"] {
    color: #79c0ff;
    background: #0c2d6b;
  }
}
@media (max-width: 760px) {
  .md-reader-minimap {
    display: none !important;
  }
}
"""


def prepare_markdown_for_preview(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    prepared: list[str] = []
    index = 0
    in_code_fence = False
    code_fence_marker = ""
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not in_code_fence and stripped.lower() in {"```mermaid", "~~~mermaid"}:
            source_line = index + 1
            fence = stripped[:3]
            diagram_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                diagram_lines.append(lines[index])
                index += 1
            diagram_source = chr(10).join(diagram_lines)
            prepared.append(
                f'<div id="source-line-{source_line}" class="mermaid" data-source-line="{source_line}" '
                f'data-mermaid-source="{html.escape(diagram_source, quote=True)}">'
                f"{html.escape(diagram_source)}</div>"
            )
        elif not in_code_fence and is_markdown_table_start(lines, index):
            marker = f'<div id="source-line-{index + 1}" class="source-line-anchor" data-source-line="{index + 1}"></div>'
            prepared.append(marker)
            prepared.append("")
            prepared.append(line)
            index += 1
            prepared.append(lines[index])
            index += 1
            while index < len(lines) and "|" in lines[index].strip():
                prepared.append(lines[index])
                index += 1
            index -= 1
        elif not in_code_fence and is_markdown_blockquote_line(line):
            marker = f'<div id="source-line-{index + 1}" class="source-line-anchor" data-source-line="{index + 1}"></div>'
            prepared.append(marker)
            prepared.append("")
            while index < len(lines) and is_markdown_blockquote_line(lines[index]):
                prepared.append(lines[index])
                index += 1
            index -= 1
        elif not in_code_fence and is_markdown_thematic_break(line):
            marker = f'<div id="source-line-{index + 1}" class="source-line-anchor" data-source-line="{index + 1}"></div>'
            prepared.append(marker)
            prepared.append("")
            prepared.append(line)
        elif not in_code_fence and stripped.startswith(("```", "~~~")):
            code_fence_marker = stripped[:3]
            in_code_fence = True
            marker = f'<span id="source-line-{index + 1}" class="source-line-anchor" data-source-line="{index + 1}"></span>'
            prepared.append(marker)
            prepared.append(line)
        elif in_code_fence:
            prepared.append(line)
            if stripped.startswith(code_fence_marker):
                in_code_fence = False
                code_fence_marker = ""
        elif stripped:
            marker = f'<span id="source-line-{index + 1}" class="source-line-anchor" data-source-line="{index + 1}"></span>'
            prepared.append(f"{html.escape(line, quote=False)}{marker}")
        else:
            prepared.append(line)
        index += 1
    return "\n".join(prepared)


def fenced_code_languages(markdown_text: str) -> list[str]:
    lines = markdown_text.splitlines()
    languages: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            language = stripped[3:].strip().split(maxsplit=1)[0] if stripped[3:].strip() else ""
            if language.lower() != "mermaid":
                languages.append(language)
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                index += 1
        index += 1
    return languages


def add_code_language_metadata(fragment: str, languages: list[str]) -> str:
    language_iter = iter(languages)

    def add_language(match: re.Match[str]) -> str:
        language = next(language_iter, "")
        if not language:
            return match.group(0)
        return f'{match.group(0)} data-code-language="{html.escape(language, quote=True)}"'

    return re.sub(r'<div class="codehilite"', add_language, fragment)


def render_task_checkboxes(fragment: str) -> str:
    def replace_task_marker(match: re.Match[str]) -> str:
        marker = match.group(1)
        checked = marker.lower() == "x"
        checked_attr = " checked" if checked else ""
        marker_text = "[x]" if checked else "[ ]"
        return (
            f'<li class="mdreader-task-item"><input type="checkbox" '
            f'class="mdreader-task-checkbox" data-task-marker="{marker_text}"{checked_attr} '
            f'contenteditable="false"> {match.group(2)}</li>'
        )

    return re.sub(r"<li>\[( |x|X)\]\s*(.*?)</li>", replace_task_marker, fragment, flags=re.DOTALL)


def cache_paths_for_restart(local_app_data: Path, organization: str, application: str) -> list[Path]:
    root = local_app_data / organization / application
    return [
        root / "WebEngine",
        root / "http_cache",
        root / "GPUCache",
    ]


def restart_command(argv: list[str]) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *argv[1:]]
    return [sys.executable, *argv]


def editor_scroll_value_for_source_line(line_number: int, visible_lines: int, maximum: int) -> int:
    anchor_offset = max(0, visible_lines // 5)
    return max(0, min(maximum, line_number - 1 - anchor_offset))


def find_match_spans(text: str, term: str, case_sensitive: bool = False) -> list[tuple[int, int]]:
    if not term:
        return []
    haystack = text if case_sensitive else text.lower()
    needle = term if case_sensitive else term.lower()
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index == -1:
            return spans
        end = index + len(term)
        spans.append((index, end))
        start = end


def next_match_index(matches: list[tuple[int, int]], cursor_position: int, backwards: bool = False) -> int:
    if not matches:
        return -1
    if backwards:
        for index in range(len(matches) - 1, -1, -1):
            if matches[index][0] < cursor_position:
                return index
        return len(matches) - 1
    for index, (start, _end) in enumerate(matches):
        if start >= cursor_position:
            return index
    return 0


def find_status_text(term: str, total: int, active_index: int) -> str:
    if not term:
        return ""
    if total <= 0:
        return "No matches"
    return f"{active_index + 1} of {total}"


def render_markdown(
    markdown_text: str,
    source_path: Path | None = None,
    appearance_mode: str = "system",
) -> str:
    if appearance_mode not in APPEARANCE_MODES:
        appearance_mode = "system"
    formatter = HtmlFormatter(style="github-dark")
    headings = extract_markdown_headings(markdown_text)
    code_languages = fenced_code_languages(markdown_text)
    body = markdown.markdown(
        prepare_markdown_for_preview(markdown_text),
        extensions=[
            "extra",
            "admonition",
            "codehilite",
            "fenced_code",
            "nl2br",
            "sane_lists",
            "toc",
        ],
        extension_configs={
            "codehilite": {
                "guess_lang": False,
                "use_pygments": True,
            }
        },
        output_format="html5",
    )
    body = add_code_language_metadata(body, code_languages)
    body = sanitize_preview_html(body)
    body = render_task_checkboxes(body)
    body = assign_heading_ids(body, headings)
    title = html.escape(source_path.name if source_path else APP_NAME)
    pygments_css = formatter.get_style_defs(".codehilite")
    headings_json = json_for_script(headings)
    navigator = document_navigator_html(headings)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{BASE_CSS}</style>
  <style>{PREVIEW_CSS}</style>
  <style>{pygments_css}</style>
</head>
<body data-md-reader-theme="{appearance_mode}">
  <main id="preview-content" contenteditable="true" spellcheck="false">{body}</main>
  <script type="application/json" id="mdreader-outline-data">{headings_json}</script>
  {navigator}
  {mermaid_script_tag()}
  <script>window.mdReaderDocumentHeadings = {headings_json};</script>
  {PREVIEW_SCRIPT}
</body>
</html>
"""


class PreviewBridge(QObject):
    def __init__(self, window: "MarkdownWindow") -> None:
        super().__init__(window)
        self.window = window

    @Slot(str)
    def previewChanged(self, markdown_text: str) -> None:
        self.window.apply_preview_markdown(markdown_text)

    @Slot()
    def previewFocused(self) -> None:
        self.window.set_active_edit_surface("preview")

    @Slot(str)
    def copyText(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.window.statusBar().showMessage("Copied block text", 2000)

    @Slot(int)
    def previewScrolled(self, line_number: int) -> None:
        self.window.sync_editor_to_preview_line(line_number)


if QWebEnginePage is not None:
    class PreviewPage(QWebEnginePage):
        def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:
            if navigation_type == QWebEnginePage.NavigationTypeLinkClicked:
                if is_allowed_external_link(url):
                    QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, navigation_type, is_main_frame)
else:
    PreviewPage = None


class MarkdownWindow(QMainWindow):
    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__()
        self.current_file: Path | None = None
        self.current_folder: Path | None = None
        self._loaded_mtime_ns: int | None = None
        self._current_text = ""
        self._dirty = False
        self._loading = False
        self._syncing_from_preview = False
        self._active_edit_surface = "editor"
        self._pending_preview_line: int | None = None
        self._syncing_editor_from_preview_scroll = False
        self._ignore_next_preview_scroll_line: int | None = None
        self._last_preview_scroll_line: int | None = None
        self._preview_render_pending = False
        self._preview_loading_visible = False
        self.settings = QSettings("MDReader", APP_NAME)
        self.reader_settings = load_reader_settings(self.settings)
        self.appearance_mode = self.reader_settings.appearance_mode
        self.view_mode = self.reader_settings.open_view_mode()
        self.setWindowTitle(APP_NAME)
        self.resize(1250, 820)
        self.setAcceptDrops(True)

        self.preview_render_timer = QTimer(self)
        self.preview_render_timer.setSingleShot(True)
        self.preview_render_timer.setInterval(PREVIEW_RENDER_DEBOUNCE_MS)
        self.preview_render_timer.timeout.connect(self.render_pending_preview)
        color_scheme_changed = getattr(QApplication.styleHints(), "colorSchemeChanged", None)
        if color_scheme_changed is not None:
            color_scheme_changed.connect(self.handle_system_color_scheme_changed)

        self.folder_model = QFileSystemModel(self)
        self.folder_model.setNameFilters(MARKDOWN_FILTERS)
        self.folder_model.setNameFilterDisables(False)

        self.file_tree = QTreeView()
        self.file_tree.setModel(self.folder_model)
        self.file_tree.setHeaderHidden(True)
        self.file_tree.doubleClicked.connect(self.open_tree_index)
        self.file_tree.activated.connect(self.open_tree_index)
        for column in range(1, self.folder_model.columnCount()):
            self.file_tree.hideColumn(column)

        self.folder_dock = QDockWidget("Markdown Files", self)
        self.folder_dock.setObjectName("markdownFilesDock")
        self.folder_dock.setWidget(self.file_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.folder_dock)
        self.folder_dock.hide()

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Open a Markdown file or folder to start editing.")
        self.editor.textChanged.connect(self.editor_changed)
        self.editor.cursorPositionChanged.connect(self.sync_preview_to_editor_cursor)
        self.editor.verticalScrollBar().valueChanged.connect(self.sync_preview_to_editor_scroll)
        self.editor.installEventFilter(self)

        if QWebEngineView is not None:
            if QWebEngineProfile is not None:
                profile = QWebEngineProfile.defaultProfile()
                profile_root = webengine_cache_root()
                profile.setCachePath(str(profile_root / "http_cache"))
                profile.setPersistentStoragePath(str(profile_root / "storage"))
            self.preview = QWebEngineView()
            if PreviewPage is not None:
                self.preview.setPage(PreviewPage(self.preview))
            if QWebEngineSettings is not None:
                settings = self.preview.settings()
                settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
                settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            if QWebChannel is not None:
                self.preview_channel = QWebChannel(self.preview.page())
                self.preview_bridge = PreviewBridge(self)
                self.preview_channel.registerObject("previewBridge", self.preview_bridge)
                self.preview.page().setWebChannel(self.preview_channel)
            self.preview.loadFinished.connect(self.apply_pending_preview_scroll)
        else:
            self.preview = QTextBrowser()
            self.preview.setOpenExternalLinks(True)

        self.preview_blur_effect = QGraphicsBlurEffect(self)
        self.preview_blur_effect.setBlurRadius(7)
        self.preview_blur_effect.setEnabled(False)
        self.preview.setGraphicsEffect(self.preview_blur_effect)

        self.preview_container = QWidget()
        self.preview_stack = QStackedLayout(self.preview_container)
        self.preview_stack.setStackingMode(QStackedLayout.StackAll)
        self.preview_stack.setContentsMargins(0, 0, 0, 0)
        self.preview_stack.addWidget(self.preview)
        self.preview_loading_overlay = QFrame()
        self.preview_loading_overlay.setObjectName("previewLoadingOverlay")
        self.preview_loading_overlay.setStyleSheet(
            """
            QFrame#previewLoadingOverlay {
                background: rgba(13, 17, 23, 210);
                border: none;
            }
            QLabel {
                color: white;
                font-size: 15px;
                font-weight: 600;
                padding: 10px 16px;
                border-radius: 6px;
                background: rgba(31, 41, 55, 220);
            }
            """
        )
        overlay_layout = QVBoxLayout(self.preview_loading_overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(QLabel("Rendering preview..."))
        self.preview_stack.addWidget(self.preview_loading_overlay)
        self.preview_loading_overlay.hide()

        self.find_bar = self._create_find_bar()
        self._find_matches: list[tuple[int, int]] = []
        self._find_active_index = -1
        self._find_preview_total = 0
        self._find_preview_active = 0

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.editor)
        self.main_splitter.addWidget(self.preview_container)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.find_bar, 0)
        central_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(central_widget)
        self._install_drop_targets(self.editor, self.preview, self.preview_container, self.main_splitter, central_widget)
        self.setStatusBar(QStatusBar(self))
        self._create_actions()
        self._create_format_toolbar()
        self.restore_settings()
        self.apply_appearance()
        self.apply_view_mode()

        if file_path:
            self.open_file(file_path)
        else:
            self.show_empty()

    def _create_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.pick_file)
        file_menu.addAction(open_action)

        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self.pick_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)

        reload_action = QAction("&Reload", self)
        reload_action.setShortcut(QKeySequence.Refresh)
        reload_action.triggered.connect(self.reload_file)
        file_menu.addAction(reload_action)

        restart_action = QAction("Restart Application", self)
        restart_action.triggered.connect(self.restart_application)
        file_menu.addAction(restart_action)

        export_html_action = QAction("Export &HTML...", self)
        export_html_action.triggered.connect(self.export_html)
        file_menu.addAction(export_html_action)

        file_menu.addSeparator()

        self.recent_menu = file_menu.addMenu("Recent &Files")
        self.refresh_recent_menu()

        file_menu.addSeparator()

        self.toggle_folder_action = self.folder_dock.toggleViewAction()
        self.toggle_folder_action.setText("Show Markdown &Files")
        file_menu.addAction(self.toggle_folder_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.editor.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self.editor.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self.editor.cut)
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.copy_active_selection)
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.editor.paste)
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        find_action = QAction("&Find...", self)
        find_action.setShortcut(QKeySequence.Find)
        find_action.triggered.connect(self.find_text)
        edit_menu.addAction(find_action)

        view_menu = self.menuBar().addMenu("&View")

        self.view_mode_action_group = QActionGroup(self)
        self.view_mode_action_group.setExclusive(True)
        self.preview_mode_action = self._add_checkable_action(
            view_menu,
            self.view_mode_action_group,
            "&Preview",
            "preview",
            lambda: self.set_view_mode("preview"),
            "Ctrl+1",
        )
        self.raw_mode_action = self._add_checkable_action(
            view_menu,
            self.view_mode_action_group,
            "&Raw",
            "raw",
            lambda: self.set_view_mode("raw"),
            "Ctrl+2",
        )
        self.split_mode_action = self._add_checkable_action(
            view_menu,
            self.view_mode_action_group,
            "&Split",
            "split",
            lambda: self.set_view_mode("split"),
            "Ctrl+3",
        )
        view_menu.addSeparator()

        default_view_menu = view_menu.addMenu("Default View &Mode")
        self.default_view_action_group = QActionGroup(self)
        self.default_view_action_group.setExclusive(True)
        self.default_preview_action = self._add_checkable_action(
            default_view_menu,
            self.default_view_action_group,
            "Preview-only",
            "preview",
            lambda: self.set_default_view_mode("preview"),
        )
        self.default_raw_action = self._add_checkable_action(
            default_view_menu,
            self.default_view_action_group,
            "Raw-only",
            "raw",
            lambda: self.set_default_view_mode("raw"),
        )
        self.default_split_action = self._add_checkable_action(
            default_view_menu,
            self.default_view_action_group,
            "Split",
            "split",
            lambda: self.set_default_view_mode("split"),
        )
        self.default_last_used_action = self._add_checkable_action(
            default_view_menu,
            self.default_view_action_group,
            "Last used",
            "last-used",
            lambda: self.set_default_view_mode("last-used"),
        )
        view_menu.addSeparator()

        appearance_menu = view_menu.addMenu("&Appearance")
        self.appearance_action_group = QActionGroup(self)
        self.appearance_action_group.setExclusive(True)
        self.system_appearance_action = self._add_checkable_action(
            appearance_menu,
            self.appearance_action_group,
            "System",
            "system",
            lambda: self.set_appearance_mode("system"),
        )
        self.light_appearance_action = self._add_checkable_action(
            appearance_menu,
            self.appearance_action_group,
            "Light",
            "light",
            lambda: self.set_appearance_mode("light"),
        )
        self.dark_appearance_action = self._add_checkable_action(
            appearance_menu,
            self.appearance_action_group,
            "Dark",
            "dark",
            lambda: self.set_appearance_mode("dark"),
        )
        view_menu.addSeparator()

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(lambda: self.change_editor_zoom(1))
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(lambda: self.change_editor_zoom(-1))
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("&Reset Zoom", self)
        reset_zoom_action.setShortcut("Ctrl+0")
        reset_zoom_action.triggered.connect(self.reset_editor_zoom)
        view_menu.addAction(reset_zoom_action)

        help_menu = self.menuBar().addMenu("&Help")

        help_action = QAction("&Markdown Help", self)
        help_action.setShortcut(QKeySequence.HelpContents)
        help_action.triggered.connect(self.show_markdown_help)
        help_menu.addAction(help_action)

        about_action = QAction("&About MD Reader", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _add_checkable_action(
        self,
        menu,
        group: QActionGroup,
        text: str,
        value: str,
        callback,
        shortcut: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.setCheckable(True)
        action.setData(value)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        group.addAction(action)
        menu.addAction(action)
        return action

    def _create_format_toolbar(self) -> None:
        toolbar = QToolBar("Markdown tools", self)
        toolbar.setObjectName("markdownToolsToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        toolbar.addAction(self.preview_mode_action)
        toolbar.addAction(self.raw_mode_action)
        toolbar.addAction(self.split_mode_action)
        toolbar.addSeparator()
        toolbar.addAction(self.system_appearance_action)
        toolbar.addAction(self.light_appearance_action)
        toolbar.addAction(self.dark_appearance_action)
        toolbar.addSeparator()
        self._add_format_action(toolbar, "H1", "Large title", lambda: self.format_heading(1), "Ctrl+Alt+1")
        self._add_format_action(toolbar, "H2", "Section heading", lambda: self.format_heading(2), "Ctrl+Alt+2")
        self._add_format_action(toolbar, "H3", "Small heading", lambda: self.format_heading(3), "Ctrl+Alt+3")
        toolbar.addSeparator()
        self._add_format_action(toolbar, "Bold", "Make selected text bold", self.format_bold, "Ctrl+B")
        self._add_format_action(toolbar, "Italic", "Make selected text italic", self.format_italic, "Ctrl+I")
        self._add_format_action(toolbar, "Code", "Format selected text as inline code", self.format_inline_code)
        toolbar.addSeparator()
        self._add_format_action(toolbar, "Link", "Add a clickable link", self.format_link, "Ctrl+K")
        self._add_format_action(toolbar, "Image", "Add an image by URL or file path", self.format_image)
        toolbar.addSeparator()
        self._add_format_action(toolbar, "Bullets", "Create a bullet list", lambda: self.format_line_prefix("- "))
        self._add_format_action(toolbar, "Numbers", "Create a numbered list", self.format_numbered_list)
        self._add_format_action(toolbar, "Task", "Create a checkbox task list", lambda: self.format_line_prefix("- [ ] "))
        toolbar.addSeparator()
        self._add_format_action(toolbar, "Quote", "Create a block quote", lambda: self.format_line_prefix("> "))
        self._add_format_action(toolbar, "Code Block", "Insert a fenced code block", self.format_code_block)
        self._add_format_action(toolbar, "Table", "Insert a simple table", self.format_table)
        self._add_format_action(toolbar, "Row", "Add a row to the active preview table", self.add_table_row)
        self._add_format_action(toolbar, "Column", "Add a column to the active preview table", self.add_table_column)

    def _add_format_action(
        self,
        toolbar: QToolBar,
        text: str,
        tooltip: str,
        callback,
        shortcut: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def _create_find_bar(self) -> QFrame:
        find_bar = QFrame()
        find_bar.setObjectName("findBar")
        find_bar.setMaximumHeight(48)
        find_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        find_bar.hide()
        layout = QHBoxLayout(find_bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        label = QLabel("Find")
        self.find_input = QLineEdit()
        self.find_input.setClearButtonEnabled(True)
        self.find_input.setPlaceholderText("Search document")
        self.find_input.textChanged.connect(lambda _text: self.perform_find(reset=True))
        self.find_input.returnPressed.connect(lambda: self.find_next(False))

        self.find_case_check = QCheckBox("Case")
        self.find_case_check.toggled.connect(lambda _checked: self.perform_find(reset=True))
        previous_button = QPushButton("Previous")
        previous_button.clicked.connect(lambda: self.find_next(True))
        next_button = QPushButton("Next")
        next_button.clicked.connect(lambda: self.find_next(False))
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.hide_find_bar)
        self.find_status = QLabel("")
        self.find_status.setMinimumWidth(80)

        layout.addWidget(label)
        layout.addWidget(self.find_input, 1)
        layout.addWidget(self.find_case_check)
        layout.addWidget(self.find_status)
        layout.addWidget(previous_button)
        layout.addWidget(next_button)
        layout.addWidget(close_button)

        close_shortcut = QShortcut(QKeySequence("Esc"), find_bar)
        close_shortcut.activated.connect(self.hide_find_bar)
        return find_bar

    def effective_theme(self) -> str:
        if self.appearance_mode in {"light", "dark"}:
            return self.appearance_mode
        color_scheme = getattr(QApplication.styleHints(), "colorScheme", lambda: None)()
        qt_color_scheme = getattr(Qt, "ColorScheme", None)
        if qt_color_scheme is not None and color_scheme == getattr(qt_color_scheme, "Dark", object()):
            return "dark"
        return "light"

    def set_appearance_mode(self, mode: str) -> None:
        if mode not in APPEARANCE_MODES:
            mode = "system"
        self.appearance_mode = mode
        self.reader_settings = ReaderSettings(
            appearance_mode=mode,
            default_view_mode=self.reader_settings.default_view_mode,
            last_used_view_mode=self.reader_settings.last_used_view_mode,
        )
        save_reader_settings(self.settings, self.reader_settings)
        self.apply_appearance()
        self.update_preview()

    def handle_system_color_scheme_changed(self, *_args) -> None:
        if self.appearance_mode != "system":
            return
        self.apply_appearance()
        self.update_preview()

    def apply_appearance(self) -> None:
        theme = self.effective_theme()
        if theme == "dark":
            background = "#0d1117"
            surface = "#161b22"
            text = "#d0d7de"
            muted = "#8b949e"
            border = "#30363d"
            focus = "#79c0ff"
            selection = "#1f6feb"
        else:
            background = "#ffffff"
            surface = "#f6f8fa"
            text = "#1f2933"
            muted = "#57606a"
            border = "#d0d7de"
            focus = "#0969da"
            selection = "#bfdbfe"
        self.setStyleSheet(
            f"""
            QMainWindow, QMenuBar, QMenu, QStatusBar {{
                background: {background};
                color: {text};
            }}
            QToolBar, QDockWidget {{
                background: {surface};
                color: {text};
                border: 1px solid {border};
            }}
            QPlainTextEdit, QTextBrowser, QTreeView {{
                background: {background};
                color: {text};
                selection-background-color: {selection};
                border: 1px solid {border};
                font-family: Consolas, "Cascadia Mono", monospace;
            }}
            QToolButton, QMenu::item {{
                color: {text};
                padding: 4px 8px;
            }}
            QToolButton:checked, QMenu::item:selected {{
                background: {selection};
                color: {text};
            }}
            QToolButton:focus, QPlainTextEdit:focus, QTextBrowser:focus, QTreeView:focus {{
                border: 2px solid {focus};
            }}
            QSplitter::handle {{
                background: {border};
            }}
            QLabel {{
                color: {muted};
            }}
            """
        )
        action_by_mode = {
            "system": self.system_appearance_action,
            "light": self.light_appearance_action,
            "dark": self.dark_appearance_action,
        }
        action_by_mode[self.appearance_mode].setChecked(True)

    def set_default_view_mode(self, mode: str) -> None:
        if mode not in DEFAULT_VIEW_MODE_OPTIONS:
            mode = "preview"
        self.reader_settings = ReaderSettings(
            appearance_mode=self.reader_settings.appearance_mode,
            default_view_mode=mode,
            last_used_view_mode=self.reader_settings.last_used_view_mode,
        )
        save_reader_settings(self.settings, self.reader_settings)
        self._sync_default_view_actions()

    def set_view_mode(self, mode: str) -> None:
        if mode not in MARKDOWN_VIEW_MODES:
            mode = "preview"
        scroll_value = self.editor.verticalScrollBar().value()
        self.view_mode = mode
        self.reader_settings = ReaderSettings(
            appearance_mode=self.reader_settings.appearance_mode,
            default_view_mode=self.reader_settings.default_view_mode,
            last_used_view_mode=mode,
        )
        save_reader_settings(self.settings, self.reader_settings)
        self.apply_view_mode()
        self.editor.verticalScrollBar().setValue(scroll_value)

    def apply_view_mode(self) -> None:
        self.editor.setVisible(self.view_mode in {"raw", "split"})
        self.preview_container.setVisible(self.view_mode in {"preview", "split"})
        if self.view_mode == "split" and self.width() < SMALL_SPLIT_WIDTH:
            self.main_splitter.setOrientation(Qt.Vertical)
        else:
            self.main_splitter.setOrientation(Qt.Horizontal)
        action_by_mode = {
            "preview": self.preview_mode_action,
            "raw": self.raw_mode_action,
            "split": self.split_mode_action,
        }
        action_by_mode[self.view_mode].setChecked(True)
        self._sync_default_view_actions()

    def _sync_default_view_actions(self) -> None:
        action_by_mode = {
            "preview": self.default_preview_action,
            "raw": self.default_raw_action,
            "split": self.default_split_action,
            "last-used": self.default_last_used_action,
        }
        action_by_mode[self.reader_settings.default_view_mode].setChecked(True)

    def new_file(self) -> None:
        if not self.confirm_discard_changes():
            return
        self.current_file = None
        self._loaded_mtime_ns = None
        self._current_text = ""
        self._set_editor_text("")
        self._set_dirty(False)
        self.update_preview()
        self.statusBar().showMessage("New unsaved Markdown file", 4000)

    def show_empty(self) -> None:
        self.current_file = None
        self.current_folder = None
        self._loaded_mtime_ns = None
        self.file_tree.setRootIndex(self.folder_model.index(""))
        self.folder_dock.hide()
        self._current_text = ""
        self._set_editor_text("")
        self._set_dirty(False)
        self.setWindowTitle(APP_NAME)
        self._set_html(render_markdown("# MD Reader\n\nOpen a Markdown file to preview it.", None, self.appearance_mode), None)

    def pick_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Markdown file",
            str(self.current_file.parent if self.current_file else self.current_folder or Path.home()),
            "Markdown files (*.md *.markdown *.mdown *.mkd);;All files (*.*)",
        )
        if file_name:
            self.open_file(Path(file_name), show_in_folder=False)

    def pick_folder(self) -> None:
        folder_name = QFileDialog.getExistingDirectory(
            self,
            "Open folder",
            str(self.current_folder or (self.current_file.parent if self.current_file else Path.home())),
        )
        if folder_name:
            self.open_folder(Path(folder_name))

    def reload_file(self) -> None:
        if self.current_file:
            self.open_file(self.current_file)

    def restart_application(self) -> None:
        if not self.confirm_discard_changes():
            return
        self.save_settings()
        if QWebEngineProfile is not None:
            try:
                QWebEngineProfile.defaultProfile().clearHttpCache()
            except RuntimeError:
                pass
        self.clear_application_cache()
        try:
            subprocess.Popen(restart_command(sys.argv), close_fds=True)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not restart application:\n\n{exc}")
            return
        QApplication.quit()

    def clear_application_cache(self) -> None:
        cache_root = app_cache_root()
        failures: list[Path] = []
        for cache_path in cache_paths_for_restart(cache_root.parent.parent, cache_root.parent.name, cache_root.name):
            if cache_path.exists():
                try:
                    shutil.rmtree(cache_path)
                except OSError:
                    failures.append(cache_path)
        if failures:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Some cache files could not be cleared before restart:\n\n"
                + "\n".join(str(path) for path in failures[:5]),
            )

    def save_file(self) -> bool:
        if self.current_file is None:
            return self.save_file_as()

        if self.file_changed_on_disk():
            result = QMessageBox.warning(
                self,
                APP_NAME,
                "This file changed on disk since you opened it.\n\nOverwrite the external changes?",
                QMessageBox.Save | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result != QMessageBox.Save:
                return False

        text = self.editor.toPlainText()
        try:
            self.atomic_write_text(self.current_file, text)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save file:\n{self.current_file}\n\n{exc}")
            return False

        self._current_text = text
        self._loaded_mtime_ns = self.file_mtime_ns(self.current_file)
        self._set_dirty(False)
        if self.current_folder and self._path_is_in_folder(self.current_file, self.current_folder):
            self.select_current_file()
        self.update_preview()
        self.add_recent_file(self.current_file)
        self.statusBar().showMessage(f"Saved {self.current_file}", 4000)
        return True

    def save_file_as(self) -> bool:
        initial_dir = self.current_file.parent if self.current_file else self.current_folder or Path.home()
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown file",
            str(initial_dir),
            "Markdown files (*.md);;All files (*.*)",
        )
        if not file_name:
            return False
        self.current_file = Path(file_name)
        return self.save_file()

    def export_html(self) -> None:
        initial_dir = self.current_file.parent if self.current_file else self.current_folder or Path.home()
        default_name = self.current_file.with_suffix(".html").name if self.current_file else "document.html"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export HTML",
            str(initial_dir / default_name),
            "HTML files (*.html *.htm);;All files (*.*)",
        )
        if not file_name:
            return
        output_path = Path(file_name)
        try:
            self.atomic_write_text(
                output_path,
                render_markdown(self.editor.toPlainText(), self.current_file or output_path, self.appearance_mode),
            )
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not export HTML:\n{output_path}\n\n{exc}")
            return
        self.statusBar().showMessage(f"Exported {output_path}", 5000)

    def open_folder(self, path: Path) -> None:
        if not path.exists() or not path.is_dir():
            QMessageBox.warning(self, APP_NAME, f"Folder does not exist:\n{path}")
            return
        self.set_current_folder(path)
        self.folder_dock.show()

    def open_file(self, path: Path, show_in_folder: bool = False) -> None:
        if not self.confirm_discard_changes():
            return
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="cp1252")
            except UnicodeDecodeError as exc:
                QMessageBox.critical(self, APP_NAME, f"Could not decode file:\n{path}\n\n{exc}")
                return
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open file:\n{path}\n\n{exc}")
            return

        self.current_file = path
        self._current_text = text
        if show_in_folder:
            if not self.current_folder or not self._path_is_in_folder(path, self.current_folder):
                self.set_current_folder(path.parent)
            self.folder_dock.show()
        else:
            self.current_folder = None
            self.file_tree.setRootIndex(self.folder_model.index(""))
            self.folder_dock.hide()
        self._set_editor_text(text)
        self._loaded_mtime_ns = self.file_mtime_ns(path)
        self._set_dirty(False)
        if show_in_folder:
            self.select_current_file()
        self.update_preview()
        self.add_recent_file(path)
        self.statusBar().showMessage(f"Opened {path}", 4000)

    def open_tree_index(self, index) -> None:
        path = Path(self.folder_model.filePath(index))
        if path.is_file():
            self.open_file(path, show_in_folder=True)

    def set_current_folder(self, path: Path) -> None:
        folder = path.resolve()
        if self.current_folder == folder:
            return
        self.current_folder = folder
        root_index = self.folder_model.setRootPath(str(folder))
        self.file_tree.setRootIndex(root_index)

    def select_current_file(self) -> None:
        if self.current_file is None:
            return
        index = self.folder_model.index(str(self.current_file))
        if index.isValid():
            self.file_tree.setCurrentIndex(index)
            self.file_tree.scrollTo(index)

    def _path_is_in_folder(self, path: Path, folder: Path) -> bool:
        try:
            path.resolve().relative_to(folder.resolve())
        except ValueError:
            return False
        return True

    def atomic_write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def file_mtime_ns(self, path: Path) -> int | None:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def file_changed_on_disk(self) -> bool:
        if self.current_file is None or self._loaded_mtime_ns is None or not self.current_file.exists():
            return False
        return self.file_mtime_ns(self.current_file) != self._loaded_mtime_ns

    def recent_files(self) -> list[Path]:
        values = self.settings.value("recentFiles", [], list)
        if isinstance(values, str):
            values = [values]
        return [Path(value) for value in values if value and Path(value).exists()]

    def add_recent_file(self, path: Path) -> None:
        resolved = path.resolve()
        recent = [item for item in self.recent_files() if item.resolve() != resolved]
        recent.insert(0, resolved)
        self.settings.setValue("recentFiles", [str(item) for item in recent[:MAX_RECENT_FILES]])
        self.refresh_recent_menu()

    def refresh_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        recent = self.recent_files()
        if not recent:
            empty_action = QAction("No Recent Files", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return
        for path in recent:
            action = QAction(path.name, self)
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked=False, selected=path: self.open_file(selected, show_in_folder=False))
            self.recent_menu.addAction(action)

    def find_text(self) -> None:
        self.show_find_bar()

    def show_find_bar(self) -> None:
        selected = self.editor.textCursor().selectedText().replace("\u2029", " ")
        self.find_bar.show()
        if selected:
            self.find_input.setText(selected)
        self.find_input.setFocus()
        self.find_input.selectAll()
        self.perform_find(reset=True)

    def hide_find_bar(self) -> None:
        self.find_bar.hide()
        self._clear_preview_find_marks()
        self.find_status.setText("")

    def perform_find(self, reset: bool = False) -> None:
        term = self.find_input.text()
        if not term:
            self._find_matches = []
            self._find_active_index = -1
            self.find_status.setText("")
            self._clear_preview_find_marks()
            return
        if self.view_mode == "preview" and QWebEngineView is not None and isinstance(self.preview, QWebEngineView):
            self._find_preview(term, reset=reset)
            return
        self._find_in_editor(term, backwards=False, reset=reset)

    def find_next(self, backwards: bool) -> None:
        term = self.find_input.text()
        if not term:
            return
        if self.view_mode == "preview" and QWebEngineView is not None and isinstance(self.preview, QWebEngineView):
            self._find_preview_next(backwards)
            return
        self._find_in_editor(term, backwards=backwards, reset=False)

    def _find_flags(self, backwards: bool = False):
        flags = QTextDocument.FindFlags()
        if backwards:
            flags |= QTextDocument.FindBackward
        if self.find_case_check.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def _webengine_find_flags(self, backwards: bool = False):
        flags = QWebEnginePage.FindFlag(0)
        if backwards:
            flags |= QWebEnginePage.FindFlag.FindBackward
        if self.find_case_check.isChecked():
            flags |= QWebEnginePage.FindFlag.FindCaseSensitively
        return flags

    def _find_in_editor(self, term: str, backwards: bool, reset: bool) -> None:
        text = self.editor.toPlainText()
        self._find_matches = find_match_spans(text, term, self.find_case_check.isChecked())
        if not self._find_matches:
            self.find_status.setText(find_status_text(term, 0, -1))
            return
        cursor_position = self.editor.textCursor().selectionStart() if backwards else self.editor.textCursor().selectionEnd()
        if reset:
            cursor_position = 0
        self._find_active_index = next_match_index(self._find_matches, cursor_position, backwards)
        start, end = self._find_matches[self._find_active_index]
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.find_status.setText(find_status_text(term, len(self._find_matches), self._find_active_index))

    def _find_preview(self, term: str, reset: bool) -> None:
        page = self.preview.page()
        if reset:
            page.findText("")
        page.findText(term, self._webengine_find_flags(False), self._update_preview_find_result)

    def _find_preview_next(self, backwards: bool) -> None:
        term = self.find_input.text()
        if not term:
            return
        if self._find_preview_total == 0:
            self._find_preview(self.find_input.text(), reset=True)
            return
        self.preview.page().findText(term, self._webengine_find_flags(backwards), self._update_preview_find_result)

    def _update_preview_find_result(self, result) -> None:
        if isinstance(result, bool):
            self._find_preview_total = 1 if result else 0
            self._find_preview_active = 1 if result else 0
            self.find_status.setText("Found" if result else "No matches")
            return
        total_getter = getattr(result, "numberOfMatches", None)
        active_getter = getattr(result, "activeMatch", None)
        total = int(total_getter()) if callable(total_getter) else 0
        active = int(active_getter()) if callable(active_getter) else 0
        self._find_preview_total = total
        self._find_preview_active = active
        self.find_status.setText(find_status_text(self.find_input.text(), total, active - 1))

    def _update_preview_find_total(self, total) -> None:
        try:
            self._find_preview_total = int(total)
        except (TypeError, ValueError):
            self._find_preview_total = 0
        self._find_preview_active = 1 if self._find_preview_total else 0
        self.find_status.setText(find_status_text(self.find_input.text(), self._find_preview_total, self._find_preview_active - 1))

    def _update_preview_find_active(self, active) -> None:
        try:
            self._find_preview_active = int(active)
        except (TypeError, ValueError):
            self._find_preview_active = 0
        self.find_status.setText(find_status_text(self.find_input.text(), self._find_preview_total, self._find_preview_active - 1))

    def _clear_preview_find_marks(self) -> None:
        if QWebEngineView is not None and isinstance(self.preview, QWebEngineView):
            self.preview.page().findText("")

    def change_editor_zoom(self, steps: int) -> None:
        self.editor.zoomIn(steps)

    def reset_editor_zoom(self) -> None:
        font = QApplication.font()
        self.editor.setFont(font)

    def show_markdown_help(self) -> None:
        QMessageBox.information(
            self,
            "Markdown Help",
            "Common Markdown tools:\n\n"
            "H1/H2/H3: headings\n"
            "Bold / Italic: emphasize selected text\n"
            "Link: [text](https://example.com)\n"
            "Image: ![description](image.png)\n"
            "Bullets / Numbers / Task: create lists\n"
            "Quote: call out a quoted paragraph\n"
            "Code Block: paste code between fences\n"
            "Table: insert a starter table\n\n"
            "You can use the toolbar without memorizing the syntax.",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>"
            f"Version {html.escape(__version__)}<br><br>"
            "A focused Markdown reader and editor for Windows.<br><br>"
            "Files stay local. No telemetry is collected.",
        )

    def restore_settings(self) -> None:
        geometry = self.settings.value("windowGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("windowState")
        if state is not None:
            self.restoreState(state)
        splitter_state = self.settings.value("mainSplitter")
        if splitter_state is not None:
            self.main_splitter.restoreState(splitter_state)

    def save_settings(self) -> None:
        save_reader_settings(self.settings, self.reader_settings)
        self.settings.setValue("windowGeometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("mainSplitter", self.main_splitter.saveState())

    def _install_drop_targets(self, *widgets: QWidget) -> None:
        for widget in widgets:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)
            viewport = getattr(widget, "viewport", None)
            if callable(viewport):
                viewport_widget = viewport()
                viewport_widget.setAcceptDrops(True)
                viewport_widget.installEventFilter(self)

    def _accept_supported_drag_event(self, event) -> bool:
        if supported_drop_path(event.mimeData().urls()) is None:
            return False
        event.acceptProposedAction()
        return True

    def open_supported_drop_urls(self, urls) -> bool:
        path = supported_drop_path(urls)
        if path is None:
            return False
        if path.is_dir():
            self.open_folder(path)
        else:
            self.open_file(path, show_in_folder=False)
        return True

    def dragEnterEvent(self, event) -> None:
        if self._accept_supported_drag_event(event):
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._accept_supported_drag_event(event):
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        if self.open_supported_drop_urls(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def editor_changed(self) -> None:
        if self._loading:
            return
        if self._syncing_from_preview:
            self._set_dirty(self.editor.toPlainText() != self._current_text)
            return
        self.set_active_edit_surface("editor")
        self.schedule_preview_update()
        self._set_dirty(self.editor.toPlainText() != self._current_text)

    def format_heading(self, level: int) -> None:
        if self._run_preview_command("heading", {"level": level}):
            return
        prefix = "#" * level + " "
        cursor = self.editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n")
        lines = text.splitlines() or ["Heading"]
        formatted = "\n".join(prefix + line.lstrip("# ").strip() for line in lines)
        self._replace_selection(
            formatted,
            select_start=len(prefix) if not text else None,
            select_length=len("Heading") if not text else None,
        )

    def format_bold(self) -> None:
        if self._run_preview_command("bold"):
            return
        self._wrap_selection("**", "**", "bold text")

    def format_italic(self) -> None:
        if self._run_preview_command("italic"):
            return
        self._wrap_selection("*", "*", "italic text")

    def format_inline_code(self) -> None:
        if self._run_preview_command("inline-code"):
            return
        self._wrap_selection("`", "`", "code")

    def format_link(self) -> None:
        if self._preview_is_active():
            url, accepted = QInputDialog.getText(self, "Add link", "Link URL:")
            if not accepted:
                return
            self._run_preview_command("link", {"url": url.strip() or "https://example.com"})
            return
        cursor = self.editor.textCursor()
        label = cursor.selectedText().replace("\u2029", " ") or "link text"
        url, accepted = QInputDialog.getText(self, "Add link", "Link URL:")
        if not accepted:
            return
        url = url.strip() or "https://example.com"
        self._replace_selection(
            f"[{label}]({url})",
            select_start=1 if label == "link text" else None,
            select_length=len(label) if label == "link text" else None,
        )

    def format_image(self) -> None:
        source, accepted = QInputDialog.getText(self, "Add image", "Image URL or file path:")
        if not accepted:
            return
        source = source.strip() or "image.png"
        if self._run_preview_command("image", {"source": source}):
            return
        cursor = self.editor.textCursor()
        alt_text = cursor.selectedText().replace("\u2029", " ") or "image description"
        self._replace_selection(
            f"![{alt_text}]({source})",
            select_start=2 if alt_text == "image description" else None,
            select_length=len(alt_text) if alt_text == "image description" else None,
        )

    def format_line_prefix(self, prefix: str) -> None:
        command_by_prefix = {
            "- ": "bullets",
            "- [ ] ": "task",
            "> ": "quote",
        }
        if prefix in command_by_prefix and self._run_preview_command(command_by_prefix[prefix]):
            return
        cursor = self.editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n")
        lines = text.splitlines() or ["List item"]
        formatted = "\n".join(prefix + line.lstrip() for line in lines)
        self._replace_selection(
            formatted,
            select_start=len(prefix) if not text else None,
            select_length=len("List item") if not text else None,
        )

    def format_numbered_list(self) -> None:
        if self._run_preview_command("numbers"):
            return
        cursor = self.editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n")
        lines = text.splitlines() or ["List item"]
        formatted = "\n".join(f"{index}. {line.lstrip()}" for index, line in enumerate(lines, start=1))
        self._replace_selection(
            formatted,
            select_start=len("1. ") if not text else None,
            select_length=len("List item") if not text else None,
        )

    def format_code_block(self) -> None:
        if self._run_preview_command("code-block"):
            return
        cursor = self.editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n") or "paste code here"
        self._replace_selection(
            f"```\n{text}\n```",
            select_start=len("```\n") if text == "paste code here" else None,
            select_length=len(text) if text == "paste code here" else None,
        )

    def format_table(self) -> None:
        if self._run_preview_command("table"):
            return
        table = (
            "| Column 1 | Column 2 |\n"
            "| --- | --- |\n"
            "| Value | Value |"
        )
        self._insert_block(table)

    def add_table_row(self) -> None:
        if self._run_preview_command("add-table-row", require_active=False):
            return
        self.statusBar().showMessage("Select a table in Preview mode to add a row", 3000)

    def add_table_column(self) -> None:
        if self._run_preview_command("add-table-column", require_active=False):
            return
        self.statusBar().showMessage("Select a table in Preview mode to add a column", 3000)

    def _wrap_selection(self, prefix: str, suffix: str, placeholder: str) -> None:
        cursor = self.editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n") or placeholder
        self._replace_selection(
            f"{prefix}{text}{suffix}",
            select_start=len(prefix) if text == placeholder else None,
            select_length=len(text) if text == placeholder else None,
        )

    def _insert_block(self, text: str) -> None:
        cursor = self.editor.textCursor()
        before = "\n\n" if cursor.position() > 0 else ""
        after = "\n\n"
        cursor.insertText(f"{before}{text}{after}")
        self.editor.setTextCursor(cursor)

    def _replace_selection(
        self,
        text: str,
        select_start: int | None = None,
        select_length: int | None = None,
    ) -> None:
        cursor = self.editor.textCursor()
        start = cursor.selectionStart()
        cursor.beginEditBlock()
        cursor.insertText(text)
        cursor.endEditBlock()
        if select_start is not None and select_length is not None:
            cursor.setPosition(start + select_start)
            cursor.setPosition(start + select_start + select_length, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.set_active_edit_surface("editor")

    def update_preview(self) -> None:
        self._set_html(
            render_markdown(self.editor.toPlainText(), self.current_file, self.appearance_mode),
            self.current_file.parent if self.current_file else self.current_folder,
        )

    def schedule_preview_update(self) -> None:
        self._preview_render_pending = True
        self._pending_preview_line = self.editor.textCursor().blockNumber() + 1
        self.show_preview_loading_overlay()
        self.preview_render_timer.start()

    def render_pending_preview(self) -> None:
        if not self._preview_render_pending:
            return
        self._preview_render_pending = False
        self.update_preview()

    def show_preview_loading_overlay(self) -> None:
        self._preview_loading_visible = True
        self.preview_blur_effect.setEnabled(True)
        self.preview_loading_overlay.show()
        self.preview_loading_overlay.raise_()

    @Slot()
    def hide_preview_loading_overlay(self, *_args) -> None:
        if not self._preview_render_pending:
            self._preview_loading_visible = False
            self.preview_blur_effect.setEnabled(False)
            self.preview_loading_overlay.hide()

    def set_active_edit_surface(self, surface: str) -> None:
        self._active_edit_surface = surface

    def _preview_is_active(self) -> bool:
        return (
            self._active_edit_surface == "preview"
            and QWebEngineView is not None
            and isinstance(self.preview, QWebEngineView)
        )

    def _preview_can_run_command(self, require_active: bool = True) -> bool:
        if QWebEngineView is None or not isinstance(self.preview, QWebEngineView):
            return False
        if self.view_mode not in {"preview", "split"}:
            return False
        return not require_active or self._active_edit_surface == "preview"

    def _run_preview_command(
        self,
        command: str,
        options: dict | None = None,
        require_active: bool = True,
    ) -> bool:
        if not self._preview_can_run_command(require_active):
            return False
        payload_command = json.dumps(command)
        payload_options = json.dumps(options or {})
        self.preview.page().runJavaScript(f"window.mdReaderApplyFormat({payload_command}, {payload_options});")
        return True

    def copy_active_selection(self) -> None:
        if self._preview_is_active():
            self.preview.page().runJavaScript("window.mdReaderCopySelection();")
            return
        self.editor.copy()

    def apply_preview_markdown(self, markdown_text: str) -> None:
        if markdown_text == self.editor.toPlainText():
            return
        self._syncing_from_preview = True
        self._loading = True
        try:
            self.editor.setPlainText(markdown_text)
        finally:
            self._loading = False
            self._syncing_from_preview = False
        self._set_dirty(markdown_text != self._current_text)

    def sync_preview_to_editor_cursor(self) -> None:
        if (
            self._syncing_editor_from_preview_scroll
            or not self.editor.hasFocus()
            or not (QWebEngineView is not None and isinstance(self.preview, QWebEngineView))
        ):
            return
        self.set_active_edit_surface("editor")
        line_number = self.editor.textCursor().blockNumber() + 1
        if self._last_preview_scroll_line == line_number:
            return
        self.scroll_preview_to_source_line(line_number)

    def sync_preview_to_editor_scroll(self) -> None:
        if (
            self._syncing_editor_from_preview_scroll
            or not self.editor.hasFocus()
            or not (QWebEngineView is not None and isinstance(self.preview, QWebEngineView))
        ):
            return
        line_number = self.editor.cursorForPosition(QPoint(0, 0)).blockNumber() + 1
        if self._last_preview_scroll_line == line_number:
            return
        self.scroll_preview_to_source_line(line_number)

    def scroll_preview_to_source_line(self, line_number: int, hide_overlay_after_scroll: bool = False) -> None:
        self._ignore_next_preview_scroll_line = line_number
        self._last_preview_scroll_line = line_number
        if hide_overlay_after_scroll:
            self.preview.page().runJavaScript(
                f"window.mdReaderScrollToSourceLine({line_number});",
                lambda _result: QTimer.singleShot(120, self.hide_preview_loading_overlay),
            )
            return
        self.preview.page().runJavaScript(f"window.mdReaderScrollToSourceLine({line_number});")

    def sync_editor_to_preview_line(self, line_number: int) -> None:
        if line_number <= 0:
            return
        if self._ignore_next_preview_scroll_line == line_number:
            self._ignore_next_preview_scroll_line = None
            return
        document = self.editor.document()
        block = document.findBlockByNumber(line_number - 1)
        if not block.isValid():
            return
        self._syncing_editor_from_preview_scroll = True
        try:
            visible_lines = max(1, self.editor.viewport().height() // max(1, self.editor.fontMetrics().lineSpacing()))
            scroll_bar = self.editor.verticalScrollBar()
            scroll_bar.setValue(
                editor_scroll_value_for_source_line(line_number, visible_lines, scroll_bar.maximum())
            )
        finally:
            self._syncing_editor_from_preview_scroll = False

    def apply_pending_preview_scroll(self, ok: bool) -> None:
        if not ok:
            self.hide_preview_loading_overlay()
            return
        if self._pending_preview_line is None:
            self.hide_preview_loading_overlay()
            return
        line_number = self._pending_preview_line
        self._pending_preview_line = None
        self.scroll_preview_to_source_line(line_number, hide_overlay_after_scroll=self._preview_loading_visible)

    def confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        result = QMessageBox.warning(
            self,
            APP_NAME,
            "The current Markdown file has unsaved changes.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Save:
            return self.save_file()
        return result == QMessageBox.Discard

    def _set_editor_text(self, text: str) -> None:
        self._loading = True
        try:
            self.editor.setPlainText(text)
        finally:
            self._loading = False

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        title_path = self.current_file.name if self.current_file else APP_NAME
        marker = "*" if dirty else ""
        self.setWindowTitle(f"{marker}{title_path} - {APP_NAME}" if self.current_file else APP_NAME)

    def _set_html(self, document: str, base_dir: Path | None) -> None:
        if QWebEngineView is not None:
            base_url = QUrl.fromLocalFile(str(base_dir) + "/") if base_dir else QUrl()
            self.preview.setHtml(document, base_url)
        else:
            self.preview.setHtml(document)
            self.hide_preview_loading_overlay()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in {QEvent.DragEnter, QEvent.DragMove}:
            return self._accept_supported_drag_event(event)
        if event.type() == QEvent.Drop:
            if self.open_supported_drop_urls(event.mimeData().urls()):
                event.acceptProposedAction()
                return True
            return False
        if watched is self.editor and event.type() == QEvent.FocusIn:
            self.set_active_edit_surface("editor")
            self.sync_preview_to_editor_cursor()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "main_splitter") and self.view_mode == "split":
            self.apply_view_mode()

    def closeEvent(self, event) -> None:
        if self.confirm_discard_changes():
            self.save_settings()
            event.accept()
        else:
            event.ignore()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Markdown files as formatted HTML.")
    parser.add_argument("file", nargs="?", help="Markdown file to open")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    configure_qt_application_identity(app)
    icon_path = resource_path("assets/mdreader.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    file_path = Path(args.file).resolve() if args.file else None
    window = MarkdownWindow(file_path)
    window.show()
    return app.exec()
