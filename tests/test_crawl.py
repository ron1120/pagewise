from pagewise.crawl import Page, crawl, extract, normalize


def test_extract_groups_text_under_headings():
    html = "<html><title>T</title><main><h1>Top</h1><p>one</p><h2>Part</h2><p>two</p><li>three</li></main></html>"
    page = extract("https://x.test/", html)
    assert page.title == "T"
    assert page.sections == [("Top", "one"), ("Part", "two"), ("Part", "three")]


def test_extract_drops_navigation_scripts_and_hidden_decoration():
    html = (
        "<nav><p>menu</p></nav><script>var a=1</script><footer><p>foot</p></footer>"
        "<main><p aria-hidden='true'>icon</p><div aria-hidden='true'><p>duplicate half</p></div><p>real</p></main>"
    )
    assert extract("https://x.test/", html).sections == [("https://x.test/", "real")]


def test_extract_keeps_spaces_between_word_spans_and_glues_letter_spans():
    words = "<main><p><span>DevOps</span><span>&amp;</span><span>AI</span><span>Engineer</span></p></main>"
    assert extract("u", words).sections[0][1] == "DevOps & AI Engineer"
    letters = "<main><p>" + "".join(f"<span>{c}</span>" for c in "Hello") + "</p></main>"
    assert extract("u", letters).sections[0][1] == "Hello"


def test_extract_does_not_count_nested_paragraphs_twice():
    html = "<main><ul><li><p>only once</p></li></ul></main>"
    assert extract("u", html).sections == [("u", "only once")]


def test_extract_removes_repeated_paragraphs_under_the_same_heading():
    html = "<main><h2>Skills</h2><p>AWS</p><p>Terraform</p><p>AWS</p></main>"
    assert extract("u", html).sections == [("Skills", "AWS"), ("Skills", "Terraform")]


def test_normalize_drops_fragments_and_queries_and_gives_bare_hosts_a_slash():
    assert normalize("https://x.test/a/?q=1#top") == "https://x.test/a/"
    assert normalize("https://x.test") == "https://x.test/"


def _site(pages: dict[str, tuple[int, str, str]]):
    def fetch(url):
        return pages.get(url, (404, "text/html", ""))

    return fetch


def test_crawl_follows_links_on_one_host_only_and_skips_non_html():
    site = {
        "https://x.test/": (200, "text/html", "<main><p>home</p><a href='/a/'>a</a><a href='https://other.test/'>o</a>"
                                                "<a href='/logo.png'>img</a><a href='/doc'>doc</a></main>"),
        "https://x.test/a/": (200, "text/html; charset=utf-8", "<main><p>page a</p><a href='/'>home</a></main>"),
        "https://x.test/doc": (200, "application/pdf", "binary"),
        "https://other.test/": (200, "text/html", "<main><p>elsewhere</p></main>"),
    }
    pages = crawl("https://x.test", fetch=_site(site))
    assert sorted(p.url for p in pages) == ["https://x.test/", "https://x.test/a/"]


def test_crawl_uses_the_sitemap_and_respects_max_pages():
    sitemap = "<urlset><url><loc>https://x.test/hidden/</loc></url><url><loc>https://x.test/more/</loc></url></urlset>"
    site = {
        "https://x.test/": (200, "text/html", "<main><p>home</p></main>"),
        "https://x.test/sitemap.xml": (200, "application/xml", sitemap),
        "https://x.test/hidden/": (200, "text/html", "<main><p>not linked anywhere</p></main>"),
        "https://x.test/more/": (200, "text/html", "<main><p>more</p></main>"),
    }
    assert len(crawl("https://x.test/", fetch=_site(site))) == 3
    assert len(crawl("https://x.test/", fetch=_site(site), max_pages=2)) == 2


def test_page_round_trips_through_json():
    page = Page("u", "t", [("h", "text")])
    assert Page.from_dict(page.to_dict()) == page


def test_a_heading_inside_a_card_does_not_become_the_heading_of_the_next_card():
    html = "<main><ul><li><h3>Card A</h3><p>text a</p></li><li><h3>Card B</h3><p>text b</p></li></ul></main>"
    assert extract("u", html).sections == [("u", "Card A text a"), ("u", "Card B text b")]
