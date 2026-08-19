/* ══════════════════════════════════════════════════════════════════
   Sling TSi — Leitor de Checklist (PWA)

   Porte de "Leitor de Checklist.py" para o navegador: mesma hierarquia
   (grupos -> subgrupos -> checklists -> itens), mesma leitura guiada e os
   mesmos tres comandos de voz — "check" avanca, "pular" deixa pendente e
   "repetir" le de novo.
   ══════════════════════════════════════════════════════════════════ */
'use strict';

const CHECKLIST_URL = 'data/Checklists-PB.json';
const URL_REDEMET = 'https://redemet-app.decea.mil.br/';
const URL_AISWEB = 'https://aisweb.decea.mil.br/';
const SETTINGS_KEY = 'sling_tsi.settings';
const PROGRESS_KEY = 'sling_tsi.progresso';

// o progresso so e retomado dentro desta janela: um checklist marcado ontem
// nao pode reaparecer como se fosse do voo de hoje
const PROGRESS_MAX_MS = 4 * 60 * 60 * 1000;

// o nome do arquivo da lugar ao aviso de uso e a matricula nao vai para a tela
const METADATA_SKIP = ['name', 'aircraftInfo'];

const DISCLAIMER =
  'Aplicativo desenvolvido para uso pessoal. Nenhuma das informações ' +
  'contidas aqui devem ser consideradas e substituem os documentos ' +
  'oficiais da Aeronave';

const HINT_VOICE =
  'Diga “check” para avançar, “pular” para deixar o item pendente ou ' +
  '“repetir” para ouvir de novo.';
const HINT_NO_LISTEN =
  'Este navegador não reconhece voz: use os botões Check, Pular e Repetir ' +
  'para percorrer a lista.';
const HINT_INSECURE =
  'Os comandos de voz exigem uma conexão segura (HTTPS): neste endereço o ' +
  'navegador bloqueia o microfone. A leitura em voz alta e os botões Check, ' +
  'Pular e Repetir continuam funcionando.';

// o reconhecimento devolve texto livre: cada comando aceita as formas que o
// pt-BR costuma transcrever ("check" vira "xeque", "cheque"...)
const COMMAND_FORMS = {
  check: ['check', 'checar', 'chec', 'xeque', 'cheque', 'tcheque', 'chek'],
  pular: ['pular', 'pula', 'pulo', 'proximo', 'proxima'],
  repetir: ['repetir', 'repete', 'repita', 'de novo', 'novamente'],
};

function stripAccents(text) {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function matchCommand(text) {
  const words = stripAccents(String(text || '').toLowerCase());
  for (const [command, forms] of Object.entries(COMMAND_FORMS)) {
    if (forms.some((form) => words.includes(form))) return command;
  }
  return null;
}

// ══════════════════════════════════════════════════════════════════
//  PREFERENCIAS
// ══════════════════════════════════════════════════════════════════
function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
  } catch (err) {
    return {};
  }
}

function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (err) {
    /* modo privado do Safari: segue sem gravar */
  }
}

// ══════════════════════════════════════════════════════════════════
//  VOZ  — sintese e reconhecimento do proprio navegador
// ══════════════════════════════════════════════════════════════════
const Recognition =
  window.SpeechRecognition || window.webkitSpeechRecognition || null;

