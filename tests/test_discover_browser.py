import pytest

from clipengine.campaigns.discover import diagnose, parse_discover

# a page whose campaign cards exist ONLY after JavaScript runs - the raw
# HTML has no money tokens at all, mirroring the live discover feed
JS_RENDERED_PAGE = """<html><body><div id="root"><p>Loading...</p></div>
<script>
document.getElementById('root').innerHTML = [
  '<div class="card"><h3>Roobet Clips</h3><span>Clipping</span>',
  '<span>$1 / 1K</span><span>$100,000 of $250,000 paid</span>',
  '<span>TikTok</span><span>Instagram</span></div>',
  '<div class="card"><h3>Pacinos Hair</h3><span>Clipping</span>',
  '<span>$1 per 1,000 views</span><span>$12.5K of $50K paid</span>',
  '<span>TikTok</span></div>'
].join('');
</script></body></html>"""


def test_raw_js_page_parses_nothing():
    """The exact live-page failure mode: plain fetch sees zero cards."""
    assert parse_discover(JS_RENDERED_PAGE) == []


def test_diagnose_flags_client_rendered_pages():
    report = diagnose(JS_RENDERED_PAGE)
    assert "bytes:" in report and "__next_f: 0" in report
    # the discriminator: rates exist in the page but only inside <script>
    assert "rate texts (anywhere): 2" in report
    assert "rate texts (visible): 0" in report
    report2 = diagnose('<div>$1.50 / 1K</div><script>self.__next_f.push()</script>')
    assert "__next_f: 1" in report2
    assert "rate texts (visible): 1" in report2
    assert "$1.50 / 1K" in report2  # $-token samples surface the shape


def test_browser_render_recovers_client_rendered_cards(tmp_path, monkeypatch):
    """Real headless Chromium: render the JS page, then parse the DOM."""
    pytest.importorskip("playwright.sync_api")
    import os

    from clipengine.campaigns.discover import render_discover

    bundled = "/opt/pw-browsers/chromium"  # this sandbox's preinstalled build
    if os.path.exists(bundled):
        monkeypatch.setenv("CLIPENGINE_CHROMIUM_PATH", bundled)

    page_file = tmp_path / "feed.html"
    page_file.write_text(JS_RENDERED_PAGE)
    html = render_discover(page_file.as_uri(), wait_ms=300, scrolls=1)
    found = {d.title: d for d in parse_discover(html)}
    assert set(found) == {"Roobet Clips", "Pacinos Hair"}
    assert found["Roobet Clips"].budget_remaining == 150000
    assert found["Pacinos Hair"].budget_total == 50000  # K suffix path


def test_browser_render_harvests_iframe_content(tmp_path, monkeypatch):
    """Whop app pages render their content in an iframe - cards must be
    recovered from child frames, not just the top-level page."""
    pytest.importorskip("playwright.sync_api")
    import os

    from clipengine.campaigns.discover import render_discover

    bundled = "/opt/pw-browsers/chromium"
    if os.path.exists(bundled):
        monkeypatch.setenv("CLIPENGINE_CHROMIUM_PATH", bundled)

    (tmp_path / "child.html").write_text(JS_RENDERED_PAGE)
    parent = tmp_path / "parent.html"
    parent.write_text(
        '<html><body><h1>Content Rewards</h1>'
        '<iframe src="child.html" width="800" height="600"></iframe>'
        "</body></html>"
    )
    html = render_discover(parent.as_uri(), wait_ms=300, scrolls=1)
    found = {d.title for d in parse_discover(html)}
    assert found == {"Roobet Clips", "Pacinos Hair"}


def test_render_without_playwright_gives_install_hint(monkeypatch):
    import builtins

    from clipengine.campaigns import discover

    real_import = builtins.__import__

    def no_playwright(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("nope")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_playwright)
    with pytest.raises(RuntimeError, match="clipengine\\[browser\\]"):
        discover.render_discover("file:///dev/null")
