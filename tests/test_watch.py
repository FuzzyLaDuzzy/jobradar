"""Watched pages: the careers pages of companies without a job platform, and what changed on them."""

from jobradar import watch

PAGE = """<html><head><style>.x{}</style><script>var a = 1;</script></head><body>
<header>Logo</header><nav><a>Início</a><a>Sobre</a></nav>
<h2>Vagas abertas</h2><ul><li>Junior Backend Developer</li><li>Estágio em Data</li></ul>
<p>Atualizado a 12/11/2026</p><p>42</p><p>Vagas abertas</p><footer>© 2026 Empresa</footer></body></html>"""


def test_page_lines_keep_the_visible_text_without_menus_or_dates():
    # "42", the repeated line, the menus, header, footer, script and style are gone;
    # a line with words and a date stays
    assert watch.page_lines(PAGE) == ["Vagas abertas", "Junior Backend Developer", "Estágio em Data",
                                      "Atualizado a 12/11/2026"]


def test_added_lines_are_the_new_ones_in_page_order():
    assert watch.added_lines(["A", "B"], ["A", "C", "B", "D"]) == ["C", "D"]
    assert watch.added_lines(["A", "B"], ["B", "A"]) == []


def test_relevance_needs_one_of_the_persons_words():
    words = watch.watch_words({"search": {"title_keywords": ["backend", "software"], "levels": ["junior"]}})
    assert "backend" in words and "junior" in words
    assert watch.is_relevant(["Junior Backend Developer"], words)
    assert watch.is_relevant(["Estágio em Software"], words)  # without accents or capitals
    assert not watch.is_relevant(["Testemunho da Ana, 12/11/2026", "Atualizado a 13/11/2026"], words)