const Voice = {
  synth: window.speechSynthesis || null,
  voice: null,
  recognizer: null,
  wantListen: false,
  speaking: false,
  errors: 0,
  handlers: {},

  get canSpeak() { return this.synth !== null; },

  /**
   * O reconhecimento so existe em contexto seguro (HTTPS ou localhost): em
   * `http://` comum o navegador nem expoe a API, ou recusa o microfone.
   */
  get canListen() { return Recognition !== null && window.isSecureContext; },

  /** Por que a escuta nao esta disponivel — para avisar o piloto direito. */
  get listenBlockedReason() {
    if (!window.isSecureContext) {
      return 'Os comandos de voz exigem uma conexao segura (HTTPS). ' +
        'Neste endereco o navegador bloqueia o microfone.';
    }
    if (!Recognition) return 'Este navegador nao reconhece voz.';
    return '';
  },

  /** Escolhe a voz pt-BR; no iOS a lista chega depois do carregamento. */
  pickVoice() {
    if (!this.synth) return;
    const voices = this.synth.getVoices();
    if (!voices.length) return;
    this.voice =
      voices.find((v) => v.lang === 'pt-BR' || v.lang === 'pt_BR') ||
      voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('pt')) ||
      null;
  },

  /** -10..10 como no leitor do Windows; 1.0 e a velocidade normal daqui. */
  rateFor(rate) {
    return Math.min(2, Math.max(0.5, 1 + Number(rate || 0) / 20));
  },

  speak(text, rate) {
    if (!this.synth || !text) return;
    this.stopSpeaking();
    // enquanto fala, o microfone fica fechado: senao o reconhecedor escuta
    // a propria leitura e dispara comandos sozinho
    this.suspendListening();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'pt-BR';
    utterance.rate = this.rateFor(rate);
    if (this.voice) utterance.voice = this.voice;
    utterance.onend = utterance.onerror = () => {
      this.speaking = false;
      this.resumeListening();
    };

    this.speaking = true;
    // o Safari ignora um speak() disparado no mesmo tique de um cancel()
    setTimeout(() => {
      if (this.speaking) this.synth.speak(utterance);
    }, 60);
  },

  stopSpeaking() {
    this.speaking = false;
    if (this.synth) this.synth.cancel();
  },

  // ── escuta continua ─────────────────────────────────────────────
  startListening(handlers) {
    if (!this.canListen) return false;
    this.handlers = handlers || {};
    this.wantListen = true;
    this.errors = 0;
    this._start();
    return true;
  },

  stopListening() {
    this.wantListen = false;
    this._stop();
  },

  suspendListening() { if (this.wantListen) this._stop(); },
  resumeListening() { if (this.wantListen) this._start(); },

  _start() {
    if (this.recognizer || this.speaking) return;
    const recognizer = new Recognition();
    recognizer.lang = 'pt-BR';
    recognizer.continuous = false;
    recognizer.interimResults = true;
    recognizer.maxAlternatives = 3;

    recognizer.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        for (let a = 0; a < result.length; a++) {
          const command = matchCommand(result[a].transcript);
          if (command) {
            this.errors = 0;
            if (this.handlers.onCommand) this.handlers.onCommand(command);
            return;
          }
        }
      }
    };

    recognizer.onerror = (event) => {
      // sem fala e aborto sao rotina: a rodada apenas recomeca
      if (event.error === 'no-speech' || event.error === 'aborted') return;
      this.errors += 1;
      if (event.error === 'not-allowed' || this.errors > 3) {
        this.wantListen = false;
        if (this.handlers.onError) this.handlers.onError(event.error);
      }
    };

    recognizer.onend = () => {
      this.recognizer = null;
      if (this.wantListen && !this.speaking) this._start();
      else if (!this.wantListen && this.handlers.onStop) this.handlers.onStop();
    };

    this.recognizer = recognizer;
    try {
      recognizer.start();
    } catch (err) {
      this.recognizer = null;
    }
  },

  _stop() {
    const recognizer = this.recognizer;
    this.recognizer = null;
    if (recognizer) {
      try { recognizer.onend = null; recognizer.stop(); } catch (err) { /* ok */ }
    }
  },
};

if (Voice.synth) {
  Voice.pickVoice();
  Voice.synth.addEventListener('voiceschanged', () => Voice.pickVoice());
}

// ══════════════════════════════════════════════════════════════════
//  DOM
// ══════════════════════════════════════════════════════════════════
function el(tag, props, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children || []) if (child) node.appendChild(child);
  return node;
}

function section(title, children, extraClass) {
  const box = el('section', { class: 'sec' + (extraClass ? ' ' + extraClass : '') });
  if (title) {
    box.appendChild(el('div', { class: 'sec-head' }, [el('span', { text: title })]));
  }
  for (const child of children) if (child) box.appendChild(child);
  return box;
}

function rowButton(name, tag, onClick) {
  return el('button', { class: 'row-btn', type: 'button', onclick: onClick }, [
    el('span', { class: 'label' }, [
      el('span', { class: 'name', text: name }),
      tag ? el('span', { class: 'tag', text: tag }) : null,
    ]),
    el('span', { class: 'chev', text: '›', 'aria-hidden': 'true' }),
  ]);
}

