"""E2E: Markdown (.md) files open in a read-only rendered preview.

Counterpart to the editor tests (``test_markdown_rich_rendering.py``,
``test_markdown_task_lists.py``): those pin the *editable* TipTap surface,
this pins the *read-only preview* that a ``.md`` file now opens in by default.

The preview is rendered by Streamdown (the same renderer chat uses), so it
emits ``data-streamdown="*"`` elements and GFM task-list checkboxes — and,
crucially, it is NOT the ``contenteditable`` TipTap editor. Because Streamdown
renders plain DOM (no iframe, unlike the HTML preview), this is also what the
iOS WKWebView shell shows, where the sandboxed HTML preview cannot render.

Seeded via the filesystem PUT endpoint (no agent run).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MARKDOWN_FILE_PATH = "preview_notes.md"

# A heading plus a GFM task list: the heading proves Markdown is parsed (not
# shown verbatim), the task list proves remark-gfm is active in the preview.
_MARKDOWN_CONTENT = """\
# Checklist

- [ ] Buy milk
- [x] Ship the PR
"""


@pytest.fixture
def seeded_preview_session(
    seeded_session: tuple[str, str],
) -> Iterator[tuple[str, str]]:
    base_url, session_id = seeded_session
    resp = httpx.put(
        f"{base_url}/v1/sessions/{session_id}"
        f"/resources/environments/default/filesystem/{_MARKDOWN_FILE_PATH}",
        json={"content": _MARKDOWN_CONTENT, "encoding": "utf-8"},
        timeout=10.0,
    )
    resp.raise_for_status()
    try:
        yield (base_url, session_id)
    finally:
        shutil.rmtree(_REPO_ROOT / session_id, ignore_errors=True)


def test_markdown_opens_in_readonly_preview(
    page: Page,
    seeded_preview_session: tuple[str, str],
) -> None:
    """A .md file opens rendered (Streamdown) and read-only — not the editor."""
    base_url, session_id = seeded_preview_session
    page.goto(f"{base_url}/c/{session_id}?file={_MARKDOWN_FILE_PATH}")

    file_viewer = page.locator('[data-testid="file-viewer"]:visible')
    expect(file_viewer).to_be_visible()

    # The heading is rendered by Streamdown as a data-streamdown element, so the
    # literal "# Checklist" source never appears — i.e. this is the preview.
    heading = file_viewer.locator('[data-streamdown="heading-1"]')
    expect(heading).to_be_visible(timeout=10_000)
    expect(heading).to_contain_text("Checklist")
    expect(file_viewer.get_by_text("# Checklist", exact=False)).to_have_count(0)

    # GFM task list renders as checkboxes reflecting [ ] / [x], inheriting the
    # shared task-list styling (PR #721).
    checkboxes = file_viewer.locator(
        '[data-streamdown="list-item"].task-list-item input[type="checkbox"]'
    )
    expect(checkboxes).to_have_count(2)
    expect(checkboxes.nth(0)).not_to_be_checked()
    expect(checkboxes.nth(1)).to_be_checked()

    # Preview is read-only: the editable TipTap surface must NOT be mounted.
    expect(file_viewer.locator("[contenteditable='true']")).to_have_count(0)


def test_markdown_preview_toggles_to_editor_and_source(
    page: Page,
    seeded_preview_session: tuple[str, str],
) -> None:
    """The toolbar cycles preview -> editor -> source for Markdown."""
    base_url, session_id = seeded_preview_session
    page.goto(f"{base_url}/c/{session_id}?file={_MARKDOWN_FILE_PATH}")

    file_viewer = page.locator('[data-testid="file-viewer"]:visible')
    expect(file_viewer).to_be_visible()
    # Default: read-only preview (Streamdown), no editable surface.
    expect(file_viewer.locator('[data-streamdown="heading-1"]')).to_be_visible(timeout=10_000)
    expect(file_viewer.locator("[contenteditable='true']")).to_have_count(0)

    # preview -> editor: the editable TipTap surface mounts.
    file_viewer.get_by_role("button", name="Rich text editor").click()
    expect(file_viewer.locator("[contenteditable='true']")).to_be_visible(timeout=10_000)

    # editor -> source: raw markdown becomes visible, no editable surface.
    file_viewer.get_by_role("button", name="View source").click()
    expect(file_viewer.locator("[contenteditable='true']")).to_have_count(0)
    expect(file_viewer.get_by_text("- [x] Ship the PR", exact=False)).to_be_visible(timeout=10_000)

    # source -> preview: back to the rendered, read-only preview.
    file_viewer.get_by_role("button", name="View preview").click()
    expect(file_viewer.locator('[data-streamdown="heading-1"]')).to_be_visible(timeout=10_000)
