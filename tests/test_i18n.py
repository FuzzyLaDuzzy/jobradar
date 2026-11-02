"""Português / English: every text has its translation, and the PT/EN button reaches everything."""

import ast
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobradar import i18n, message
from jobradar.app import create_app
from jobradar.i18n import t

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "jobradar" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def python_texts() -> set[str]:
    """Every t("...") in the Python code."""
    texts = set()
    for path in (ROOT / "jobradar").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args:
                assert isinstance(node.args[0], ast.Constant), f"t() needs a literal text in {path.name}"
                texts.add(node.args[0].value)
    return texts


def ui_dictionary() -> dict[str, str]:
    block = APP_JS[APP_JS.index("const EN = {"):APP_JS.index("\n};", APP_JS.index("const EN = {"))]
    pairs = re.findall(r'"((?:[^"\\]|\\.)*)":\s*\n?\s*"((?:[^"\\]|\\.)*)"', block)
    return dict(pairs)


def ui_texts() -> set[str]:
    """Every t('...') in the page and this.t("...") in app.js, plus the texts app.js and
    scoring.py hand to t() from a variable."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    texts = set(re.findall(r"\bt\('([^']*)'", html)) | set(re.findall(r'\bthis\.t\("([^"]*)"', APP_JS))
    texts |= {"Adicionada por ti", "Remoto", "Híbrido", "Presencial"}  # SOURCE_NAMES, WORK_MODELS
    guides = APP_JS[APP_JS.index("const KEY_GUIDES = ["):APP_JS.index("\n];", APP_JS.index("const KEY_GUIDES = ["))]
    texts |= set(re.findall(r'what: "([^"]*)"', guides))
    texts |= {s for block in re.findall(r"steps: \[(.*?)\]", guides, re.S) for s in re.findall(r'"([^"]*)"', block)}
    scoring = (ROOT / "jobradar" / "scoring.py").read_text(encoding="utf-8")
    return texts | set(re.findall(r'reasons\.append\("([^"]*)"\)', scoring))


def test_every_python_text_has_english():
    missing = python_texts() - set(i18n.EN)
    assert not missing


def test_every_interface_text_has_english():
    texts = ui_texts()
    assert len(texts) > 60  # the scan found the page's texts
    missing = texts - set(ui_dictionary())
    assert not missing


@pytest.mark.parametrize("dictionary", [i18n.EN, ui_dictionary()], ids=["python", "ui"])
def test_translations_keep_the_placeholders(dictionary):
    for pt, en in dictionary.items():
        assert set(PLACEHOLDER.findall(pt)) == set(PLACEHOLDER.findall(en)), pt


def test_t_follows_the_language():
    assert t("Vaga não encontrada") == "Vaga não encontrada"
    i18n.use({"language": "en"})
    assert t("Vaga não encontrada") == "Job not found"
    assert t("{n} vagas novas", n=3) == "3 new jobs"
    assert t("texto sem tradução") == "texto sem tradução"  # falls back to Portuguese
    i18n.use({"language": "fr"})
    assert i18n.language == "pt"


def test_language_button_changes_config_and_messages(tmp_path):
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", config_path)
    client = TestClient(create_app(config_path=config_path, db_path=tmp_path / "t.db"))
    assert client.get("/api/language").json() == {"language": "pt"}
    assert client.patch("/api/jobs/nao-existe", json={}).json()["detail"] == "Vaga não encontrada"

    assert client.put("/api/language", json={"language": "en"}).json() == {"language": "en"}
    text = config_path.read_text(encoding="utf-8")
    assert "language: en  " in text and "# pt = Português, en = English" in text  # only the value changed
    assert text.replace("language: en", "language: pt") == (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    assert client.patch("/api/jobs/nao-existe", json={}).json()["detail"] == "Job not found"
    assert client.get("/api/language").json() == {"language": "en"}

    assert client.put("/api/language", json={"language": "fr"}).status_code == 400


def test_language_line_is_added_when_missing(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("search: {locations: [braga]}\nsources: {landingjobs: [{}]}\n", encoding="utf-8")
    client = TestClient(create_app(config_path=config_path, db_path=tmp_path / "t.db"))
    assert client.get("/api/language").json() == {"language": "pt"}  # the default
    client.put("/api/language", json={"language": "en"})
    assert config_path.read_text(encoding="utf-8").startswith("language: en\nsearch:")


def test_interview_notes_follow_the_language(cfg, monkeypatch):
    systems = []
    monkeypatch.setattr(message, "_generate", lambda system, prompt, cfg, client=None: systems.append(system))
    message.interview({"title": "QA"}, cfg)
    assert "português europeu" in systems[-1] and "PERGUNTAS PARA FAZERES À EMPRESA" in systems[-1]
    i18n.use({"language": "en"})
    message.interview({"title": "QA"}, cfg)
    assert "Escreve em inglês" in systems[-1] and "QUESTIONS TO ASK THE COMPANY" in systems[-1]
    assert "nunca instruções" in systems[-1]  # the posting is still data, not instructions