// ══════════════════════════════════════════════════════════════════
//  NAVEGACAO  — pilha de telas com o botao voltar do sistema
// ══════════════════════════════════════════════════════════════════
const bar = document.getElementById('bar');
const controlsBar = document.getElementById('controls');
const content = document.getElementById('content');

const stack = [];
let reader = null;

function render() {
  const screen = stack[stack.length - 1];
  if (reader) { reader.stop(); reader = null; }
  Voice.stopSpeaking();
  Voice.stopListening();

  bar.textContent = '';
  controlsBar.textContent = '';
  controlsBar.hidden = true;
  content.textContent = '';
  window.scrollTo(0, 0);

  document.title = screen.title
    ? `Sling TSi · ${screen.title}`
    : 'Sling TSi · Aplicativos';

  if (stack.length > 1) {
    bar.appendChild(
      el('button', { class: 'btn', type: 'button', onclick: () => history.back() },
        [document.createTextNode('‹  Voltar')]));
  }
  screen.header(bar);
  screen.body(content);
}

function go(screen) {
  stack.push(screen);
  history.pushState({ depth: stack.length }, '');
  render();
}

window.addEventListener('popstate', () => {
  if (stack.length > 1) {
    stack.pop();
    render();
  }
});

function titleHeader(text) {
  return (host) => {
    host.appendChild(el('h1', { text }));
    host.appendChild(el('span', { class: 'dash', text: '—', 'aria-hidden': 'true' }));
  };
}

// ══════════════════════════════════════════════════════════════════
//  LEITURA GUIADA
// ══════════════════════════════════════════════════════════════════
class Reader {
  constructor(key) {
    this.key = key || '';
    this.entries = [];
    this.lastText = '';
    this.nextIndex = 0;
    this.lastChallenge = null;
    this.searchStart = 0;
    this.listening = false;
    this.rate = Number(loadSettings().speed || 0);
  }

  add(text, entry) {
    this.entries.push(Object.assign({ text: text, box: null, row: null }, entry));
  }

  firstUnchecked(start) {
    for (let i = start; i < this.entries.length; i++) {
      const box = this.entries[i].box;
      if (box && !box.checked) return i;
    }
    return null;
  }

  mark(index, done) {
    const entry = this.entries[index];
    if (!entry || !entry.box) return;
    entry.box.checked = done;
    entry.row.classList.toggle('done', done);
    this.saveProgress();
  }

  // ── progresso: o iOS encerra o app em segundo plano sem avisar, e um
  //    checklist pela metade nao pode se perder no meio do voo ──────
  saveProgress() {
    if (!this.key) return;
    const marcados = [];
    this.entries.forEach((entry, i) => {
      if (entry.box && entry.box.checked) marcados.push(i);
    });
    try {
      if (!marcados.length) localStorage.removeItem(PROGRESS_KEY);
      else localStorage.setItem(PROGRESS_KEY, JSON.stringify({
        chave: this.key, marcados: marcados, quando: Date.now(),
      }));
    } catch (err) { /* modo privado do Safari */ }
  }

  /** Devolve o horario retomado, ou null se nao havia nada para retomar. */
  restoreProgress() {
    let dados;
    try {
      dados = JSON.parse(localStorage.getItem(PROGRESS_KEY));
    } catch (err) {
      return null;
    }
    if (!dados || dados.chave !== this.key) return null;
    if (Date.now() - dados.quando > PROGRESS_MAX_MS) return null;

    let ultimo = null;
    for (const i of dados.marcados) {
      const entry = this.entries[i];
      if (!entry || !entry.box) continue;
      entry.box.checked = true;
      entry.row.classList.add('done');
      ultimo = i;
    }
    if (ultimo === null) return null;
    // a leitura recomeca do primeiro item ainda pendente
    this.lastChallenge = null;
    this.nextIndex = ultimo + 1;
    return new Date(dados.quando);
  }

