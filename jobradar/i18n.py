"""Português or English, from `language` in config.yaml (the PT/EN button changes it).

Texts are written in Portuguese where they are used and looked up here by that same
text, so a missing translation shows the Portuguese one instead of breaking.
tests/test_i18n.py checks that every t("...") in the code has its English text.
"""

from __future__ import annotations

LANGUAGES = ("pt", "en")
# One global: JobRadar is a single-user local app, so one language at a time.
language = "pt"

EN = {
    # config.py
    "YAML inválido: {error}": "Invalid YAML: {error}",
    "A configuração tem de ser um mapa YAML.": "The configuration must be a YAML map.",
    "Falta a secção '{section}'.": "The '{section}' section is missing.",
    "{field} tem de ser uma lista.": "{field} must be a list.",
    "{field} tem de ser um mapa.": "{field} must be a map.",
    "search.locations não pode estar vazio.": "search.locations can't be empty.",
    "Fonte desconhecida: {kind} (usa {known}).": "Unknown source: {kind} (use {known}).",
    "{entry} precisa de '{field}'.": "{entry} needs '{field}'.",
    "scoring.llm.provider tem de ser {options}.": "scoring.llm.provider must be {options}.",
    "language tem de ser {options}.": "language must be {options}.",
    "Não foi possível gravar: a secção '{section}' do config.yaml tem um formato que a app não sabe editar. "
    "Edita-a no ⚙.":
        "Couldn't save: the '{section}' section of config.yaml has a layout the app can't edit. Edit it with ⚙.",
    "Não foi possível gravar {field}: confirma o valor.": "Couldn't save {field}: check the value.",
    # profile.py and its endpoints
    "A IA não conseguiu ler o CV. Tenta outra vez ou preenche à mão.":
        "The AI couldn't read the CV. Try again or fill it in by hand.",
    "O ficheiro não é um PDF.": "The file isn't a PDF.",
    "O CV tem mais de 5 MB.": "The CV is larger than 5 MB.",
    "cada item pode ter até {n} caracteres": "each item can have up to {n} characters",
    # app.py
    "o link tem de começar por http:// ou https://": "the link must start with http:// or https://",
    "Vaga não encontrada": "Job not found",
    "Configuração inválida: {error}": "Invalid configuration: {error}",
    "Falta {key} no .env (cria a chave em {where}).": "{key} is missing from .env (create the key at {where}).",
    "A ANTHROPIC_API_KEY foi recusada. Confirma a chave no .env.":
        "ANTHROPIC_API_KEY was refused. Check the key in .env.",
    "Demasiados pedidos à API da Anthropic. Tenta daqui a um minuto.":
        "Too many requests to the Anthropic API. Try again in a minute.",
    "A API da Anthropic respondeu com o erro {code}.": "The Anthropic API answered with error {code}.",
    "Sem ligação à API da Anthropic.": "No connection to the Anthropic API.",
    "Estado inválido. Usa: {options}": "Invalid status. Use: {options}",
    "Já há uma atualização a correr.": "A refresh is already running.",
    "Pedido recusado: vem de outro site.": "Request refused: it comes from another site.",
    "entrada inválida": "invalid entry",
    "A app ainda não lê esta plataforma.": "The app doesn't read this platform yet.",
    "a chave só pode ter letras, números, '-', '_' e '.'": "a key can only have letters, numbers, '-', '_' and '.'",
    # gemini.py, message.py
    "Atingiste o limite do plano gratuito do Gemini. Tenta daqui a uns minutos.":
        "You've reached the Gemini free tier limit. Try again in a few minutes.",
    "O Gemini está com muita procura neste momento. Tenta daqui a uns minutos.":
        "Gemini is very busy right now. Try again in a few minutes.",
    "A GEMINI_API_KEY foi recusada. Cria uma chave nova no Google AI Studio.":
        "GEMINI_API_KEY was refused. Create a new key in Google AI Studio.",
    "A API do Gemini respondeu com o erro {code}. {detail}": "The Gemini API answered with error {code}. {detail}",
    "O Gemini demorou demasiado a responder. Tenta outra vez.": "Gemini took too long to answer. Try again.",
    "Sem ligação à API do Gemini.": "No connection to the Gemini API.",
    "O Gemini bloqueou o pedido ({reason}).": "Gemini blocked the request ({reason}).",
    "O Gemini não devolveu texto ({reason}).": "Gemini returned no text ({reason}).",
    "O modelo recusou este pedido.": "The model declined this request.",
    "O modelo não devolveu nenhum texto.": "The model returned no text.",
    # sources
    "Falta ITJOBS_API_KEY no .env (pede-a grátis em itjobs.pt/api)":
        "ITJOBS_API_KEY is missing from .env (get one free at itjobs.pt/api)",
    "ITJobs: {message}. Confirma a chave no .env (ITJOBS_API_KEY=..., sem espaços nem aspas) e que é a que "
    "recebeste por email de itjobs.pt/api.":
        "ITJobs: {message}. Check the key in .env (ITJOBS_API_KEY=..., no spaces or quotes) and that it is the "
        "one itjobs.pt/api emailed you.",
    "Zoho Recruit: {url} sem a lista de vagas (a página mudou?)":
        "Zoho Recruit: {url} has no job list (did the page change?)",
    # notify.py
    "1 vaga nova": "1 new job",
    "{n} vagas novas": "{n} new jobs",
    " (e mais {n})": " (and {n} more)",
    # discover.py
    "A procurar {n} empresas em {platforms} plataformas (demora uns segundos por empresa)...":
        "Looking up {n} companies on {platforms} platforms (a few seconds per company)...",
    ", menciona {place}": ", mentions {place}",
    "{name}: {platform}/{slug} ({jobs} vagas{where}).": "{name}: {platform}/{slug} ({jobs} jobs{where}).",
    "Para a seguir, acrescenta às `sources` do config.yaml:": "To follow it, add this to `sources` in config.yaml:",
    "O JobRadar ainda não lê esta plataforma.": "JobRadar doesn't read this platform yet.",
    "Nenhuma das empresas tem um site de carreiras numa plataforma conhecida.":
        "None of these companies has a careers site on a known platform.",
    # __main__.py
    "Criei {path} a partir do exemplo: muda a zona, a área e o perfil no ⚙ da app ou no ficheiro.":
        "Created {path} from the example: set your area, kind of job and profile with the ⚙ button or in the file.",
    "lidas": "read",
    "mantidas": "kept",
    "novas": "new",
    "JobRadar a correr em {url}  (Ctrl+C para parar)": "JobRadar running at {url}  (Ctrl+C to stop)",
    # why the filters cut a job (the ✂ tab)
    "título sénior": "senior title",
    "excluída": "excluded",
    "fora da área": "not your kind of job",
    "fora da zona": "outside your area",
    "antiga": "too old",
    "suspeita de burla": "looks like a scam",
    "empresa excluída": "excluded company",
    # the CSV export
    "Estado": "Status",
    "Nova": "New",
    "Guardada": "Saved",
    "Candidatei": "Applied",
    "Descartada": "Discarded",
    "Empresa": "Company",
    "Vaga": "Job",
    "Localização": "Location",
    "Salário": "Salary",
    "Fonte": "Source",
    "Link": "Link",
    "Publicada": "Posted",
    "Candidatei em": "Applied on",
    "Encaixe": "Fit",
    "Notas": "Notes",
    "jobradar-candidaturas.csv": "jobradar-applications.csv",
    # + Add job, from a link
    "Este site não deixa ler as vagas por programas: preenche os campos à mão.":
        "This site doesn't let programs read its jobs: fill in the fields by hand.",
    "Não foi possível abrir o link ({error}).": "Couldn't open the link ({error}).",
    "A página é grande demais para ler.": "The page is too big to read.",
    "Não encontrei uma vaga nesta página: preenche os campos à mão.":
        "I couldn't find a job on this page: fill in the fields by hand.",
}


def use(cfg: dict) -> None:
    global language
    language = cfg.get("language") if cfg.get("language") in LANGUAGES else "pt"


def t(text: str, **values) -> str:
    if language == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text
