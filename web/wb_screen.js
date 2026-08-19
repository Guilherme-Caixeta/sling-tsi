/* ══════════════════════════════════════════════════════════════════
   Sling TSi — Peso & Balanceamento: a tela

   Mesma estrutura da versao Tkinter: Aeronave & Performance, o bloco de
   combustivel com o cursor vermelho, a tabela de composicao de massa, os
   tres cartoes de resultado, o envelope de CG e a barra de perfis.
   O calculo e a folha A4 ficam em wb.js.
   ══════════════════════════════════════════════════════════════════ */
'use strict';

// ══════════════════════════════════════════════════════════════════
//  CAIXAS DE DIALOGO  — no tema da pagina
// ══════════════════════════════════════════════════════════════════
function modal(title, bodyNodes, buttons) {
  const dialog = el('dialog', { class: 'modal' });
  const foot = el('div', { class: 'modal-foot' });
  const box = el('form', { method: 'dialog', class: 'modal-box' }, [
    el('div', { class: 'sec-head' }, [el('span', { text: title })]),
    ...bodyNodes, foot,
  ]);
  for (const [label, value, primary] of buttons) {
    foot.appendChild(el('button', {
      class: primary ? 'btn-primary' : 'btn', type: 'submit', value: value,
      text: label,
    }));
  }
  dialog.appendChild(box);
  document.body.appendChild(dialog);
  return dialog;
}

function askText(title, prompt, initial) {
  return new Promise((resolve) => {
    const input = el('input', { class: 'field', type: 'text', value: initial || '' });
    const dialog = modal(title, [
      el('span', { class: 'field-label', text: prompt }), input,
    ], [['Cancelar', 'cancel', false], ['Salvar', 'ok', true]]);
    dialog.addEventListener('close', () => {
      const value = dialog.returnValue === 'ok' ? input.value.trim() : '';
      dialog.remove();
      resolve(value || null);
    });
    dialog.showModal();
    input.focus();
  });
}

function askConfirm(title, message) {
  return new Promise((resolve) => {
    const dialog = modal(title, [el('p', { class: 'modal-text', text: message })],
      [['Nao', 'cancel', false], ['Sim', 'ok', true]]);
    dialog.addEventListener('close', () => {
      const ok = dialog.returnValue === 'ok';
      dialog.remove();
      resolve(ok);
    });
    dialog.showModal();
  });
}

/** Abre a folha A4 em outra aba: no navegador nao ha arquivo em disco. */
function openPrintSheet(html) {
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return Boolean(win);
}

