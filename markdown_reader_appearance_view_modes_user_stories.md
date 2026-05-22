# User Stories: Appearance Modes and Markdown View Modes

## Feature Summary

Implement two reader-focused controls for a markdown file viewer:

1. Light mode, dark mode, and system appearance.
2. Preview-only, raw-only, and split view modes.

The app should default to **rendered** because the main target user is a casual reader opening an AI-generated `.md` file.

---

## Product Context

### Current app state

The app can:

1. Open markdown files.
2. Show raw markdown.
3. Show rendered markdown preview.
4. Show raw and preview side by side.

### Target user

A casual user who wants to open and read an AI-generated markdown file without needing to understand markdown syntax.

### Core principle

The default experience should feel like reading a normal document.

Raw markdown should be available, but it should not be forced on casual users.

---

# User Story 1: Use Light, Dark, or System Appearance

## Story

As a casual reader,  

I want to choose between light mode, dark mode, and system mode,  

so that I can read markdown documents comfortably in different environments.

## Requirements

### Appearance options

The app must support:

1. Light mode.
2. Dark mode.
3. System mode.

System mode follows the device or browser appearance preference.

### Default behavior

The first-run default should be:

```text
System
```

If system preference cannot be detected, use light mode.

### Manual control

The user must be able to select:

```text
System
Light
Dark
```

The selected option should apply immediately.

### Persistence

The app must remember the selected appearance mode across sessions.

### Theme coverage

The selected appearance must apply to:

1. App shell.
2. Markdown preview.
3. Raw markdown view.
4. Split view.
5. Toolbar.
6. Menus.
7. Dialogs or popovers.
8. Empty states.
9. Error states.
10. Scrollbars where supported.

### Markdown readability

Both light and dark mode must keep these readable:

1. Body text.
2. Headings.
3. Links.
4. Tables.
5. Code blocks.
6. Inline code.
7. Blockquotes.
8. Task lists.
9. Focus states.

## Acceptance Criteria

1. Given I open the app for the first time, the app follows my system appearance.
2. Given I choose light mode, the app switches to light mode immediately.
3. Given I choose dark mode, the app switches to dark mode immediately.
4. Given I choose system mode, the app follows my system preference.
5. Given I restart the app, my selected appearance mode is remembered.
6. Given I read a markdown file in dark mode, the document remains readable.
7. Given I read a markdown file in light mode, the document remains readable.
8. Given I use keyboard navigation, focus indicators remain visible in both themes.

---

# User Story 2: Open Markdown in Rendered Mode by Default

## Story

As a casual user,  

I want markdown files to open as rendered documents by default,  

so that I can read the content without seeing markdown syntax first.

## Requirements

### Default view mode

The app must open files in:

```text
Rendered
```

This should be the first-run default.

### Rendered behavior

Rendered mode should:

1. Show the rendered markdown document.
2. Hide the raw markdown source.
3. Use comfortable reading width.
4. Use readable typography and spacing.
5. Keep search, export, and navigation controls accessible.
6. Support dark and light mode.

### Raw markdown access

The user must still be able to switch to raw-only or split mode manually.

## Acceptance Criteria

1. Given I open a markdown file for the first time, I see rendered view only.
2. Given I am in rendered mode, the raw markdown source is hidden.
3. Given I want to inspect the source, I can switch to raw-only mode.
4. Given I want source and preview together, I can switch to split mode.
5. Given I return to rendered mode, the app shows the rendered document cleanly.
6. Given I am a casual user, I am not required to understand markdown syntax to read the file.

---

# User Story 3: Switch to Raw-Only Mode

## Story

As a user who wants to inspect or edit markdown source,  

I want a raw-only mode,  

so that I can focus on the markdown text without the preview pane.

## Requirements

### Raw-only behavior

Raw-only mode should:

1. Show only the markdown source.
2. Hide the rendered preview.
3. Use a readable monospace font.
4. Support line wrapping.
5. Support syntax highlighting if available.
6. Support find within source if search exists.
7. Work in light and dark mode.

### Editing behavior

If the app supports editing, switching into or out of raw-only mode must not discard unsaved edits.

