const { createApp } = Vue;

const STORAGE_KEY = "jobradar.filters";
const SOURCE_NAMES = {
  itjobs: "ITJobs", sysmatch: "Sysmatch", landingjobs: "Landing.jobs", netempregos: "Net-Empregos", randstad: "Randstad",
  manual: "Adicionada por ti", balancasmarques: "Balanças Marques", workable: "Workable", workinbraga: "Work in Braga",
  smartrecruiters_search: "SmartRecruiters", iefp: "IEFP",
};
const WORK_MODELS = { remote: "Remoto", hybrid: "Híbrido", "on-site": "Presencial", onsite: "Presencial" };
const EMPTY_JOB = () => ({ title: "", company: "", url: "", location: "", notes: "", description: "", posted_at: "" });
const WELCOME_KEY = "jobradar.welcomed";
// the Applications tab: applied, and how it went (like APPLIED in jobradar/db.py)
const APPLIED = ["candidatei", "entrevista", "oferta", "rejeitada"];
const FOLLOW_UP_DAYS = 7; // an application with no reply for this long gets the follow-up reminder
const THEME_KEY = "jobradar.theme"; // "light" or "dark"; none = follow the system (style.css)

function savedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "";
  } catch {
    return "";
  }
}
document.documentElement.dataset.theme = savedTheme(); // before Vue mounts, so the page never flashes
// The API keys and how to get each one (welcome screen, and 🔑 in the settings).
const KEY_GUIDES = [
  {
    key: "ITJOBS_API_KEY", name: "ITJobs.pt", url: "https://www.itjobs.pt/api", site: "itjobs.pt/api",
    what: "Liga a fonte ITJobs.pt, o maior site de emprego em informática em Portugal. Grátis.",
    steps: [
      "Abre itjobs.pt/api.",
      "Na secção «API Key», escreve o teu email e carrega em «Submit».",
      "A chave chega por email: cola-a aqui.",
    ],
  },
  {
    key: "GEMINI_API_KEY", name: "Google Gemini", url: "https://aistudio.google.com/apikey", site: "aistudio.google.com",
    what: "IA grátis: avalia cada vaga, escreve a mensagem de candidatura e prepara a entrevista. Opcional.",
    steps: [
      "Abre aistudio.google.com/apikey e entra com a tua conta Google.",
      "Carrega em «Create API key» (se pedir, aceita os termos e escolhe ou cria um projeto).",
      "Copia a chave e cola-a aqui. O plano grátis tem limites por minuto e por dia.",
    ],
  },
  {
    key: "ANTHROPIC_API_KEY", name: "Anthropic (Claude)", url: "https://console.anthropic.com/settings/keys",
    site: "console.anthropic.com",
    what: "Alternativa paga ao Gemini. Opcional.",
    steps: [
      "Abre console.anthropic.com, cria uma conta e junta créditos em «Billing».",
      "Em «API keys», carrega em «Create Key» e copia a chave.",
      "Cola-a aqui e, no ⚙, muda scoring.llm.provider para anthropic.",
    ],
  },
];
const EMPTY_KEYS = () => Object.fromEntries(KEY_GUIDES.map((g) => [g.key, ""]));

