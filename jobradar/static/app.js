const { createApp } = Vue;

const STORAGE_KEY = "jobradar.filters";
const SOURCE_NAMES = {
  itjobs: "ITJobs", sysmatch: "Sysmatch", landingjobs: "Landing.jobs", netempregos: "Net-Empregos", randstad: "Randstad",
  manual: "Adicionada por ti", balancasmarques: "Balanças Marques", workable: "Workable", workinbraga: "Work in Braga",
};
const WORK_MODELS = { remote: "Remoto", hybrid: "Híbrido", "on-site": "Presencial", onsite: "Presencial" };
const EMPTY_JOB = () => ({ title: "", company: "", url: "", location: "", notes: "" });
const WELCOME_KEY = "jobradar.welcomed";
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
  "+ Adicionar vaga": "+ Add job",
  "A procurar…": "Searching…",
  "Procurar vagas": "Find jobs",
  "Definições": "Settings",
  "{kept} relevantes de {fetched}": "{kept} relevant of {fetched}",
  " · {n} novas": " · {n} new",
  "Erro: {error}": "Error: {error}",
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
  "Mudar para tema claro": "Switch to light theme",
  "Mudar para tema escuro": "Switch to dark theme",
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
      loading: true,
      refreshing: false,
      error: "",
      tab: saved.tab || "todas",
      query: saved.query || "",
      source: saved.source || "",
      minScore: saved.minScore ?? 0,
      sort: saved.sort || "score",
      showInactive: saved.showInactive || false,
      settingsOpen: false,
      configText: "",
      configError: "",
      keys: {},
      savingConfig: false,
      addOpen: false,
      newJob: EMPTY_JOB(),
      addError: "",
      adding: false,
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
      ];
    },
    visible() {
      return this.jobs.filter((j) => this.showInactive || j.active || j.status === "candidatei");
    },
    counts() {
      const c = { todas: 0, nova: 0, guardada: 0, candidatei: 0, descartada: 0 };
      for (const j of this.visible) {
        c[j.status] = (c[j.status] || 0) + 1;
        if (j.status !== "descartada") c.todas++;
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
      const q = this.normalize(this.query);
      let list = this.visible.filter((j) => {
        if (this.tab === "todas" ? j.status === "descartada" : j.status !== this.tab) return false;
        if (this.source && j.source !== this.source) return false;
        if (j.score < this.minScore) return false;
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
  },

  watch: {
    tab: "persist", query: "persist", source: "persist", minScore: "persist", sort: "persist", showInactive: "persist",
  },

  methods: {
    t(text, values = {}) {
      const s = (this.lang === "en" && EN[text]) || text;
      return s.replace(/\{(\w+)\}/g, (m, key) => (key in values ? values[key] : m));
    },

    persist() {
      const { tab, query, source, minScore, sort, showInactive } = this;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ tab, query, source, minScore, sort, showInactive }));
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
        [this.jobs, this.runs] = await Promise.all([this.api("/api/jobs"), this.api("/api/runs")]);
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
      try {
        const { runs } = await this.api("/api/refresh", { method: "POST" });
        const fresh = runs.reduce((n, r) => n + (r.new || 0), 0);
        await this.load();
        this.showToast(fresh ? this.t("{n} vagas novas encontradas", { n: fresh }) : this.t("Sem vagas novas desde a última procura"));
      } catch (e) {
        this.error = e.message;
      } finally {
        this.refreshing = false;
      }
    },

    async setStatus(job, status) {
      const next = job.status === status ? "nova" : status;
      const previous = job.status;
      job.status = next;
      try {
        await this.api(`/api/jobs/${encodeURIComponent(job.uid)}`, {
          method: "PATCH",
          body: JSON.stringify({ status: next }),
        });
      } catch (e) {
        job.status = previous;
        this.showToast(this.t("Não foi possível guardar: {error}", { error: e.message }));
      }
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

    // kind: "message" (application message) or "interview" (interview prep), same endpoint name;
    // language: "pt" or "en" to choose the message's language (by default, the posting's)
    async generate(job, kind, language) {
      job[kind + "Busy"] = true;
      job[kind + "Error"] = "";
      try {
        const query = language ? `?language=${language}` : "";
        const { text } = await this.api(`/api/jobs/${encodeURIComponent(job.uid)}/${kind}${query}`, { method: "POST" });
        job[kind] = text;
        if (language) job.messageLanguage = language; // "Another version" keeps it
      } catch (e) {
        job[kind + "Error"] = this.t("Não foi possível gerar: {error}", { error: e.message });
      } finally {
        job[kind + "Busy"] = false;
      }
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
      this.$nextTick(() => this.$refs.newTitle?.focus());
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
      } catch (e) {
        this.error = e.message;
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
    // links straight to a screen: /#mercado, /#perfil
    if (location.hash === "#mercado") this.openMarket();
    else if (location.hash === "#perfil") this.openProfile();
    else this.checkWelcome();
  },
})
  .component("chip-list", ChipList)
  .mount("#app");