## Acceptance Criteria

1. Given I choose raw-only mode, only the markdown source is visible.
2. Given I am in raw-only mode, the preview pane is hidden.
3. Given I switch away from raw-only mode, my file content is preserved.
4. Given I have unsaved edits, switching modes does not discard them.
5. Given I use raw-only mode in dark mode, the source text remains readable.
6. Given I use raw-only mode in light mode, the source text remains readable.

---

# User Story 4: Switch to Split Mode

## Story

As a user who wants to compare markdown source with rendered output,  

I want a split mode,  

so that I can see raw markdown and preview side by side.

## Requirements

### Split behavior

Split mode should show:

1. Raw markdown pane.
2. Rendered preview pane.
3. A clear divider between panes.
4. Adjustable pane width if supported.
5. Synchronized scrolling if practical.
6. Support for light and dark mode.

### Responsive behavior

Desktop:

1. Show raw and preview side by side.

Tablet:

1. Show side by side if space allows.
2. Use stacked panes if space is limited.

Mobile:

1. Do not force cramped side-by-side panes.
2. Use tabs or disable split mode with a clear explanation.

## Acceptance Criteria

1. Given I choose split mode on desktop, I see raw markdown and preview side by side.
2. Given I resize the panes, the layout remains usable.
3. Given I scroll in one pane, synchronized scrolling works if implemented.
4. Given I use split mode in dark mode, both panes remain readable.
5. Given I use split mode on mobile, the layout does not become cramped or unusable.
6. Given I switch away from split mode, the file content is preserved.

---

# User Story 5: Remember View Mode Preference

## Story

As a returning user,  

I want the app to remember my preferred view mode,  

so that I do not need to switch modes every time I open a markdown file.

## Requirements

### First-run default

The first-run default must be:

```text
Rendered-only
```

### Persisted preference

After the user manually changes view mode, the app should remember their preference.

Supported modes:

```text
Rendered-only
Raw-only
Split
```

### Settings option

Add a setting called:

```text
Default view mode
```

Allowed values:

```text
Rendered-only
Raw-only
Split
Last used
```

Recommended default:

```text
Rendered-only
```

## Acceptance Criteria

1. Given I have never changed settings, markdown files open in rendered-only mode.
2. Given I set default view mode to raw-only, files open in raw-only mode.
3. Given I set default view mode to split, files open in split mode when supported.
4. Given I set default view mode to last used, the app opens files using my most recent view mode.
5. Given stored settings are invalid, the app falls back to rendered-only mode.

---

# User Story 6: Switch View Modes Quickly

## Story

As a user reading or inspecting a markdown file,  

I want a simple view mode control,  

so that I can switch between preview, raw, and split without digging through settings.

## Requirements

### View mode selector

Add a visible control with these labels:

```text
Preview
Raw
Split
```

Avoid technical labels such as:

```text
AST
Source Buffer
Dual Renderer
```

### Optional keyboard shortcuts

Suggested shortcuts:

```text
Ctrl + 1: Preview
Ctrl + 2: Raw
Ctrl + 3: Split
```

### Scroll preservation

When switching modes, preserve the user’s approximate document position.

Example:

If the user is reading the `Requirements` section in preview mode and switches to split mode, the preview pane should stay near that section.

## Acceptance Criteria

1. Given I am viewing a markdown file, I can see or access a view mode selector.
2. Given I choose Preview, the app switches to preview-only mode.
3. Given I choose Raw, the app switches to raw-only mode.
4. Given I choose Split, the app switches to split mode.
5. Given I switch modes, my approximate reading position is preserved.
6. Given I use keyboard shortcuts, I can switch modes without a mouse.
7. Given a mode is active, the selector clearly shows the active mode.

---

# Suggested Technical Model

## Appearance mode

```ts
type AppearanceMode = 'system' | 'light' | 'dark';
```

## Effective theme

```ts
type EffectiveTheme = 'light' | 'dark';
```

## Markdown view mode

```ts
type MarkdownViewMode = 'preview' | 'raw' | 'split';
```

## Reader settings