// Texts are written in Portuguese and looked up here by that same text (like jobradar/i18n.py);
// a missing one shows in Portuguese. tests/test_i18n.py checks every t("...") has its English.
const EN = {
  // header and source chips
  "Vagas na tua zona, filtradas e pontuadas para ti": "Jobs in your area, filtered and scored for you",
  "Atualizado {when}": "Updated {when}",
  "Menu": "Menu",
  "+ Adicionar vaga por link": "+ Add job by link",
  "Tema claro": "Light theme",
  "Tema escuro": "Dark theme",
  "Fontes": "Sources",
  "{n} relevantes": "{n} relevant",
  "O que cada fonte trouxe na última procura: relevantes são as que passaram os teus filtros.":
    "What each source brought in the last search: relevant means it passed your filters.",
  "{n} sem vagas relevantes": "{n} with no relevant jobs",
  "Filtros": "Filters",
  "Estado": "Status",
  "★ Guardada": "★ Saved",
  "✕ Descartada": "✕ Discarded",
  "A procurar…": "Searching…",
  "Procurar vagas": "Find jobs",
  "Definições": "Settings",
  "{kept} relevantes de {fetched}": "{kept} relevant of {fetched}",
  " · {n} novas": " · {n} new",
  "Erro: {error}": "Error: {error}",
  "A ler as fontes: {done} de {total}": "Reading the sources: {done} of {total}",
  "A começar…": "Starting…",
  "ainda a ler {names}": "still reading {names}",
  "{n} fontes": "{n} sources",
  "{n} com problemas": "{n} failing",
  "A IA está a avaliar as vagas novas…": "The AI is scoring the new jobs…",
  // tabs and toolbar
  "Estado das vagas": "Job status",
  "Todas": "All", "Novas": "New", "Guardadas": "Saved", "Candidaturas": "Applied", "Descartadas": "Discarded",
  "Pesquisar título, empresa ou tecnologia…": "Search title, company or technology…",
  "Fonte": "Source",
  "Todas as fontes": "All sources",
  "Ordenar": "Sort",
  "Melhor encaixe": "Best fit",
  "Mais recentes": "Most recent",
  "Encaixe mín.": "Min. fit",
  "Mostrar indisponíveis": "Show unavailable",
  // job list
  "Ainda não há vagas": "No jobs yet",
  "Carrega em": "Press",
  "para ler todas as fontes configuradas.": "to read every source you set up.",
  "Nenhuma vaga com estes filtros": "No jobs match these filters",
  "Experimenta baixar o encaixe mínimo ou mudar de separador.": "Try a lower minimum fit or another tab.",
  "Nova": "New",
  "Localização por confirmar": "Location to be confirmed",
  "Candidatei-me a {date}": "Applied on {date}",
  "também em {source}": "also on {source}",
  "Pede {n}+ anos": "Asks for {n}+ years",
  "Já não está publicada": "No longer published",
  "Descrição": "Description",
  "Sem descrição. Abre a vaga para ver os detalhes.": "No description. Open the job to see the details.",
  "Notas (ex.: enviei o CV a 30/10, contacto da recrutadora…)": "Notes (e.g. sent my CV on 30/10, the recruiter's contact…)",
  "A escrever…": "Writing…",
  "↻ Outra versão da mensagem": "↻ Another version of the message",
  "Licença MIT": "MIT License",
  "🧩 Ajustar o CV": "🧩 Tailor my CV",
  "✂ Cortadas": "✂ Cut",
  "Modelo de IA": "AI model",
  "Fontes que parecem avariadas": "Sources that look broken",
  "Foi cortada pela palavra “{word}”.": "It was cut by the word “{word}”.",
  "Deixar de cortar “{word}”": "Stop cutting “{word}”",
  "O título não tem nenhuma das tuas palavras de área. Acrescentar uma?": "The title has none of your field's words. Add one?",
  "Fica fora da tua zona.": "It's outside your area.",
  "Acrescentar “{place}” à zona": "Add “{place}” to your area",
  "Filtro mudado: vale a partir da próxima procura.": "Filter changed: it applies from the next search.",
  "Não foi possível mudar o filtro: {error}": "Couldn't change the filter: {error}",
  "Se for normal (a fonte não tem vagas na tua zona), podes tirá-la das fontes no ⚙.":
    "If that's expected (the source has no jobs in your area), you can remove it from the sources in ⚙.",
  "{source}: deu erro nas últimas {n} procuras ({error})": "{source}: failed in the last {n} searches ({error})",
  "{source}: não trouxe vagas nas últimas {n} procuras (antes trazia {before})":
    "{source}: brought no jobs in the last {n} searches (it used to bring {before})",
  "{source}: ainda não trouxe nenhuma vaga em {n} procuras. O site pode ter mudado, ou não tem vagas na tua zona.":
    "{source}: hasn't brought a single job in {n} searches. The site may have changed, or it has no jobs in your area.",
  "Gemini (Google, grátis)": "Gemini (Google, free)",
  "Claude (Anthropic, pago)": "Claude (Anthropic, paid)",
  "por omissão": "default",
  "Avalia as vagas novas e escreve as mensagens, os ajustes ao CV e a preparação da entrevista. Se um modelo maior estiver ocupado, as mensagens passam para o Gemini 3.5 Flash Lite.":
    "It scores new jobs and writes the messages, the CV tailoring and the interview prep. If a bigger model is busy, messages switch to Gemini 3.5 Flash Lite.",
  "Modelo de IA: {model}": "AI model: {model}",
  "Não foi possível mudar o modelo: {error}": "Couldn't change the model: {error}",
  "Salário indicado no anúncio": "Salary stated in the posting",
  "Salário ≥": "Salary ≥",
  "€/mês": "€/month",
  "Salário mínimo por mês": "Minimum salary per month",
  "As tuas candidaturas, guardadas, descartadas e notas, numa folha para o Excel":
    "Your applications, saved and discarded jobs and notes, in a sheet for Excel",
  "⬇ Exportar CSV": "⬇ Export CSV",
  "O que a última procura leu e os filtros cortaram, com o motivo. Se uma vaga te interessar, guarda-a.":
    "What the last search read and the filters cut, with the reason. If a job interests you, save it.",
  "Motivo": "Reason",
  "Todos os motivos": "All reasons",
  "Nenhuma vaga cortada com estes filtros.": "No cut jobs with these filters.",
  "Guardada ✓": "Saved ✓",
  "＋ Guardar": "＋ Save",
  "Mostrar mais ({n})": "Show more ({n})",
  "A ler…": "Reading…",
  "Ler do link": "Read from link",
  "Descrição lida do link ({n} caracteres).": "Description read from the link ({n} characters).",
  "↻ Analisar de novo": "↻ Analyse again",
  "A analisar…": "Analysing…",
  "Ajustes ao CV": "CV tailoring",
  "Reescrever em inglês": "Rewrite in English",
  "Reescrever em português": "Rewrite in Portuguese",
  "✉ Gerar mensagem de candidatura": "✉ Write application message",
  "A preparar…": "Preparing…",
  "↻ Preparar de novo": "↻ Prepare again",
  "🎯 Preparar entrevista": "🎯 Prepare for the interview",
  "Rascunho da mensagem": "Message draft",
  "Preparação da entrevista": "Interview preparation",
  "Copiar": "Copy",
  "Abrir ↗": "Open ↗",
  "★ Guardar": "★ Save",
  "✓ Candidatei-me": "✓ Applied",
  "✕ Descartar": "✕ Discard",
  "🎤 Entrevista": "🎤 Interview",
  "🏆 Oferta": "🏆 Offer",
  "⛔ Rejeitada": "⛔ Rejected",
  "Entrevistas": "Interviews",
  "Ofertas": "Offers",
  "Rejeitadas": "Rejected",
  "Sem resposta": "No reply yet",
  "Taxa de resposta": "Reply rate",
  "Sem resposta há {n} dias: escrever follow-up": "No reply for {n} days: write a follow-up",
  "✉ Email de seguimento": "✉ Follow-up email",
  "↻ Outro email de seguimento": "↻ Another follow-up email",
  "Email de seguimento": "Follow-up email",
  "Republicada": "Reposted",
  "A empresa voltou a publicar esta vaga: o estado e as notas passaram para aqui.":
    "The company posted this job again: its status and notes moved here.",
  // settings and add job
  "Fechar": "Close",
  "chave encontrada": "key found",
  "falta ITJOBS_API_KEY no .env": "ITJOBS_API_KEY missing from .env",
  "IA (avaliação e mensagens): {state}": "AI (scoring and messages): {state}",
  "desligada (opcional, GEMINI_API_KEY ou ANTHROPIC_API_KEY)": "off (optional, GEMINI_API_KEY or ANTHROPIC_API_KEY)",
  "Edita a zona, o tipo de trabalho, as fontes e o teu perfil. Depois de guardar, carrega em":
    "Edit your area, kind of job, sources and profile. After saving, press",
  "Cancelar": "Cancel",
  "Guardar": "Save",
  "Adicionar vaga": "Add job",
  "Para vagas que encontraste noutro sítio (LinkedIn, um amigo…). Fica nas Guardadas e acompanhas como as outras.":
    "For jobs you found somewhere else (LinkedIn, a friend…). It goes to Saved and you track it like the others.",
  "Título *": "Title *",
  "ex.: Junior Backend Developer": "e.g. Junior Backend Developer",
  "Empresa": "Company",
  "Link da vaga": "Job link",
  "Localização": "Location",
  "ex.: Lisboa (híbrido)": "e.g. Lisbon (hybrid)",
  "Notas": "Notes",
  "Adicionar": "Add",
  // app.js
  "Adicionada por ti": "Added by you",
  "Remoto": "Remote", "Híbrido": "Hybrid", "Presencial": "On-site",
  "Erro {code}": "Error {code}",
  "Não foi possível carregar as vagas: {error}": "Couldn't load the jobs: {error}",
  "{n} vagas novas encontradas": "{n} new jobs found",
  "Sem vagas novas desde a última procura": "No new jobs since the last search",
  "Não foi possível guardar: {error}": "Couldn't save: {error}",
  "Notas guardadas": "Notes saved",
  "Não foi possível guardar as notas: {error}": "Couldn't save the notes: {error}",
  "Não foi possível gerar: {error}": "Couldn't generate: {error}",
  "Copiado": "Copied",
  "Não foi possível copiar: seleciona o texto e usa Ctrl+C": "Couldn't copy: select the text and press Ctrl+C",
  "Vaga adicionada às Guardadas": "Job added to Saved",
  "Não foi possível adicionar: {error}": "Couldn't add: {error}",
  "Definições guardadas": "Settings saved",
  "Não foi possível mudar a língua: {error}": "Couldn't change the language: {error}",
  "Palavras-chave: {n}": "Keywords: {n}",
  "Avaliação IA: {n}": "AI score: {n}",
  "agora mesmo": "just now",
  "há {n} min": "{n} min ago",
  "há {n} h": "{n} h ago",
  "ontem": "yesterday",
  "há {n} dias": "{n} days ago",
  "data desconhecida": "unknown date",
  "publicada hoje": "posted today",
  "publicada ontem": "posted yesterday",
  "publicada há {n} dias": "posted {n} days ago",
  // welcome screen and API keys
  "Boas-vindas ao JobRadar": "Welcome to JobRadar",
  "Chaves de API": "API keys",
  "O JobRadar procura vagas na tua zona em vários sites. Algumas fontes e a IA precisam de uma chave de API: junta as que quiseres, todas são opcionais.":
    "JobRadar looks for jobs in your area on several sites. Some sources and the AI need an API key: add the ones you want, they're all optional.",
  "As chaves ficam só no ficheiro .env deste computador e a app nunca as mostra.":
    "The keys stay only in the .env file on this computer, and the app never shows them.",
  "configurada": "set",
  "em falta": "missing",
  "Abrir {site} ↗": "Open {site} ↗",
  "Já configurada: cola outra para a substituir": "Already set: paste another one to replace it",
  "Cola aqui a chave": "Paste the key here",
  "Depois, escolhe a tua zona, o tipo de trabalho e o teu perfil no ⚙.":
    "Then choose your area, the kind of job and your profile with ⚙.",
  "Agora não": "Not now",
  "Tema": "Theme",
  "Claro": "Light",
  "Escuro": "Dark",
  "Guardar chaves": "Save keys",
  "Chaves guardadas": "Keys saved",
  "Não foi possível guardar as chaves: {error}": "Couldn't save the keys: {error}",
  "Liga a fonte ITJobs.pt, o maior site de emprego em informática em Portugal. Grátis.":
    "Turns on the ITJobs.pt source, the largest IT job board in Portugal. Free.",
  "Abre itjobs.pt/api.": "Open itjobs.pt/api.",
  "Na secção «API Key», escreve o teu email e carrega em «Submit».": "In the “API Key” section, type your email and press “Submit”.",
  "A chave chega por email: cola-a aqui.": "The key arrives by email: paste it here.",
  "IA grátis: avalia cada vaga, escreve a mensagem de candidatura e prepara a entrevista. Opcional.":
    "Free AI: scores each job, writes the application message and prepares the interview. Optional.",
  "Abre aistudio.google.com/apikey e entra com a tua conta Google.": "Open aistudio.google.com/apikey and sign in with your Google account.",
  "Carrega em «Create API key» (se pedir, aceita os termos e escolhe ou cria um projeto).":
    "Press “Create API key” (if asked, accept the terms and choose or create a project).",
  "Copia a chave e cola-a aqui. O plano grátis tem limites por minuto e por dia.":
    "Copy the key and paste it here. The free tier has limits per minute and per day.",
  "Alternativa paga ao Gemini. Opcional.": "Paid alternative to Gemini. Optional.",
  "Abre console.anthropic.com, cria uma conta e junta créditos em «Billing».":
    "Open console.anthropic.com, create an account and add credits under “Billing”.",
  "Em «API keys», carrega em «Create Key» e copia a chave.": "Under “API keys”, press “Create Key” and copy the key.",
  "Cola-a aqui e, no ⚙, muda scoring.llm.provider para anthropic.":
    "Paste it here and, with ⚙, change scoring.llm.provider to anthropic.",
  // ＋ follow a company
  "＋ Seguir empresa": "＋ Follow company",
  "Procurar o site de carreiras da {company} e receber as vagas dela diretamente":
    "Find {company}'s careers site and get its jobs straight from there",
  "Seguir {company}": "Follow {company}",
  "Procuro o site de carreiras da empresa em 10 plataformas com API pública. Se a app o souber ler, passas a receber as vagas dela diretamente, com a descrição completa.":
    "I look for the company's careers site on 10 platforms with a public API. If the app can read it, you get its jobs straight from there, with the full description.",
  "A procurar… (uns segundos)": "Looking… (a few seconds)",
  "Já segues esta empresa.": "You already follow this company.",
  "Não encontrei a {company} em nenhuma das plataformas. As vagas dela continuam a chegar pelos sites de emprego.":
    "I didn't find {company} on any of the platforms. Its jobs keep coming through the job boards.",
  "menciona {place}": "mentions {place}",
  "Seguir": "Follow",
  "A app ainda não lê esta plataforma.": "The app doesn't read this platform yet.",
  "Não foi possível procurar: {error}": "Couldn't look it up: {error}",
  "A {company} passa a ser lida na próxima procura.": "{company} will be read on the next search.",
  "Não foi possível seguir: {error}": "Couldn't follow it: {error}",
  // 📊 market
  "Mercado": "Market",
  "O que as vagas pedem": "What the jobs ask for",
  "Competências mais pedidas nas {n} vagas relevantes e publicadas que a app encontrou, e as que o teu perfil já tem.":
    "The skills asked for most in the {n} relevant, still-published jobs the app found, and the ones your profile already has.",
  "Só as que me faltam": "Only the ones I'm missing",
  "Ainda não há vagas para contar. Carrega em Procurar vagas.": "No jobs to count yet. Press Find jobs.",
  "{n} vagas": "{n} jobs",
  "tens": "you have it",
  "falta": "missing",
  "idioma": "language",
  "Quando aprenderes uma, acrescenta-a no 👤 Perfil: passa a dar pontos nas vagas que a pedem.":
    "When you learn one, add it in 👤 Profile: it then adds points to the jobs that ask for it.",
  "Não foi possível contar as competências: {error}": "Couldn't count the skills: {error}",
  // 👤 profile
  "Perfil": "Profile",
  "O teu perfil": "Your profile",
  "É o que a pontuação, a mensagem de candidatura e a preparação da entrevista usam.":
    "It's what the score, the application message and the interview prep use.",
  "A ler o CV…": "Reading the CV…",
  "Arrasta o teu CV (PDF) para aqui ou clica para o escolher": "Drag your CV (PDF) here or click to choose it",
  "O {ai} lê o CV e preenche os campos em baixo: revê-os antes de guardar. O CV é enviado ao {ai} e não fica guardado.":
    "{ai} reads the CV and fills in the fields below: check them before saving. The CV is sent to {ai} and isn't kept.",
  "Para ler o CV é precisa uma chave de IA (🔑 nas definições). Também podes preencher à mão.":
    "Reading the CV needs an AI key (🔑 in the settings). You can also fill it in by hand.",
  "Quem és": "Who you are",
  "Nome": "Name",
  "Contactos (para a assinatura das mensagens)": "Contacts (for the messages' signature)",
  "telefone · linkedin.com/in/… · github.com/…": "phone · linkedin.com/in/… · github.com/…",
  "O que sabes": "What you know",
  "Competências": "Skills",
  "Temas que te interessam (valem mais pontos)": "Topics you care about (worth more points)",
  "Formação": "Education",
  "Projetos": "Projects",
  "Experiência": "Experience",
  "+ acrescentar": "+ add",
  "Remover": "Remove",
  "Escreve e carrega em Enter": "Type and press Enter",
  "Resumo (o que a IA lê para pontuar as vagas)": "Summary (what the AI reads to score jobs)",
  "Mais factos (texto livre)": "More facts (free text)",
  "O que procuras": "What you're looking for",
  "Posições (palavras que o título da vaga tem de ter)": "Positions (words the job title must have)",
  "Zona (a primeira é a principal)": "Area (the first one is the main one)",
  "aceitar também vagas 100% remotas": "also accept fully remote jobs",
  "Nível": "Level",
  "Só estágio e júnior": "Internships and junior only",
  "Qualquer nível": "Any level",
  "Guardar perfil": "Save profile",
  "Perfil guardado. As pontuações novas aparecem na próxima procura.": "Profile saved. The new scores show up on the next search.",
  "CV lido: revê os campos e carrega em Guardar perfil.": "CV read: check the fields and press Save profile.",
  "Não foi possível ler o CV: {error}": "Couldn't read the CV: {error}",
  "Não foi possível guardar o perfil: {error}": "Couldn't save the profile: {error}",
  "Não foi possível abrir o perfil: {error}": "Couldn't open the profile: {error}",
  "O CV tem mais de 5 MB.": "The CV is larger than 5 MB.",
  // ⚡ triage: the new jobs one at a time
  "{n} vagas novas por decidir": "{n} new jobs to decide on",
  "Triagem rápida": "Quick triage",
  "Triagem": "Triage",
  "{i} de {n}": "{i} of {n}",
  "Saltar": "Skip",
  "Desfazer": "Undo",
  "No telemóvel, desliza a vaga: para a direita guarda, para a esquerda descarta.": "On a phone, swipe the job: right saves it, left discards it.",
  "Acabaste a triagem": "Triage done",
  "{saved} guardadas · {discarded} descartadas · {applied} candidaturas · {skipped} saltadas": "{saved} saved · {discarded} discarded · {applied} applied · {skipped} skipped",
  "Ver as guardadas": "See saved jobs",
  // score reasons, stored in Portuguese by jobradar/scoring.py
  "júnior/estágio": "junior/internship",
  "estágio profissional": "professional internship",
  "zona preferida": "preferred area",
};