  clearProgress() {
    for (const entry of this.entries) {
      if (!entry.box) continue;
      entry.box.checked = false;
      entry.row.classList.remove('done');
    }
    this.lastChallenge = null;
    this.nextIndex = 0;
    this.searchStart = 0;
    try {
      localStorage.removeItem(PROGRESS_KEY);
    } catch (err) { /* modo privado do Safari */ }
  }

  scrollTo(index) {
    const row = this.entries[index] && this.entries[index].row;
    if (row) row.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  say(text) {
    this.lastText = text;
    Voice.speak(text, this.rate);
  }

  /** Marca o desafio pendente e le ate o proximo — o comando "check". */
  check() {
    if (!this.entries.length) return;
    if (this.lastChallenge !== null) this.mark(this.lastChallenge, true);

    const first = this.firstUnchecked(this.searchStart);
    let text;
    if (first === null) {
      text = 'Checklist completo.';
    } else {
      const start = Math.min(this.nextIndex, first);
      text = this.entries.slice(start, first + 1)
        .map((entry) => entry.text).filter(Boolean).join('. ');
      this.nextIndex = first + 1;
      this.lastChallenge = first;
    }
    if (first !== null) this.scrollTo(first);
    this.say(text);
  }

  /** Deixa o item pendente sem marcar e segue para o proximo desafio. */
  skip() {
    if (!this.entries.length) return;
    const skipped = this.firstUnchecked(this.searchStart);
    if (skipped === null) return;

    // avanca o inicio da busca para que o item pulado nunca volte
    this.searchStart = skipped + 1;
    const next = this.firstUnchecked(skipped + 1);
    if (next === null) return;

    const text = this.entries.slice(skipped + 1, next + 1)
      .map((entry) => entry.text).filter(Boolean).join('. ');
    this.nextIndex = next + 1;
    this.lastChallenge = next;
    this.scrollTo(next);
    this.say(text);
  }

  repeat() { Voice.speak(this.lastText, this.rate); }

  setRate(rate) {
    this.rate = rate;
    const settings = loadSettings();
    settings.speed = rate;
    saveSettings(settings);
  }

  stop() {
    this.listening = false;
    Voice.stopListening();
    Voice.stopSpeaking();
  }
}

// ══════════════════════════════════════════════════════════════════
//  ITENS
// ══════════════════════════════════════════════════════════════════
function addItemRow(reader, item, host) {
  const type = item.type || '';
  const prompt = String(item.prompt || '');
  const indent = item.indent === 1 ? ' indent' : '';

  if (type === 'ITEM_SPACE') {
    host.appendChild(el('div', { class: 'spacer' }));
    return;
  }

  if (type === 'ITEM_CHALLENGE_RESPONSE') {
    const expectation = String(item.expectation || '');
    const box = el('input', { type: 'checkbox' });
    const promptNode = el('span', { class: 'prompt', text: prompt });
    const answerNode = el('span', { class: 'answer', text: expectation });
    const row = el('label', { class: 'item' + indent }, [
      box, promptNode, el('span', { class: 'leader', 'aria-hidden': 'true' }),
      answerNode,
    ]);
    // item conferido esmaece, como as linhas ja resolvidas do planejador
    box.addEventListener('change', () => {
      row.classList.toggle('done', box.checked);
      reader.saveProgress();
    });
    host.appendChild(row);
    reader.add(`${prompt}. ${expectation}`, { box: box, row: row });
    return;
  }

  // ── itens de texto: nota, atencao e advertencia ─────────────────
  const text = prompt || type;
  let tone = '';
  if (type === 'ITEM_PLAINTEXT') tone = ' plain';
  else if (type === 'ITEM_NOTE') tone = ' note';
  else if (type === 'ITEM_CAUTION') tone = ' caution';
  else if (type === 'ITEM_WARNING' || type === 'ITEM_WARNIN') tone = ' warning';
  const centered = item.centered ? ' centered' : '';

  const node = el('p', { class: 'text-item' + tone + indent + centered, text: text });
  host.appendChild(node);
  reader.add(text, { row: node });
}

// ══════════════════════════════════════════════════════════════════
//  TELAS
// ══════════════════════════════════════════════════════════════════
function metadataText(data) {
  return Object.entries(data.metadata || {})
    .filter(([key]) => !METADATA_SKIP.includes(key))
    .map(([, value]) => String(value))
    .join('\n');
}

function screenMenu(data) {
  return {
    title: '',
    header: (host) => {
      host.appendChild(el('img', {
        class: 'logo', src: 'assets/sling_tsi.png', alt: 'Sling TSi',
      }));
    },
    body: (host) => {
      const status = el('p', { class: 'status' });

      const openUrl = (url, name) => {
        if (!navigator.onLine) {
          status.textContent = `${name} precisa de internet — o aparelho está sem rede.`;
          status.classList.add('bad');
          return;
        }
        const opened = window.open(url, '_blank', 'noopener');
        if (!opened) {
          status.textContent = `Permita pop-ups para abrir o ${name}.`;
          status.classList.add('bad');
        }
      };

      host.appendChild(section('Escolha um aplicativo', [
        rowButton('Checklist', 'procedimentos normais e de emergência',
          () => go(screenGroups(data))),
        rowButton('Peso & Balanceamento', 'envelope de CG',
          () => go(screenWB())),
        rowButton('RedeMet', 'meteorologia aeronáutica · DECEA',
          () => openUrl(URL_REDEMET, 'RedeMet')),
        rowButton('AISweb', 'cartas e publicações · DECEA',
          () => openUrl(URL_AISWEB, 'AISweb')),
      ]));
      host.appendChild(status);

      if (data.metadata) {
        host.appendChild(el('div', {}, [
          el('button', {
            class: 'btn', type: 'button', text: 'Sobre o aplicativo',
            onclick: () => go(screenAbout(data)),
          }),
        ]));
      }
    },
  };
}

function screenAbout(data) {
  return {
    title: 'Sobre',
    header: titleHeader('Sobre'),
    body: (host) => {
      host.appendChild(section('Aviso',
        [el('p', { class: 'meta', text: DISCLAIMER })], 'note'));
      host.appendChild(section('Metadados do arquivo',
        [el('p', { class: 'meta', text: metadataText(data) })]));
    },
  };
}

function screenGroups(data) {
  return {
    title: 'Checklists',
    header: titleHeader('Checklists'),
    body: (host) => {
      const groups = data.groups || [];
      if (!groups.length) {
        host.appendChild(section('Grupos',
          [el('p', { class: 'hint', text: 'Nenhum grupo encontrado.' })]));
        return;
      }
      const rows = groups.map((group) => {
        const count = (group.groups || []).length;
        const tag = !count ? '' : count === 1 ? '1 seção' : `${count} seções`;
        return rowButton(group.title || '', tag, () => go(screenSections(data, group)));
      });
      host.appendChild(section('Grupos', rows));
    },
  };
}

function screenSections(data, group) {
  return {
    title: group.title || 'Seções',
    header: titleHeader(group.title || 'Seções'),
    body: (host) => {
      const subgroups = group.groups || [];
      if (!subgroups.length) {
        host.appendChild(section('Seções',
          [el('p', { class: 'hint', text: 'Nenhuma seção encontrada.' })]));
        return;
      }
      const rows = subgroups.map((subgroup) => {
        const count = (subgroup.checklists || []).length;
        const tag = !count ? ''
          : count === 1 ? '1 checklist' : `${count} checklists`;
        return rowButton(subgroup.title || '', tag,
          () => go(screenItems(data, group, subgroup)));
      });
      host.appendChild(section('Seções', rows));
    },
  };
}

function screenItems(data, group, subgroup) {
  return {
    title: subgroup.title || 'Itens',
    header: titleHeader(subgroup.title || 'Itens'),
    body: (host) => {
      reader = new Reader(`${group.title || ''} / ${subgroup.title || ''}`);

      // ── controles de leitura ────────────────────────────────────
      const listenButton = el('button', {
        class: 'btn', type: 'button', text: 'Ouvir',
      });

      const setListening = (active) => {
        listenButton.textContent = active ? '●  Ouvindo' : 'Ouvir';
        listenButton.classList.toggle('listening', active);
      };

      listenButton.addEventListener('click', () => {
        if (!Voice.canListen) {
          window.alert(Voice.listenBlockedReason);
          return;
        }
        Voice.stopSpeaking();
        if (reader.listening) {
          reader.listening = false;
          Voice.stopListening();
          setListening(false);
          return;
        }
        reader.listening = true;
        setListening(true);
        Voice.startListening({
          onCommand: (command) => {
            if (command === 'check') reader.check();
            else if (command === 'pular') reader.skip();
            else reader.repeat();
          },
          onError: (error) => {
            reader.listening = false;
            setListening(false);
            window.alert(`Não foi possível ouvir: ${error}`);
          },
        });
      });

      const speed = el('input', {
        type: 'range', min: '-10', max: '10', step: '1',
        value: String(reader.rate), 'aria-label': 'Velocidade da voz',
      });
      speed.addEventListener('input', () => reader.setRate(Number(speed.value)));

      controlsBar.hidden = false;
      controlsBar.appendChild(el('button', {
        class: 'btn-primary', type: 'button', text: 'Check',
        onclick: () => reader.check(),
      }));
      controlsBar.appendChild(el('button', {
        class: 'btn', type: 'button', text: 'Repetir',
        onclick: () => reader.repeat(),
      }));
      controlsBar.appendChild(el('button', {
        class: 'btn', type: 'button', text: 'Pular',
        onclick: () => reader.skip(),
      }));
      controlsBar.appendChild(listenButton);
      controlsBar.appendChild(el('div', { class: 'speed' }, [
        el('label', { text: 'Velocidade da voz' }), speed,
      ]));

      // ── conteudo ────────────────────────────────────────────────
      const checklists = subgroup.checklists || [];
      if (!checklists.length) {
        host.appendChild(section(subgroup.title || 'Itens',
          [el('p', { class: 'hint', text: 'Nenhum item encontrado.' })]));
        return;
      }

      for (const checklist of checklists) {
        const title = String(checklist.title || '');
        const box = section(title || null, []);
        if (title) reader.add(title, {});
        for (const item of checklist.items || []) addItemRow(reader, item, box);
        host.appendChild(box);
      }

      const dica = Voice.canListen ? HINT_VOICE
        : (window.isSecureContext ? HINT_NO_LISTEN : HINT_INSECURE);
      host.appendChild(el('p', { class: 'hint', text: dica }));

      // progresso de um voo em andamento: retomado sempre com aviso visivel,
      // nunca em silencio — o piloto precisa saber que aquilo nao e desta
      // passada pelo checklist
      const quando = reader.restoreProgress();
      if (quando) {
        const hora = quando.toLocaleTimeString('pt-BR',
          { hour: '2-digit', minute: '2-digit' });
        const aviso = el('div', { class: 'resumed' }, [
          el('span', { text: `Itens marcados às ${hora} foram retomados.` }),
          el('button', {
            class: 'btn', type: 'button', text: 'Recomeçar',
            onclick: () => { reader.clearProgress(); aviso.remove(); },
          }),
        ]);
        host.insertBefore(aviso, host.firstChild);
      }
    },
  };
}

// ══════════════════════════════════════════════════════════════════
//  ENTRADA
// ══════════════════════════════════════════════════════════════════
async function main() {
  let data;
  try {
    const response = await fetch(CHECKLIST_URL, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
  } catch (err) {
    content.appendChild(section('Checklists', [
      el('p', { class: 'hint', text: `Não foi possível ler ${CHECKLIST_URL}: ${err.message}` }),
    ]));
    return;
  }

  await seedProfiles();          // perfis de fabrica na primeira visita
  stack.push(screenMenu(data));
  history.replaceState({ depth: 1 }, '');
  render();
  watchConnection();

  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* segue online */ });
  }
}

function watchConnection() {
  const pill = el('div', { class: 'offline-pill', text: 'sem rede' });
  document.body.appendChild(pill);
  const update = () => document.body.classList.toggle('offline', !navigator.onLine);
  window.addEventListener('online', update);
  window.addEventListener('offline', update);
  update();
}

document.addEventListener('visibilitychange', () => {
  // sair do app com a leitura em curso deixaria a voz presa
  if (document.hidden) { Voice.stopSpeaking(); Voice.stopListening(); }
});

main();