```ts
type ReaderSettings = {
  appearanceMode: AppearanceMode;
  defaultViewMode: MarkdownViewMode | 'last-used';
  lastUsedViewMode: MarkdownViewMode;
};
```

## Default settings

```ts
const defaultReaderSettings: ReaderSettings = {
  appearanceMode: 'system',
  defaultViewMode: 'preview',
  lastUsedViewMode: 'preview'
};
```

---

# Suggested Implementation Tasks

## Task 1: Add appearance state

Implement app state for system, light, and dark appearance.

Done when:

1. The selected appearance mode is stored.
2. The effective theme is calculated correctly.
3. System mode reacts to device or browser preference changes.

## Task 2: Add light and dark theme tokens

Create theme tokens for both light and dark mode.

Minimum tokens:

```ts
type ThemeTokens = {
  background: string;
  surface: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  link: string;
  focusRing: string;
  codeBackground: string;
  codeText: string;
  tableBorder: string;
};
```

Done when:

1. Preview uses the tokens.
2. Raw view uses the tokens.
3. Split view uses the tokens.
4. Toolbar and menus use the tokens.
5. Focus states remain visible.

## Task 3: Add appearance selector

Create a selector for System, Light, and Dark.

Done when:

1. The user can change appearance manually.
2. The selected appearance is visibly active.
3. The setting persists across sessions.
4. The selector is keyboard accessible.

## Task 4: Add view mode state

Implement app state for preview, raw, and split mode.

Done when:

1. Preview-only mode works.
2. Raw-only mode works.
3. Split mode works.
4. Preview-only is the first-run default.

## Task 5: Add view mode selector

Create a selector for Preview, Raw, and Split.

Done when:

1. The active mode is visible.
2. The user can switch modes with pointer input.
3. The user can switch modes with keyboard input.
4. Switching modes updates the layout immediately.

## Task 6: Implement preview-only layout

Done when:

1. Rendered markdown is shown.
2. Raw markdown is hidden.
3. Document width and spacing are comfortable for reading.
4. Reader controls remain accessible.

## Task 7: Implement raw-only layout

Done when:

1. Raw markdown is shown.
2. Preview is hidden.
3. Text remains readable in both themes.
4. Unsaved edits are preserved when switching modes.

## Task 8: Implement split layout

Done when:

1. Raw and preview panes are both visible.
2. Desktop layout is side by side.
3. Smaller screens use a safe fallback.
4. File content is preserved when switching modes.

## Task 9: Persist user settings

Persist:

1. Appearance mode.
2. Default view mode.
3. Last used view mode.

Done when:

1. Preferences survive app restart.
2. Invalid stored values fall back to safe defaults.
3. First-run behavior remains preview-only and system appearance.

## Task 10: Add tests

Minimum test cases:

1. First launch uses system appearance.
2. First opened file uses preview-only mode.
3. User can switch to light mode.
4. User can switch to dark mode.
5. User can switch to system mode.
6. User can switch to raw-only mode.
7. User can switch to split mode.
8. User can switch back to preview-only mode.
9. Appearance preference persists.
10. View mode preference persists.
11. Invalid settings fall back to preview-only mode.
12. Unsaved edits are preserved when switching modes.
13. Split mode is safe on small screens.
14. Focus indicators are visible in both themes.

---

# Non-Goals for This Feature Pass

Do not implement:

1. Custom theme editor.
2. User-created color palettes.
3. Plugin-based themes.
4. AI summarization.
5. AI rewriting.
6. Graph view.
7. Backlinks.
8. Multi-file vault mode.
9. Cloud sync.
10. Collaboration.

---

# Definition of Done

This feature is complete when:

1. Markdown files open in preview-only mode by default.
2. Users can switch between preview-only, raw-only, and split mode.
3. Users can choose system, light, or dark appearance.
4. Appearance preference persists.
5. View mode preference persists.
6. All view modes remain readable in both light and dark mode.
7. Keyboard access works for appearance and view controls.
8. Focus states are visible in both themes.
9. Split mode behaves safely on smaller screens.
10. The user is never forced to see raw markdown unless they choose it.