function loadFilters() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

const PROFILE_SEEN_KEY = "jobradar.profileSeen";
// sources that list other companies' jobs by the company's name: their cards offer "Follow company"
// (not Sysmatch or Randstad: they are agencies and their jobs name the agency, never the client)
const FOLLOWABLE = new Set(["itjobs", "landingjobs", "netempregos", "workinbraga", "manual"]);
const PLATFORM_NAMES = {
  smartrecruiters: "SmartRecruiters", lever: "Lever", bamboohr: "BambooHR", recruitee: "Recruitee",
  greenhouse: "Greenhouse", workable: "Workable", ashby: "Ashby", personio: "Personio", breezy: "Breezy HR", teamtailor: "Teamtailor",
};
const MAX_CV_BYTES = 5 * 1024 * 1024;
const ITEM_LISTS = ["education", "projects", "experience"];

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]); // drop "data:application/pdf;base64,"
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// A list of short words as removable tags: Enter, a comma or leaving the field adds what was typed.
const ChipList = {
  props: { modelValue: Array, placeholder: String, label: String, removeLabel: String },
  emits: ["update:modelValue"],
  data: () => ({ draft: "" }),
  methods: {
    add() {
      const items = this.draft.split(",").map((s) => s.trim()).filter(Boolean);
      if (items.length) this.$emit("update:modelValue", [...new Set([...this.modelValue, ...items])]);
      this.draft = "";
    },
    remove(i) {
      this.$emit("update:modelValue", this.modelValue.filter((_, j) => j !== i));
    },
    key(e) {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        this.add();
      } else if (e.key === "Backspace" && !this.draft && this.modelValue.length) {
        this.remove(this.modelValue.length - 1);
      }
    },
  },
  template: `<div class="chips">
    <span v-for="(item, i) in modelValue" :key="item" class="chip">{{ item }}<button type="button"
      @click="remove(i)" :aria-label="removeLabel + ' ' + item">✕</button></span>
    <input v-model="draft" @keydown="key" @blur="add" :placeholder="placeholder" :aria-label="label">
  </div>`,
};