// ══════════════════════════════════════════════════════════════════
//  TELA
// ══════════════════════════════════════════════════════════════════
function screenWB() {
  const fields = {};
  const moments = {};
  const out = {};

  const defaults = {
    consumo: String(DEFAULT_CONS_LH), duracao: String(DEFAULT_DUR_H),
    empty_kg: String(DEFAULT_EMPTY_KG), empty_cg: String(DEFAULT_EMPTY_CG_MM),
    pilot: '', copilot: '', pax3: '', pax4: '', baggage: '', fuel: '',
    pilot_arm: String(ARM_FRONT_SEATS), copilot_arm: String(ARM_FRONT_SEATS),
  };

  let active = null;              // perfil carregado
  let syncing = false;            // evita o laco cursor <-> campo
  let statusTimer = 0;

  const picker = el('select', { class: 'picker', 'aria-label': 'Perfis salvos' });
  const status = el('p', { class: 'status' });
  const chart = svgEl('svg', {
    viewBox: `0 0 ${CW} ${CH}`, class: 'envelope',
    preserveAspectRatio: 'xMidYMid meet',
  });

  function field(key, extra) {
    const input = el('input', Object.assign({
      class: 'field', type: 'text', inputmode: 'decimal',
      value: defaults[key], 'data-key': key,
    }, extra || {}));
    input.addEventListener('input', render);
    fields[key] = input;
    return input;
  }

  function values() {
    const get = (key, fallback) => num(fields[key].value, fallback);
    return {
      consumo: get('consumo', DEFAULT_CONS_LH), duracao: get('duracao', 0),
      empty_kg: get('empty_kg', DEFAULT_EMPTY_KG),
      empty_cg: get('empty_cg', DEFAULT_EMPTY_CG_MM),
      pilot: get('pilot', 0), copilot: get('copilot', 0),
      pax3: get('pax3', 0), pax4: get('pax4', 0),
      baggage: get('baggage', 0), fuel: get('fuel', 0),
      pilot_arm: get('pilot_arm', ARM_FRONT_SEATS),
      copilot_arm: get('copilot_arm', ARM_FRONT_SEATS),
    };
  }

  function flash(message, ok) {
    status.textContent = message;
    status.classList.toggle('bad', ok === false);
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => { status.textContent = ''; }, 3500);
  }

  // ── perfis ──────────────────────────────────────────────────────
  function fillPicker() {
    const profiles = loadProfiles() || {};
    const names = Object.keys(profiles).sort((a, b) =>
      a.toLowerCase().localeCompare(b.toLowerCase()));
    picker.textContent = '';
    picker.appendChild(el('option', {
      value: '', text: names.length ? 'Ler Perfis' : '(nenhum perfil salvo)',
    }));
    for (const name of names) {
      picker.appendChild(el('option', { value: name, text: name }));
    }
    picker.value = active && names.includes(active) ? active : '';
  }

  function applyProfile(name) {
    const data = (loadProfiles() || {})[name];
    if (!data) return;
    for (const key of PROFILE_FIELDS) fields[key].value = String(data[key] || '');
    active = name;
    fillPicker();
    render();
  }

  picker.addEventListener('change', () => {
    if (picker.value) applyProfile(picker.value);
  });

  async function saveProfile() {
    const name = await askText('Salvar Perfil', 'Nome do perfil:', '');
    if (!name) return;
    const profiles = loadProfiles() || {};
    if (name in profiles) {
      const ok = await askConfirm('Salvar Perfil',
        `Ja existe um perfil chamado "${name}". Substituir?`);
      if (!ok) return;
    }
    const entry = {};
    for (const key of PROFILE_FIELDS) entry[key] = fields[key].value.trim();
    profiles[name] = entry;
    if (!saveProfiles(profiles)) { flash('Nao foi possivel gravar.', false); return; }
    active = name;
    fillPicker();
    flash(`✓ Perfil "${name}" salvo`);
  }

  function manageProfiles() {
    const list = el('div', { class: 'profile-list' });
    const note = el('p', { class: 'status' });
    const dialog = modal('Perfis salvos', [list, note], [['Fechar', 'close', false]]);

    const refresh = () => {
      const profiles = loadProfiles() || {};
      const names = Object.keys(profiles).sort((a, b) =>
        a.toLowerCase().localeCompare(b.toLowerCase()));
      list.textContent = '';
      if (!names.length) {
        list.appendChild(el('p', { class: 'hint', text: 'Nenhum perfil salvo ainda.' }));
        return;
      }
      for (const name of names) {
        const input = el('input', { class: 'field', type: 'text', value: name });
        const rename = el('button', {
          class: 'btn-primary', type: 'button', text: 'Salvar',
        });
        const remove = el('button', { class: 'btn danger', type: 'button', text: 'Excluir' });

        rename.addEventListener('click', async () => {
          const novo = input.value.trim();
          if (!novo) { note.textContent = 'O nome nao pode ficar vazio.'; return; }
          if (novo === name) { note.textContent = 'Nome inalterado.'; return; }
          const current = loadProfiles() || {};
          if (novo in current) {
            const ok = await askConfirm('Gerenciar Perfis',
              `Ja existe um perfil chamado "${novo}". Substituir?`);
            if (!ok) return;
          }
          const renamed = {};
          for (const [key, value] of Object.entries(current)) {
            if (key === name) renamed[novo] = value;
            else if (key !== novo) renamed[key] = value;
          }
          saveProfiles(renamed);
          if (active === name) active = novo;
          fillPicker();
          refresh();
          note.textContent = `"${name}" renomeado para "${novo}".`;
        });

        remove.addEventListener('click', async () => {
          const ok = await askConfirm('Gerenciar Perfis',
            `Excluir o perfil "${name}"? Esta acao nao pode ser desfeita.`);
          if (!ok) return;
          const current = loadProfiles() || {};
          delete current[name];
          saveProfiles(current);
          if (active === name) active = null;
          fillPicker();
          refresh();
          note.textContent = `"${name}" excluido.`;
        });

        list.appendChild(el('div', { class: 'profile-row' }, [input, rename, remove]));
      }
    };

    refresh();
    dialog.addEventListener('close', () => dialog.remove());
    dialog.showModal();
  }

  function printSheet() {
    const v = values();
    const res = calcWB(v);
    const land = calcLanding(res, v.consumo, v.duracao);
    if (openPrintSheet(buildPrintHtml(v, res, land, active))) {
      flash('✓ Folha A4 aberta em outra aba');
    } else {
      flash('Permita pop-ups para abrir a folha A4.', false);
    }
  }

  function setBadge(badge, info, r) {
    badge.classList.remove('ok', 'ng');
    if (r.total <= 0) {
      badge.textContent = '—';
      info.textContent = '';
      return;
    }
    if (r.overweight) {
      badge.textContent = '⚠ EXCESSO DE PESO';
      badge.classList.add('ng');
    } else if (r.cgOob) {
      badge.textContent = '⚠ CG FORA DOS LIMITES';
      badge.classList.add('ng');
    } else {
      badge.textContent = '✓ Dentro do envelope';
      badge.classList.add('ok');
    }
    info.textContent = `${r.total.toFixed(1)} kg · ${r.cgMm.toFixed(0)} mm · ` +
      `${r.pMac.toFixed(1)} %MAC`;
  }

  // ── render ──────────────────────────────────────────────────────
  function render() {
    const v = values();
    const res = calcWB(v);
    const land = calcLanding(res, v.consumo, v.duracao);
    const burnL = v.consumo * v.duracao;

    out.emptyKg.textContent = v.empty_kg.toFixed(1);
    out.emptyArm.textContent = v.empty_cg.toFixed(0);

    const rows = [
      ['vazio', v.empty_kg, v.empty_cg],
      ['pilot', v.pilot, v.pilot_arm],
      ['copil', v.copilot, v.copilot_arm],
      ['pax3', v.pax3, ARM_REAR_SEATS],
      ['pax4', v.pax4, ARM_REAR_SEATS],
      ['bag', v.baggage, ARM_BAGGAGE],
      ['fuel', v.fuel * FUEL_DENSITY, ARM_FUEL],
    ];
    for (const [key, kg, arm] of rows) {
      moments[key].textContent = kg === 0 ? '—' : (kg * arm / 1000).toFixed(3);
    }

    out.totalKg.textContent = `${res.total.toFixed(1)} kg`;
    out.totalArm.textContent = res.total > 0 ? res.cgMm.toFixed(0) : '—';
    out.totalMom.textContent = res.total > 0
      ? (res.cgMm * res.total / 1000).toFixed(1) : '—';
    out.weight.textContent = `${res.total.toFixed(1)} kg`;

    out.burnTag.textContent = burnL === 0 ? ''
      : `− ${burnL.toFixed(0)} L queimados (${(burnL * FUEL_DENSITY).toFixed(1)} kg)`;
    const dry = land.fuelKg < 0;
    out.landKg.textContent = land.fuelKg.toFixed(1);
    out.landKg.classList.toggle('bad', dry);
    out.landMom.textContent = land.fuelKg === 0 ? '—'
      : (land.fuelKg * ARM_FUEL / 1000).toFixed(3);
    out.landMom.classList.toggle('bad', dry);
    out.ltotKg.textContent = `${land.total.toFixed(1)} kg`;
    out.ltotArm.textContent = land.total > 0 ? land.cgMm.toFixed(0) : '—';
    out.ltotArm.classList.toggle('bad', land.cgOob);
    out.ltotMom.textContent = land.total > 0
      ? (land.cgMm * land.total / 1000).toFixed(1) : '—';

    setBadge(out.badgeDep, out.badgeDepInfo, res);
    setBadge(out.badgeLand, out.badgeLandInfo, land);

    if (!syncing) {
      syncing = true;
      out.slider.value = String(Math.min(MAX_FUEL_L, Math.max(0, v.fuel)));
      syncing = false;
    }
    out.fuelL.textContent = `${v.fuel.toFixed(0)} L`;
    out.fuelKg.textContent = `· ${(v.fuel * FUEL_DENSITY).toFixed(1)} kg`;

    drawEnvelope(chart, res, burnL > 0 ? land : null);
  }

  // ── montagem ────────────────────────────────────────────────────
  return {
    title: 'Peso & Balanceamento',

    header: (host) => {
      host.appendChild(el('h1', { text: 'Peso & Balanceamento' }));
      host.appendChild(el('span', { class: 'dash', text: '—', 'aria-hidden': 'true' }));
      host.appendChild(el('div', { class: 'bar-right' }, [picker]));
      fillPicker();
    },

    body: (host) => {
      // Aeronave & Performance
      const grid = el('div', { class: 'field-grid' });
      const labels = [
        ['consumo', 'Consumo Combustível (L/h)'],
        ['duracao', 'Duração Vôo (h)'],
        ['empty_kg', 'Peso Vazio (kg)'],
        ['empty_cg', 'CG Vazio (mm)'],
      ];
      for (const [key, label] of labels) {
        grid.appendChild(el('label', { class: 'field-cell' }, [
          el('span', { class: 'field-label', text: label }), field(key),
        ]));
      }
      host.appendChild(section('Aeronave & Performance', [grid]));

      // Combustivel na decolagem
      out.fuelL = el('span', { class: 'fuel-l', text: '0 L' });
      out.fuelKg = el('span', { class: 'fuel-kg', text: '· 0.0 kg' });
      out.slider = el('input', {
        type: 'range', min: '0', max: String(MAX_FUEL_L), step: '1', value: '0',
        class: 'fuel-slider', 'aria-label': 'Combustível na decolagem',
      });
      out.slider.addEventListener('input', () => {
        if (syncing) return;
        syncing = true;
        const litres = Number(out.slider.value);
        fields.fuel.value = litres === 0 ? '' : String(litres);
        syncing = false;
        render();
      });
      host.appendChild(section(null, [
        el('div', { class: 'fuel-head' }, [
          el('span', { class: 'fuel-title', text: 'Combustível na Decolagem' }),
          out.fuelL, out.fuelKg,
        ]),
        out.slider,
        el('div', { class: 'fuel-scale' }, [
          el('span', { text: '0 L' }),
          el('span', { text: `${MAX_FUEL_L} L · máx.` }),
        ]),
      ], 'fuel'));

      // Composicao de massa
      const table = el('div', { class: 'wb-table' });
      table.appendChild(el('div', { class: 'wb-row head' }, [
        el('span', { text: 'Item' }), el('span', { text: 'Peso (kg)' }),
        el('span', { text: 'Braço (mm)' }), el('span', { text: 'Momento (kg·m)' }),
      ]));

      const itemCell = (name, tag) => el('span', { class: 'wb-item' }, [
        el('b', { text: name }), tag ? el('i', { text: tag }) : null,
      ]);
      const momentCell = (key) => {
        const node = el('span', { class: 'wb-num', text: '—' });
        moments[key] = node;
        return node;
      };

      out.emptyKg = el('span', { class: 'wb-num muted', text: '—' });
      out.emptyArm = el('span', { class: 'wb-num muted', text: '—' });
      table.appendChild(el('div', { class: 'wb-row' }, [
        itemCell('Peso Vazio', '← perfil'), out.emptyKg, out.emptyArm,
        momentCell('vazio'),
      ]));

      const massRows = [
        ['pilot', 'Piloto', 'assento dianteiro', 'pilot', 'pilot_arm'],
        ['copil', 'Copiloto', 'assento dianteiro', 'copilot', 'copilot_arm'],
        ['pax3', 'Passageiro 3', 'assento traseiro', 'pax3', ARM_REAR_SEATS],
        ['pax4', 'Passageiro 4', 'assento traseiro', 'pax4', ARM_REAR_SEATS],
        ['bag', 'Bagagem', `máx. ${MAX_BAG_KG} kg`, 'baggage', ARM_BAGGAGE],
        ['fuel', 'Combustível na Decolagem',
          `máx. ${MAX_FUEL_L} L · ×${FUEL_DENSITY} kg/L`, 'fuel', ARM_FUEL],
      ];
      for (const [key, name, tag, weightKey, arm] of massRows) {
        const armCell = typeof arm === 'string'
          ? field(arm, { class: 'field right' })
          : el('span', { class: 'wb-num', text: String(arm) });
        table.appendChild(el('div', { class: 'wb-row' }, [
          itemCell(name, tag), field(weightKey, { class: 'field right' }),
          armCell, momentCell(key),
        ]));
      }

      out.totalKg = el('span', { class: 'wb-num strong', text: '— kg' });
      out.totalArm = el('span', { class: 'wb-num strong', text: '—' });
      out.totalMom = el('span', { class: 'wb-num strong', text: '—' });
      table.appendChild(el('div', { class: 'wb-row total' }, [
        el('span', { class: 'wb-item' }, [el('b', { text: 'TOTAL NA DECOLAGEM' })]),
        out.totalKg, out.totalArm, out.totalMom,
      ]));

      out.burnTag = el('i', { text: '' });
      out.landKg = el('span', { class: 'wb-num', text: '—' });
      out.landMom = el('span', { class: 'wb-num', text: '—' });
      table.appendChild(el('div', { class: 'wb-row' }, [
        el('span', { class: 'wb-item' }, [
          el('b', { text: 'Combustível no Pouso' }), out.burnTag,
        ]),
        out.landKg, el('span', { class: 'wb-num', text: String(ARM_FUEL) }),
        out.landMom,
      ]));

      out.ltotKg = el('span', { class: 'wb-num strong', text: '— kg' });
      out.ltotArm = el('span', { class: 'wb-num strong', text: '—' });
      out.ltotMom = el('span', { class: 'wb-num strong', text: '—' });
      table.appendChild(el('div', { class: 'wb-row total' }, [
        el('span', { class: 'wb-item' }, [el('b', { text: 'TOTAL NO POUSO' })]),
        out.ltotKg, out.ltotArm, out.ltotMom,
      ]));

      // cartoes de resultado
      out.weight = el('div', { class: 'card-value', text: '—' });
      out.badgeDep = el('div', { class: 'badge', text: '—' });
      out.badgeDepInfo = el('div', { class: 'card-info' });
      out.badgeLand = el('div', { class: 'badge', text: '—' });
      out.badgeLandInfo = el('div', { class: 'card-info' });

      const cards = el('div', { class: 'cards' }, [
        el('div', { class: 'card' }, [
          el('div', { class: 'card-cap', text: 'Peso na Decolagem' }), out.weight,
        ]),
        el('div', { class: 'card' }, [
          el('div', { class: 'card-cap', text: 'Na Decolagem' }),
          out.badgeDep, out.badgeDepInfo,
        ]),
        el('div', { class: 'card' }, [
          el('div', { class: 'card-cap', text: 'No Pouso' }),
          out.badgeLand, out.badgeLandInfo,
        ]),
      ]);

      host.appendChild(section('Composição de Massa', [table, cards]));

      // envelope de CG
      host.appendChild(section('Envelope de CG — Peso vs CG%MAC', [
        el('div', { class: 'envelope-box' }, [chart]),
        el('p', {
          class: 'hint',
          text: 'Região vermelha = envelope de operação. O ponto vermelho ' +
            'indica CG fora do limite. Envelope TSi aproximado — consulte o ' +
            'POH para limites exatos.',
        }),
      ]));

      // acoes
      host.appendChild(el('div', { class: 'actions' }, [
        el('button', {
          class: 'btn-primary', type: 'button', text: 'Salvar Perfil',
          onclick: saveProfile,
        }),
        el('button', {
          class: 'btn', type: 'button', text: 'Gerenciar Perfis',
          onclick: manageProfiles,
        }),
        el('button', {
          class: 'btn', type: 'button', text: 'Imprimir (A4 P&B)',
          onclick: printSheet,
        }),
      ]));
      host.appendChild(status);

      render();
    },
  };
}
