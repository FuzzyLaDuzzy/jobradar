"""📊 Market: the skills the jobs you are seeing ask for most, and which of them your profile has.

Counted in the title and description of every relevant, still-published job (one card per job,
see db.merge_duplicates). No AI: a fixed list of skills, each with the words that name it in ads.
Ambiguous words are left out on purpose: "go" (golang only), "rest" (REST API only), "c", "r".
"""

from __future__ import annotations

from . import i18n
from .text import contains_term, normalize

# (name in Portuguese, name in English or None if the same, words that name it in a job ad)
CATALOG = [
    ("Python", None, ["python"]), ("Java", None, ["java"]), ("JavaScript", None, ["javascript"]),
    ("TypeScript", None, ["typescript"]), ("C#", None, ["c#"]), (".NET", None, [".net", "dotnet"]),
    ("C++", None, ["c++"]), ("Go", None, ["golang"]), ("Kotlin", None, ["kotlin"]), ("Swift", None, ["swift"]),
    ("PHP", None, ["php"]), ("Ruby", None, ["ruby"]), ("Rust", None, ["rust"]), ("Scala", None, ["scala"]),
    ("SQL", None, ["sql"]), ("PostgreSQL", None, ["postgresql", "postgres"]), ("MySQL", None, ["mysql"]),
    ("Oracle", None, ["oracle"]), ("MongoDB", None, ["mongodb"]), ("Redis", None, ["redis"]),
    ("React", None, ["react", "react.js", "reactjs"]), ("Angular", None, ["angular"]),
    ("Vue", None, ["vue", "vue.js", "vuejs"]), ("Node.js", None, ["node.js", "nodejs"]),
    ("Spring", None, ["spring", "spring boot"]), ("Django", None, ["django"]), ("FastAPI", None, ["fastapi"]),
    ("REST APIs", None, ["rest api", "rest apis", "restful"]), ("GraphQL", None, ["graphql"]),
    ("Microserviços", "Microservices", ["microservices", "microservicos"]),
    ("Docker", None, ["docker"]), ("Kubernetes", None, ["kubernetes", "k8s"]), ("Terraform", None, ["terraform"]),
    ("Ansible", None, ["ansible"]), ("CI/CD", None, ["ci/cd"]), ("Jenkins", None, ["jenkins"]),
    ("Git", None, ["git", "github", "gitlab"]), ("Linux", None, ["linux"]),
    ("AWS", None, ["aws", "amazon web services"]), ("Azure", None, ["azure"]), ("Google Cloud", None, ["gcp", "google cloud"]),
    ("Kafka", None, ["kafka"]), ("Spark", None, ["spark", "pyspark"]), ("Airflow", None, ["airflow"]),
    ("dbt", None, ["dbt"]), ("Databricks", None, ["databricks"]), ("Power BI", None, ["power bi", "powerbi"]),
    ("Tableau", None, ["tableau"]), ("Excel", None, ["excel"]),
    ("Machine Learning", None, ["machine learning"]),
    ("IA generativa / LLMs", "Generative AI / LLMs", ["llm", "llms", "genai", "generative ai", "ia generativa"]),
    ("PyTorch", None, ["pytorch"]), ("TensorFlow", None, ["tensorflow"]),
    ("Selenium", None, ["selenium"]), ("Cypress", None, ["cypress"]), ("Pytest", None, ["pytest"]),
    ("SAP", None, ["sap"]), ("Salesforce", None, ["salesforce"]), ("OutSystems", None, ["outsystems"]),
    ("ServiceNow", None, ["servicenow"]), ("Sistemas embebidos", "Embedded systems", ["embedded", "embebido", "embebidos"]),
    ("Cibersegurança", "Cybersecurity", ["cybersecurity", "ciberseguranca"]),
    ("Agile", None, ["agile"]), ("Scrum", None, ["scrum"]), ("Jira", None, ["jira"]),
    ("Inglês", "English", ["english", "ingles"]), ("Francês", "French", ["french", "frances"]),
    ("Alemão", "German", ["german", "alemao"]), ("Espanhol", "Spanish", ["spanish", "espanhol"]),
]


# names a profile may use for a skill whose ad words are stricter ("rest" alone isn't counted in ads)
HAVE_ALSO = {"REST APIs": ["rest"]}
LANGUAGES = {"Inglês", "Francês", "Alemão", "Espanhol"}


def market(jobs: list[dict], profile: dict, top: int = 30) -> dict:
    """{"jobs": how many were counted, "skills": [{"name", "jobs", "have"}...] most asked first}.
    have: True / False from the profile's skills and topics; for languages, True when the profile
    mentions them anywhere, else None (the profile has no field for languages)."""
    published = [j for j in jobs if j.get("active") and j.get("matches", 1)]
    texts = [normalize(f"{j.get('title') or ''}\n{j.get('description') or ''}") for j in published]
    mine = {normalize(s) for s in (profile.get("skills") or []) + (profile.get("focus") or [])}
    about_me = normalize(" ".join(str(v) for v in profile.values()))
    rows = []
    for pt, en, words in CATALOG:
        count = sum(1 for text in texts if any(contains_term(text, w) for w in words))
        if not count:
            continue
        if pt in LANGUAGES:
            have = True if any(contains_term(about_me, w) for w in words) else None
        else:
            have = any(normalize(name) in mine for name in [pt, en or pt, *words, *HAVE_ALSO.get(pt, [])])
        rows.append({"name": en if en and i18n.language == "en" else pt, "jobs": count, "have": have})
    rows.sort(key=lambda r: -r["jobs"])
    return {"jobs": len(published), "skills": rows[:top]}