createApp({
  data() {
    const saved = loadFilters();
    return {
      lang: "pt",
      theme: savedTheme(),
      systemDark: window.matchMedia("(prefers-color-scheme: dark)").matches,
      jobs: [],
      runs: [],
      sourcesOpen: false, // the sources' window
      menuOpen: false, // ☰ Menu
      filtersOpen: false, // everything but the search, behind "Filters"
      cut: [], // ✂ what the filters cut in the last search, and why
      health: [], // sources that look broken
      cutReason: "",
      cutLimit: 100,
      loading: true,
      refreshing: false,
      progress: null, // while searching: how many sources are read, and the ones still being read
      scoringNow: false, // the AI is scoring the last search's jobs
      error: "",
      tab: saved.tab || "todas",
      query: saved.query || "",
      source: saved.source || "",
      minScore: saved.minScore ?? 0,
      sort: saved.sort || "score",
      showInactive: saved.showInactive || false,
      minSalary: saved.minSalary || 0,
      settingsOpen: false,
      configText: "",
      ai: { current: "", choices: [] }, // ⚙ the AI model
      aiChoice: "",
      savingAi: false,
      configError: "",
      keys: {},
      savingConfig: false,
      addOpen: false,
      newJob: EMPTY_JOB(),
      addError: "",
      adding: false,
      readingLink: false,
      keyGuides: KEY_GUIDES,
      keyStatus: {},
      keysOpen: false,
      firstRun: false,
      newKeys: EMPTY_KEYS(),
      keysError: "",
      savingKeys: false,
      follow: { open: false, company: "", busy: false, saving: false, followed: false, found: [], error: "" },
      justFollowed: [],
      marketOpen: false,
      market: { jobs: 0, skills: [] },
      marketMissingOnly: false,
      profileOpen: false,
      profile: null,
      profileExample: false,
      profileAi: "",
      profileError: "",
      savingProfile: false,
      readingCv: false,
      cvOver: false,
      toast: "",
      // ⚡ triage: the new jobs one at a time; history: what was decided, for Undo; dx: how far a finger dragged the card
      triage: { open: false, queue: [], index: 0, history: [], dir: "", dx: 0, startX: null },
    };
  },

  computed: {
    darkNow() {
      return this.theme ? this.theme === "dark" : this.systemDark;
    },
    tabs() {
      return [
        { key: "todas", label: this.t("Todas") },
        { key: "nova", label: this.t("Novas") },
        { key: "guardada", label: this.t("Guardadas") },
        { key: "candidatei", label: this.t("Candidaturas") },
        { key: "descartada", label: this.t("Descartadas") },
        { key: "cortadas", label: this.t("✂ Cortadas") },
      ];
    },
    visible() {
      return this.jobs.filter((j) => this.showInactive || j.active || APPLIED.includes(j.status));
    },
    counts() {
      const c = { todas: 0, nova: 0, guardada: 0, candidatei: 0, descartada: 0, cortadas: this.cut.length };
      for (const j of this.visible) {
        c[this.tabOf(j)]++;
        if (!["descartada", "rejeitada"].includes(j.status)) c.todas++;
      }
      return c;
    },
    sources() {
      return [...new Set(this.jobs.map((j) => j.source))].sort();
    },
    lastRefresh() {
      const times = this.runs.map((r) => r.finished_at).filter(Boolean).sort();
      return times.length ? times[times.length - 1] : null;
    },
    filtered() {
      if (this.tab === "cortadas") return [];
      const q = this.normalize(this.query);
      let list = this.visible.filter((j) => {
        if (this.tab === "todas" ? ["descartada", "rejeitada"].includes(j.status) : this.tabOf(j) !== this.tab) return false;
        if (this.source && j.source !== this.source) return false;
        if (j.score < this.minScore) return false;
        if (this.minSalary && !(j.salary && j.salary.max >= this.minSalary)) return false;
        if (q) {
          const hay = this.normalize([j.title, j.company, j.location, j.description, j.contract].join(" "));
          if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
        }
        return true;
      });
      const byDate = (a, b) => (b.posted_at || b.first_seen || "").localeCompare(a.posted_at || a.first_seen || "");
      list.sort(this.sort === "date" ? byDate : (a, b) => b.score - a.score || byDate(a, b));
      return list;
    },
    cutReasons() {
      const counts = {};
      for (const c of this.cut) counts[c.category] = (counts[c.category] || 0) + 1;
      return Object.entries(counts).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
    },
    cutFiltered() {
      const q = this.normalize(this.query);
      return this.cut.filter((c) => {
        if (this.cutReason && c.category !== this.cutReason) return false;
        if (this.source && c.source !== this.source) return false;
        const hay = this.normalize([c.title, c.company, c.location].join(" "));
        return !q || q.split(/\s+/).every((w) => hay.includes(w));
      });
    },
    cutShown() {
      return this.cutFiltered.slice(0, this.cutLimit);
    },
    runTotals() {
      const sum = (key) => this.runs.reduce((n, r) => n + (r[key] || 0), 0);
      return { kept: sum("kept"), fetched: sum("fetched"), new: sum("new"), errors: this.runs.filter((r) => r.status === "error").length };
    },
    brokenSources() {
      return new Set(this.health.map((h) => h.source));
    },
    // the "⚠ n failing" on the sources line: an error in the last search, or broken for a few searches
    failingSources() {
      return new Set([...this.brokenSources, ...this.runs.filter((r) => r.status === "error").map((r) => r.source)]);
    },
    // the sources' window: the ones with something to say first (problems, then most relevant jobs), the rest folded
    sourceGroups() {
      const quiet = (r) => r.status === "ok" && !r.kept && !this.brokenSources.has(r.source);
      const rank = (r) => (this.failingSources.has(r.source) ? 0 : r.status === "ok" ? 2 : 1);
      const top = this.runs.filter((r) => !quiet(r)).sort((a, b) => rank(a) - rank(b) || b.kept - a.kept);
      return { top, none: this.runs.filter(quiet) };
    },
    // how many filters are on, for the "Filters · 2" button (the order isn't a filter)
    activeFilters() {
      return [this.source, this.minScore, this.minSalary, this.showInactive].filter(Boolean).length;
    },
    statuses() {
      return [
        { key: "nova", label: this.t("Nova") },
        { key: "guardada", label: this.t("★ Guardada") },
        { key: "candidatei", label: this.t("✓ Candidatei-me") },
        { key: "entrevista", label: this.t("🎤 Entrevista") },
        { key: "oferta", label: this.t("🏆 Oferta") },
        { key: "rejeitada", label: this.t("⛔ Rejeitada") },
        { key: "descartada", label: this.t("✕ Descartada") },
      ];
    },
    // the new jobs still to decide on, best first: what the ⚡ triage goes through
    triageJobs() {
      return this.visible.filter((j) => j.status === "nova" && j.active).sort((a, b) => b.score - a.score);
    },
    triageJob() {
      return this.triage.queue[this.triage.index] || null;
    },
    triageTally() {
      const n = (status) => this.triage.history.filter((h) => h.status === status).length;
      return { saved: n("guardada"), discarded: n("descartada"), applied: n("candidatei"), skipped: n(null) };
    },
    // the Applications tab's summary: how your applications went
    stats() {
      const applied = this.jobs.filter((j) => APPLIED.includes(j.status));
      const n = (status) => applied.filter((j) => j.status === status).length;
      const replied = applied.length - n("candidatei");
      return [
        { label: this.t("Candidaturas"), value: applied.length },
        { label: this.t("Entrevistas"), value: n("entrevista") },
        { label: this.t("Ofertas"), value: n("oferta") },
        { label: this.t("Rejeitadas"), value: n("rejeitada") },
        { label: this.t("Sem resposta"), value: n("candidatei") },
        { label: this.t("Taxa de resposta"), value: applied.length ? Math.round((100 * replied) / applied.length) + "%" : "–" },
      ];
    },
  },

  watch: {
    tab: "persist", query: "persist", source: "persist", minScore: "persist", sort: "persist", showInactive: "persist",
    minSalary: "persist",
    cutReason() {
      this.cutLimit = 100;
    },
  },

  methods: {
    t(text, values = {}) {
      const s = (this.lang === "en" && EN[text]) || text;
      return s.replace(/\{(\w+)\}/g, (m, key) => (key in values ? values[key] : m));
    },

    persist() {
      const { tab, query, source, minScore, sort, showInactive, minSalary } = this;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ tab, query, source, minScore, sort, showInactive, minSalary }));
      } catch {
        /* storage unavailable: filters just won't be remembered */
      }
    },

    async api(path, options = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        // validation errors (422) come as a list: keep only the messages
        const detail = Array.isArray(body.detail)
          ? body.detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ")
          : body.detail;
        throw new Error(detail || this.t("Erro {code}", { code: res.status }));
      }
      return body;
    },

    setLang(lang) {
      this.lang = lang;
      document.documentElement.lang = lang;
    },

    async loadLanguage() {
      try {
        this.setLang((await this.api("/api/language")).language);
      } catch {
        /* keep Portuguese */
      }
    },

    async changeLanguage(language) {
      try {
        this.setLang((await this.api("/api/language", { method: "PUT", body: JSON.stringify({ language }) })).language);
      } catch (e) {
        this.showToast(this.t("Não foi possível mudar a língua: {error}", { error: e.message }));
      }
    },

    // only this browser remembers it: it's how the screen looks, not a search setting
    setTheme(theme) {
      this.theme = theme;
      document.documentElement.dataset.theme = theme;
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch {
        /* storage unavailable: back to the system's theme next time */
      }
    },

    async load() {
      try {
        [this.jobs, this.runs, this.cut, this.health] = await Promise.all(
          [this.api("/api/jobs"), this.api("/api/runs"), this.api("/api/cut"), this.api("/api/health")]);
        this.error = "";
      } catch (e) {
        this.error = this.t("Não foi possível carregar as vagas: {error}", { error: e.message });
      } finally {
        this.loading = false;
      }
    },

    async refresh() {
      this.refreshing = true;
      this.error = "";
      this.progress = { total: 0, done: 0, waiting: [] };
      const poll = setInterval(async () => {
        try {
          this.progress = await this.api("/api/refresh/progress");
        } catch {
          /* the bar just waits for the next one */
        }
      }, 600);
      try {
        const { runs, scoring } = await this.api("/api/refresh", { method: "POST" });
        const fresh = runs.reduce((n, r) => n + (r.new || 0), 0);
        await this.load();
        this.showToast(fresh ? this.t("{n} vagas novas encontradas", { n: fresh }) : this.t("Sem vagas novas desde a última procura"));
        if (fresh) this.tab = "nova";
        if (scoring) this.waitForScores();
      } catch (e) {
        this.error = e.message;
      } finally {
        clearInterval(poll);
        this.progress = null;
        this.refreshing = false;
      }
    },

    // the AI scores the new jobs after the search answers: the list reloads when it's done
    async waitForScores() {
      this.scoringNow = true;
      try {
        while ((await this.api("/api/scoring")).running) await new Promise((r) => setTimeout(r, 4000));
        await this.load();
      } catch {
        /* the scores show on the next reload */
      } finally {
        this.scoringNow = false;
      }
    },

    async setStatus(job, status) {
      const off = APPLIED.includes(status) && status !== "candidatei" ? "candidatei" : "nova";
      const next = job.status === status ? off : status;
      const previous = job.status;
      job.status = next;
      try {
        const saved = await this.api(`/api/jobs/${encodeURIComponent(job.uid)}`, {
          method: "PATCH",
          body: JSON.stringify({ status: next }),
        });
        job.applied_at = saved.applied_at;
      } catch (e) {
        job.status = previous;
        this.showToast(this.t("Não foi possível guardar: {error}", { error: e.message }));
      }
    },

    openTriage() {
      this.triage = { open: true, queue: [...this.triageJobs], index: 0, history: [], dir: "", dx: 0, startX: null };
      this.$nextTick(() => this.$refs.triage && this.$refs.triage.focus());
    },

    closeTriage(tab) {
      this.triage.open = false;
      if (tab) this.tab = tab;
    },

    // the job on screen: "guardada", "descartada" or "candidatei"; null skips it (it stays new)
    decide(status) {
      const tr = this.triage;
      const job = this.triageJob;
      if (!job) return;
      tr.dir = status === "descartada" ? "left" : status ? "right" : "up";
      tr.dx = 0;
      tr.history.push({ job, status });
      tr.index++;
      if (status) this.setStatus(job, status);
    },

    undoTriage() {
      const tr = this.triage;
      const last = tr.history.pop();
      if (!last) return;
      // the same status again puts the job back in New (setStatus toggles)
      if (last.status && last.job.status === last.status) this.setStatus(last.job, last.status);
      tr.dir = "back";
      tr.index--;
    },

    triageKey(e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const keys = {
        ArrowRight: () => this.decide("guardada"),
        ArrowLeft: () => this.decide("descartada"),
        ArrowDown: () => this.decide(null),
        c: () => this.decide("candidatei"),
        z: () => this.undoTriage(),
        Backspace: () => this.undoTriage(),
        o: () => this.triageJob && window.open(this.triageJob.url, "_blank", "noopener"),
        Escape: () => this.closeTriage(),
      };
      const action = keys[e.key.length === 1 ? e.key.toLowerCase() : e.key];
      if (!action) return;
      e.preventDefault();
      action();
    },

    // on a phone the card follows the finger: far enough right saves the job, left discards it
    swipeStart(e) {
      if (e.pointerType !== "mouse") this.triage.startX = e.clientX;
    },

    swipeMove(e) {
      if (this.triage.startX !== null) this.triage.dx = e.clientX - this.triage.startX;
    },

    swipeEnd() {
      const { dx } = this.triage;
      this.triage.startX = null;
      if (dx > 90) this.decide("guardada");
      else if (dx < -90) this.decide("descartada");
      else this.triage.dx = 0;
    },

    async saveNotes(job) {
      try {
        await this.api(`/api/jobs/${encodeURIComponent(job.uid)}`, {
          method: "PATCH",
          body: JSON.stringify({ notes: job.notes }),
        });
        this.showToast(this.t("Notas guardadas"));
      } catch (e) {
        this.showToast(this.t("Não foi possível guardar as notas: {error}", { error: e.message }));
      }
    },

    // kind: "message" (application message), "followup", "interview" or "cv", same endpoint name;
    // language: "pt" or "en" to choose a message's language (by default, the posting's)
    async generate(job, kind, language) {
      job[kind + "Busy"] = true;
      job[kind + "Error"] = "";
      try {
        const query = language ? `?language=${language}` : "";
        const { text } = await this.api(`/api/jobs/${encodeURIComponent(job.uid)}/${kind}${query}`, { method: "POST" });
        job[kind] = text;
        if (language) job[kind + "Language"] = language; // "Another version" keeps it
      } catch (e) {
        job[kind + "Error"] = this.t("Não foi possível gerar: {error}", { error: e.message });
      } finally {
        job[kind + "Busy"] = false;
      }
    },

    tabOf(job) {
      return APPLIED.includes(job.status) ? "candidatei" : job.status;
    },

    inApplications(job) {
      return APPLIED.includes(job.status);
    },

    // days since you applied with no news (still "Applied"): from FOLLOW_UP_DAYS, the card reminds you
    waitingDays(job) {
      if (job.status !== "candidatei" || !job.applied_at) return 0;
      const days = Math.floor((Date.now() - new Date(job.applied_at).getTime()) / 86400000);
      return days >= FOLLOW_UP_DAYS ? days : 0;
    },

    followUp(job) {
      job.descOpen = true; // the email shows under the description
      this.generate(job, "followup", job.followupLanguage);
    },

    healthText(h) {
      const source = this.sourceName(h.source);
      if (h.kind === "error") return this.t("{source}: deu erro nas últimas {n} procuras ({error})", { source, n: h.runs, error: h.message });
      if (h.kind === "empty") return this.t("{source}: não trouxe vagas nas últimas {n} procuras (antes trazia {before})", { source, n: h.runs, before: h.before });
      return this.t("{source}: ainda não trouxe nenhuma vaga em {n} procuras. O site pode ter mudado, ou não tem vagas na tua zona.", { source, n: h.runs });
    },

    // the other language for the draft's button, from its first line: "Assunto: ..." or "Subject: ..."
    otherLanguage(text) {
      return /^\s*assunto\b/i.test(text || "") ? "en" : "pt";
    },

    async copyText(text) {
      try {
        await navigator.clipboard.writeText(text);
        this.showToast(this.t("Copiado"));
      } catch {
        this.showToast(this.t("Não foi possível copiar: seleciona o texto e usa Ctrl+C"));
      }
    },

    shortDate(iso) {
      return new Date(iso).toLocaleDateString(this.lang === "en" ? "en-GB" : "pt-PT");
    },

    openAddJob() {
      this.newJob = EMPTY_JOB();
      this.addError = "";
      this.addOpen = true;
      this.$nextTick(() => this.$refs.newUrl?.focus());
    },

    // ✂ tab, after saving a cut job: the filter change that would have kept it (only if you click it)
    cutTip(c) {
      const word = c.word;
      if ((c.kind === "título sénior" || c.kind === "excluída") && word) {
        return {
          text: this.t("Foi cortada pela palavra “{word}”.", { word }),
          action: "remove", field: c.kind === "título sénior" ? "exclude_title_keywords" : "exclude_keywords", words: [word],
          button: (w) => this.t("Deixar de cortar “{word}”", { word: w }),
        };
      }
      if (c.kind === "fora da área") {
        const skip = new Set(["the", "and", "for", "with", "de", "da", "do", "das", "dos", "para", "com", "em", "e", "m/f"]);
        const words = [...new Set(c.title.toLowerCase().split(/[^\p{L}\p{N}.#+]+/u))]
          .filter((w) => w.length >= 3 && !skip.has(w) && !/^\d+$/.test(w)).slice(0, 4);
        return words.length ? {
          text: this.t("O título não tem nenhuma das tuas palavras de área. Acrescentar uma?"),
          action: "add", field: "title_keywords", words, button: (w) => "＋ " + w,
        } : null;
      }
      const place = (c.location || "").split(",")[0].trim().toLowerCase();
      if (c.kind === "fora da zona" && place) {
        return {
          text: this.t("Fica fora da tua zona."), action: "add", field: "locations", words: [place],
          button: (w) => this.t("Acrescentar “{place}” à zona", { place: w }),
        };
      }
      return null;
    },

    async adjustFilter(c, tip, word) {
      try {
        await this.api("/api/filters", { method: "POST", body: JSON.stringify({ action: tip.action, field: tip.field, word }) });
        c.tipDone = true;
        this.showToast(this.t("Filtro mudado: vale a partir da próxima procura."));
      } catch (e) {
        this.showToast(this.t("Não foi possível mudar o filtro: {error}", { error: e.message }));
      }
    },

    // "+ Add job": the posting at the link fills in the form; you check it, then add it
    async readLink() {
      this.readingLink = true;
      this.addError = "";
      try {
        const job = await this.api("/api/jobs/from-url", { method: "POST", body: JSON.stringify({ url: this.newJob.url }) });
        Object.assign(this.newJob, job);
      } catch (e) {
        this.addError = e.message;
      } finally {
        this.readingLink = false;
      }
    },

    // ✂ tab: a job the filters cut, saved by hand; it joins Saved like any job added there
    async keepCut(c) {
      const job = { title: c.title.slice(0, 200), company: (c.company || "").slice(0, 200), url: c.url || "",
                    location: (c.location || "").slice(0, 200) };
      try {
        await this.api("/api/jobs", { method: "POST", body: JSON.stringify(job) });
        c.kept = true;
        this.jobs = await this.api("/api/jobs");
        this.showToast(this.t("Vaga adicionada às Guardadas"));
      } catch (e) {
        this.showToast(this.t("Não foi possível adicionar: {error}", { error: e.message }));
      }
    },

    async addJob() {
      this.adding = true;
      this.addError = "";
      try {
        await this.api("/api/jobs", { method: "POST", body: JSON.stringify(this.newJob) });
        this.addOpen = false;
        await this.load();
        this.showToast(this.t("Vaga adicionada às Guardadas"));
      } catch (e) {
        this.addError = this.t("Não foi possível adicionar: {error}", { error: e.message });
      } finally {
        this.adding = false;
      }
    },

    // First run: no key set and the welcome screen never closed on this browser.
    async checkWelcome() {
      try {
        this.keyStatus = await this.api("/api/keys");
      } catch {
        return;
      }
      let welcomed = false;
      try {
        welcomed = localStorage.getItem(WELCOME_KEY) === "1";
      } catch {
        /* storage unavailable: show it while no key is set */
      }
      if (!welcomed && !Object.values(this.keyStatus).some(Boolean)) this.openKeys(true);
      else this.offerProfile();
    },

    // While the profile is still the example one, it opens by itself once per browser.
    async offerProfile() {
      try {
        if (localStorage.getItem(PROFILE_SEEN_KEY) === "1") return;
      } catch {
        /* storage unavailable: offer it */
      }
      const data = await this.api("/api/profile").catch(() => null);
      if (data && data.example) this.openProfile(data);
    },

    // Jobs from job boards and agencies (or added by hand) name a company the app may not follow yet.
    canFollow(job) {
      return !!job.company && FOLLOWABLE.has(job.source.split(":")[0]) && !this.justFollowed.includes(job.company);
    },

    async findCompany(company) {
      this.follow = { open: true, company, busy: true, saving: false, followed: false, found: [], error: "" };
      try {
        const { followed, found } = await this.api("/api/discover", { method: "POST", body: JSON.stringify({ company }) });
        Object.assign(this.follow, { followed, found });
      } catch (e) {
        this.follow.error = this.t("Não foi possível procurar: {error}", { error: e.message });
      } finally {
        this.follow.busy = false;
      }
    },

    async followCompany(hit) {
      this.follow.saving = true;
      try {
        await this.api("/api/sources", { method: "POST", body: JSON.stringify({ kind: hit.platform, entry: hit.entry }) });
        this.justFollowed.push(this.follow.company);
        this.follow.open = false;
        this.showToast(this.t("A {company} passa a ser lida na próxima procura.", { company: this.follow.company }));
      } catch (e) {
        this.follow.error = this.t("Não foi possível seguir: {error}", { error: e.message });
      } finally {
        this.follow.saving = false;
      }
    },

    platformName(platform) {
      return PLATFORM_NAMES[platform] || platform;
    },

    async openMarket() {
      try {
        this.market = await this.api("/api/market");
        this.marketOpen = true;
      } catch (e) {
        this.showToast(this.t("Não foi possível contar as competências: {error}", { error: e.message }));
      }
    },

    async openProfile(data = null) {
      this.profileError = "";
      try {
        data = data || (await this.api("/api/profile"));
      } catch (e) {
        this.showToast(this.t("Não foi possível abrir o perfil: {error}", { error: e.message }));
        return;
      }
      this.profile = data.profile;
      this.profileExample = data.example;
      this.profileAi = data.ai;
      this.profileOpen = true;
    },

    closeProfile() {
      this.profileOpen = false;
      try {
        localStorage.setItem(PROFILE_SEEN_KEY, "1");
      } catch {
        /* it will open by itself again next time */
      }
    },

    async readCv(file) {
      this.cvOver = false;
      if (!file) return;
      this.profileError = "";
      if (file.size > MAX_CV_BYTES) {
        this.profileError = this.t("O CV tem mais de 5 MB.");
        return;
      }
      this.readingCv = true;
      try {
        const { profile } = await this.api("/api/profile/cv", {
          method: "POST",
          body: JSON.stringify({ pdf: await fileAsBase64(file) }),
        });
        // what the CV says replaces the fields; what it doesn't say (zone, level...) stays
        for (const [key, value] of Object.entries(profile)) {
          if (value && value.length) this.profile[key] = value;
        }
        if (this.profileExample) this.profile.facts = ""; // the example's placeholder facts
        this.showToast(this.t("CV lido: revê os campos e carrega em Guardar perfil."));
      } catch (e) {
        this.profileError = this.t("Não foi possível ler o CV: {error}", { error: e.message });
      } finally {
        this.readingCv = false;
      }
    },

    addItem(list) {
      this.profile[list].push("");
      this.$nextTick(() => this.$refs[list + "Item"]?.at(-1)?.focus());
    },

    async saveProfile() {
      this.savingProfile = true;
      this.profileError = "";
      const body = { ...this.profile };
      for (const list of ITEM_LISTS) body[list] = body[list].map((s) => s.trim()).filter(Boolean);
      try {
        const data = await this.api("/api/profile", { method: "PUT", body: JSON.stringify(body) });
        this.profileExample = data.example;
        this.closeProfile();
        this.showToast(this.t("Perfil guardado. As pontuações novas aparecem na próxima procura."));
      } catch (e) {
        this.profileError = this.t("Não foi possível guardar o perfil: {error}", { error: e.message });
      } finally {
        this.savingProfile = false;
      }
    },

    openKeys(firstRun = false) {
      this.settingsOpen = false;
      this.firstRun = firstRun;
      this.newKeys = EMPTY_KEYS();
      this.keysError = "";
      this.keysOpen = true;
    },

    closeKeys() {
      this.keysOpen = false;
      try {
        localStorage.setItem(WELCOME_KEY, "1");
      } catch {
        /* the welcome screen will show again next time */
      }
      if (this.firstRun) this.offerProfile(); // first run: keys, then the profile
    },

    async saveKeys() {
      this.savingKeys = true;
      this.keysError = "";
      try {
        this.keyStatus = await this.api("/api/keys", { method: "PUT", body: JSON.stringify(this.newKeys) });
        this.keys = this.keyStatus;
        this.newKeys = EMPTY_KEYS(); // never keep a key in the page longer than needed
        this.closeKeys();
        this.showToast(this.t("Chaves guardadas"));
      } catch (e) {
        this.keysError = this.t("Não foi possível guardar as chaves: {error}", { error: e.message });
      } finally {
        this.savingKeys = false;
      }
    },

    async openSettings() {
      this.configError = "";
      try {
        const data = await this.api("/api/config");
        this.configText = data.yaml;
        this.keys = data.keys;
        this.settingsOpen = true;
        this.api("/api/ai").then((ai) => {
          this.ai = ai;
          this.aiChoice = ai.current;
        }).catch(() => {}); // without it, the select just stays empty
      } catch (e) {
        this.error = e.message;
      }
    },

    async saveAi() {
      this.savingAi = true;
      try {
        await this.api("/api/ai", { method: "PUT", body: JSON.stringify({ choice: this.aiChoice }) });
        this.ai.current = this.aiChoice;
        this.configText = (await this.api("/api/config")).yaml; // the text below now has the new model
        const choice = this.ai.choices.find((c) => c.id === this.aiChoice);
        this.showToast(this.t("Modelo de IA: {model}", { model: choice ? choice.label : this.aiChoice }));
      } catch (e) {
        this.aiChoice = this.ai.current;
        this.showToast(this.t("Não foi possível mudar o modelo: {error}", { error: e.message }));
      } finally {
        this.savingAi = false;
      }
    },

    async saveConfig() {
      this.savingConfig = true;
      this.configError = "";
      try {
        await this.api("/api/config", { method: "PUT", body: JSON.stringify({ yaml: this.configText }) });
        this.settingsOpen = false;
        await this.loadLanguage(); // the language may have been changed in the file
        this.showToast(this.t("Definições guardadas"));
      } catch (e) {
        this.configError = e.message;
      } finally {
        this.savingConfig = false;
      }
    },

    showToast(message) {
      this.toast = message;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => (this.toast = ""), 3500);
    },

    // a company's own careers site needs no badge on its jobs: "Accenture" under Accenture says nothing new
    sourceIsCompany(job) {
      const source = this.normalize(this.sourceName(job.source));
      const company = this.normalize(job.company);
      return Boolean(company) && (company.includes(source) || source.includes(company));
    },

    normalize(text) {
      return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
    },

    sourceName(source) {
      if (SOURCE_NAMES[source]) return this.t(SOURCE_NAMES[source]);
      const value = source.split(":").slice(1).join(":") || source;
      const name = value.replace(/Group$/, "").replace(/_/g, " ");
      return name.charAt(0).toUpperCase() + name.slice(1);
    },

    scoreClass(score) {
      return score >= 70 ? "high" : score >= 45 ? "mid" : "low";
    },

    scoreTitle(job) {
      const parts = [this.t("Palavras-chave: {n}", { n: job.kw_score })];
      if (job.llm_score != null) parts.push(this.t("Avaliação IA: {n}", { n: job.llm_score }));
      return parts.join(" · ");
    },

    isNew(job) {
      if (job.status !== "nova" || !job.first_seen) return false;
      return Date.now() - new Date(job.first_seen).getTime() < 48 * 3600 * 1000;
    },

    relative(iso) {
      const diff = (Date.now() - new Date(iso).getTime()) / 1000;
      if (diff < 60) return this.t("agora mesmo");
      if (diff < 3600) return this.t("há {n} min", { n: Math.round(diff / 60) });
      if (diff < 86400) return this.t("há {n} h", { n: Math.round(diff / 3600) });
      const days = Math.round(diff / 86400);
      return days === 1 ? this.t("ontem") : this.t("há {n} dias", { n: days });
    },

    posted(job) {
      if (!job.posted_at) return this.t("data desconhecida");
      const days = Math.floor((Date.now() - new Date(job.posted_at + "T12:00:00").getTime()) / 86400000);
      if (days <= 0) return this.t("publicada hoje");
      if (days === 1) return this.t("publicada ontem");
      return this.t("publicada há {n} dias", { n: days });
    },

    workModel(value) {
      return WORK_MODELS[value] ? this.t(WORK_MODELS[value]) : value;
    },

    initials(company) {
      return (company || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    },
  },

  mounted() {
    this.loadLanguage();
    this.load();
    // ☰ Menu: a click anywhere (one of its items too) or Esc closes it; its own button stops the click
    document.addEventListener("click", () => (this.menuOpen = false));
    document.addEventListener("keydown", (e) => e.key === "Escape" && (this.menuOpen = false));
    // links straight to a screen: /#mercado, /#perfil
    if (location.hash === "#mercado") this.openMarket();
    else if (location.hash === "#perfil") this.openProfile();
    else this.checkWelcome();
  },
})
  .component("chip-list", ChipList)
  .mount("#app");
