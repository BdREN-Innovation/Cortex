import pytest

from engine.contracts.documents import CleanDocument
from engine.contracts.jsonio import read_json, read_jsonl
from engine.crawler.extract import extract
from engine.crawler.fetcher import FetchPolicy
from engine.crawler.frontier import Frontier, ScopeRules, canonicalize
from engine.crawler.pipeline import CrawlConfig, crawl


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://X.test/a/", "https://x.test/a"),
        ("https://x.test/a#section", "https://x.test/a"),
        ("https://x.test/a?utm_source=news", "https://x.test/a"),
        ("https://x.test/a?b=2&a=1", "https://x.test/a?a=1&b=2"),
        ("https://x.test//a//b", "https://x.test/a/b"),
        ("https://x.test:443/a", "https://x.test/a"),
    ],
)
def test_canonicalize_collapses_url_variants(raw, expected):
    assert canonicalize(raw) == expected


def test_frontier_never_yields_a_page_twice():
    rules = ScopeRules(allowed_domains=["x.test"], max_depth=2)
    frontier = Frontier(["https://x.test/a"], rules)
    assert frontier.add("https://x.test/a/", depth=1) is False
    assert frontier.add("https://other.test/a", depth=1) is False
    assert frontier.add("https://x.test/b", depth=1) is True
    assert frontier.add("https://x.test/c", depth=5) is False


def test_extract_pulls_title_breadcrumb_and_drops_chrome():
    html = """<html lang="en"><head><title>T</title></head><body>
      <nav class="breadcrumb"><a>Home</a><a>Docs</a><span>Billing</span></nav>
      <main><h1>Billing</h1><p>We bill monthly.</p></main>
      <footer>Copyright</footer><script>var x=1</script></body></html>"""
    found = extract(html, "https://x.test/docs/billing")
    assert found.title == "T"
    assert found.section_path == ["Home", "Docs", "Billing"]
    assert "We bill monthly." in found.text
    assert "Copyright" not in found.text
    assert "var x" not in found.text


def test_crawl_end_to_end(site_url, tmp_path):
    config = CrawlConfig(
        site="acme",
        seeds=[f"{site_url}/index.html"],
        max_depth=2,
        max_pages=10,
        min_text_chars=50,
        fetch=FetchPolicy(delay_seconds=0.0, obey_robots=True),
    )
    out_dir = crawl(config, out_root=tmp_path)

    docs = [CleanDocument.from_dict(row) for row in read_jsonl(out_dir / "documents.jsonl")]
    urls = {d.canonical_url for d in docs}
    # The four content pages must all be found, by following links from the seed.
    for page in ("index.html", "docs/billing.html", "docs/limits.html", "docs/refunds.html"):
        assert f"{site_url}/{page}" in urls, urls
    assert all(d.validate() == [] for d in docs)

    billing = next(d for d in docs if "billing" in d.canonical_url)
    assert "bills monthly" in billing.text
    assert billing.section_path == ["Home", "Docs", "Billing"]
    assert "Copyright Acme" not in billing.text

    manifest = read_json(out_dir / "manifest.json")
    # 4 content pages + the server's auto-generated /docs listing, which the
    # next test shows how to exclude.
    assert manifest["pages_written"] == len(docs)
    assert manifest["errors"] == []


def test_crawl_respects_robots(site_url, tmp_path):
    """/private/ is disallowed by the fixture robots.txt."""
    from engine.crawler.fetcher import Fetcher

    fetcher = Fetcher(FetchPolicy(delay_seconds=0.0))
    assert fetcher.allowed(f"{site_url}/docs/billing.html") is True
    assert fetcher.allowed(f"{site_url}/private/secret.html") is False


def test_exclude_patterns_drop_directory_listings(site_url, tmp_path):
    """The breadcrumbs link to /docs/, which the server renders as an auto-generated
    file listing. It is not content, and exclude_patterns is how you say so."""
    config = CrawlConfig(
        site="acme",
        seeds=[f"{site_url}/index.html"],
        exclude_patterns=[r"/docs$"],
        max_depth=2,
        max_pages=10,
        min_text_chars=50,
        fetch=FetchPolicy(delay_seconds=0.0),
    )
    out_dir = crawl(config, out_root=tmp_path)
    urls = {row["canonical_url"] for row in read_jsonl(out_dir / "documents.jsonl")}

    assert f"{site_url}/docs" not in urls
    assert f"{site_url}/docs/billing.html" in urls
    assert len(urls) == 4


def test_duplicate_content_is_written_once(site_url, tmp_path):
    """Two URLs serving identical text must collapse to one document."""
    config = CrawlConfig(
        site="acme",
        seeds=[f"{site_url}/index.html", f"{site_url}/index.html?utm_source=x"],
        max_depth=0,
        max_pages=10,
        min_text_chars=50,
        fetch=FetchPolicy(delay_seconds=0.0),
    )
    out_dir = crawl(config, out_root=tmp_path)
    docs = list(read_jsonl(out_dir / "documents.jsonl"))
    assert len(docs) == 1
