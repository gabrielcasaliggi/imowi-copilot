/**
 * imowi Operations Hub — demo presentación
 */
(function () {
  const API = (window.IMOWI_API_URL || window.location.origin).replace(/\/$/, '');
  const TOKEN_KEY = 'imowi_token';

  const state = {
    token: localStorage.getItem(TOKEN_KEY) || '',
    usuario: null,
    orgs: [],
    tenantSlug: 'coop-batan',
    brandColor: '#22d3ee',
    orgName: '',
    logoLabel: 'i',
    rol: '',
    historial: [],
    ticketFormacion: null,
    ticketTimeline: [],
    notifications: [],
    fichaJsc: null,
    tickets: [],
    stats: null,
    telemetry: [],
    kb: [],
    traces: [],
    sending: false,
    sessionId: localStorage.getItem('imowi_session') || '',
    estadoConversacion: null,
  };

  const $ = (id) => document.getElementById(id);

  function isAdmin() {
    return state.usuario?.rol === 'admin';
  }

  function authHeaders() {
    const h = { 'Content-Type': 'application/json' };
    if (state.token) h.Authorization = `Bearer ${state.token}`;
    if (isAdmin() && state.tenantSlug) {
      h['X-Tenant-Slug'] = state.tenantSlug;
    }
    return h;
  }

  async function api(path, opts = {}) {
    const res = await fetch(`${API}${path}`, {
      ...opts,
      headers: { ...authHeaders(), ...(opts.headers || {}) },
    });
    if (res.status === 401) {
      logout();
      throw new Error('Sesión expirada');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function estadoBadge(estado) {
    const colors = {
      Normal: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      Activa: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      Suspendida: 'bg-red-500/20 text-red-300 border-red-500/40',
      'Al día': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      Deuda: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      'Anomalía Predictiva': 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      Abierto: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
      'En Revisión': 'bg-violet-500/20 text-violet-300 border-violet-500/40',
      Cerrado: 'bg-slate-500/20 text-slate-400 border-slate-500/40',
      N1: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      N2: 'bg-violet-500/20 text-violet-300 border-violet-500/40',
      Proveedor: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      'Autónomo Predictivo': 'bg-violet-500/20 text-violet-300 border-violet-500/40',
      'Reporte Cliente': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    };
    const cls = colors[estado] || 'bg-slate-600/30 text-slate-300 border-slate-500/30';
    return `<span class="px-2 py-0.5 text-[10px] font-mono uppercase rounded border ${cls}">${escapeHtml(estado)}</span>`;
  }

  function applyBrand(ctx) {
    state.brandColor = ctx.brand_color || '#22d3ee';
    state.orgName = ctx.organizacion_nombre || '';
    state.logoLabel = ctx.logo_label || 'i';
    document.documentElement.style.setProperty('--brand', state.brandColor);
    $('logoMark').textContent = state.logoLabel;
    $('logoMark').style.background = `linear-gradient(135deg, ${state.brandColor}, #3b82f6)`;
    $('orgTitle').textContent = state.orgName;
    const rolLabel = isAdmin() ? 'NOC imowi' : state.usuario?.nombre || '';
    $('userBadge').textContent = `${rolLabel} · ${ctx.rol || state.rol}`;
  }

  function showApp(show) {
    $('loginScreen').classList.toggle('hidden', show);
    $('appShell').classList.toggle('hidden', !show);
  }

  async function login(user, pass) {
    const res = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario: user, password: pass }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Credenciales incorrectas');
    }
    const data = await res.json();
    state.token = data.token;
    state.usuario = data;
    localStorage.setItem(TOKEN_KEY, state.token);
    state.tenantSlug = data.rol === 'admin' ? 'imowi' : (data.org_slug || (data.cooperativa?.includes('Viamonte') ? 'coop-viamonte' : 'coop-batan'));
    try {
      await boot();
      showApp(true);
    } catch (err) {
      logout();
      throw err;
    }
  }

  async function restoreSession() {
    if (!state.token || state.usuario) return;
    const me = await api('/api/me');
    state.usuario = me;
    state.tenantSlug = me.rol === 'admin' ? 'imowi' : (me.org_slug || state.tenantSlug);
  }

  function logout() {
    state.token = '';
    state.usuario = null;
    state.sessionId = '';
    state.estadoConversacion = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('imowi_session');
    showApp(false);
  }

  function renderFichaJsc(f) {
    const el = $('fichaJsc');
    if (!f) {
      el.innerHTML = '<p class="text-slate-500 text-xs">Sin línea resuelta en JSC.</p>';
      return;
    }
    el.innerHTML = `
      <div class="space-y-1.5 text-xs">
        <div class="flex justify-between"><span class="text-slate-500">MSISDN</span><span class="text-cyan-300">${escapeHtml(f.msisdn)}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Abonado</span><span>${escapeHtml(f.abonado)}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Plan</span><span>${escapeHtml(f.plan)}</span></div>
        <div class="flex justify-between gap-2"><span class="text-slate-500">Línea</span>${estadoBadge(f.estado_linea)}</div>
        <div class="flex justify-between gap-2"><span class="text-slate-500">Cuenta</span>${estadoBadge(f.estado_cuenta)} <span class="text-slate-500">${escapeHtml(f.saldo_resumen)}</span></div>
        <div class="text-[10px] text-slate-600 pt-1">APN ${escapeHtml(f.apn)} · Roaming ${escapeHtml(f.roaming_habilitado)}</div>
        <div class="text-[10px] text-slate-600">${escapeHtml(f.fuente)}</div>
      </div>`;
  }

  const ESTADO_CASO_LABELS = {
    nuevo_reclamo: 'Nuevo reclamo',
    recolectando_datos: 'Recolectando datos',
    buscando_kb: 'Buscando en KB',
    guiando_resolucion: 'Guía N1',
    esperando_confirmacion: 'Esperando confirmación',
    ticket_creado: 'Ticket registrado',
    cerrado_resuelto: 'Cerrado resuelto',
  };

  function ensureSessionId() {
    if (!state.sessionId) {
      state.sessionId = (crypto.randomUUID && crypto.randomUUID()) || `s-${Date.now()}`;
      localStorage.setItem('imowi_session', state.sessionId);
    }
    return state.sessionId;
  }

  function renderEstadoCaso() {
    const el = $('estadoCasoBadge');
    if (!el) return;
    if (isAdmin() || !state.estadoConversacion) {
      el.classList.add('hidden');
      return;
    }
    const label = ESTADO_CASO_LABELS[state.estadoConversacion] || state.estadoConversacion;
    el.classList.remove('hidden');
    el.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono uppercase rounded border bg-cyan-500/10 text-cyan-300 border-cyan-500/30">${escapeHtml(label)}</span>`;
  }

  function renderChat() {
    $('chatMessages').innerHTML = state.historial.map((m) => {
      const u = m.rol === 'usuario';
      return `<div class="flex ${u ? 'justify-end' : 'justify-start'} mb-3">
        <div class="max-w-[85%] px-4 py-2.5 rounded-2xl text-sm ${u ? 'bg-cyan-500/15 border border-cyan-500/25' : 'bg-slate-800/80 border border-slate-700/60'}">${escapeHtml(m.contenido)}</div></div>`;
    }).join('');
    $('chatMessages').scrollTop = $('chatMessages').scrollHeight;
  }

  function renderTicketFormacion() {
    const t = state.ticketFormacion;
    const el = $('ticketFormacion');
    if (!t) {
      el.innerHTML = '<p class="text-slate-500 text-xs font-mono">Pendiente de escalamiento.</p>';
      renderTicketTimeline();
      return;
    }
    const adminControls = isAdmin() ? `
        <div class="pt-2 mt-2 border-t border-slate-800 space-y-2">
          <div class="grid grid-cols-2 gap-2">
            <select id="ticketNivel" class="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]">
              <option value="N1" ${t.nivel === 'N1' ? 'selected' : ''}>N1</option>
              <option value="N2" ${t.nivel === 'N2' ? 'selected' : ''}>N2</option>
            </select>
            <select id="ticketEstado" class="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]">
              ${['Abierto', 'En Revisión', 'Escalado', 'Pendiente Cliente', 'Cerrado'].map((e) => `<option value="${e}" ${t.estado === e ? 'selected' : ''}>${e}</option>`).join('')}
            </select>
          </div>
          <input id="ticketProveedor" value="${escapeHtml(t.proveedor || '')}" placeholder="Proveedor sugerido / referencia" class="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]">
          <textarea id="ticketResolucion" placeholder="Agregar avance visible para la cooperativa..." class="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px] min-h-[54px]"></textarea>
          <button type="button" id="btnTicketUpdate" class="w-full py-1.5 rounded border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10">Actualizar seguimiento</button>
        </div>` : `
        <div class="pt-2 mt-2 border-t border-slate-800">
          <p class="text-[10px] text-slate-500">Vista de seguimiento: el NOC actualizará el estado y las novedades del ticket.</p>
        </div>`;
    el.innerHTML = `
      <div class="space-y-1 text-xs font-mono">
        <div class="flex justify-between"><span class="text-slate-500">ID</span><span class="text-cyan-300">${t.id}</span></div>
        <div class="flex justify-between"><span class="text-slate-500">Línea</span><span>${escapeHtml(t.linea)}</span></div>
        <div class="flex flex-wrap gap-1">${t.nivel ? estadoBadge(t.nivel) : ''} ${t.destino ? `<span class="px-2 py-0.5 text-[10px] font-mono uppercase rounded border bg-slate-600/30 text-slate-300 border-slate-500/30">${escapeHtml(t.destino)}</span>` : ''} ${estadoBadge(t.origen)} ${estadoBadge(t.estado)}</div>
        ${t.proveedor ? `<p class="text-amber-300 text-[10px]">→ ${escapeHtml(t.proveedor)}</p>` : ''}
        ${t.motivo_escalamiento ? `<p class="text-slate-400 text-[10px]">${escapeHtml(t.motivo_escalamiento)}</p>` : ''}
        ${t.intent_ejecutado ? `<p class="text-violet-300 text-[10px]">${escapeHtml(t.intent_ejecutado)}</p>` : ''}
        ${adminControls}
      </div>`;
    $('btnTicketUpdate')?.addEventListener('click', updateSelectedTicket);
  }

  function renderTicketTimeline() {
    const el = $('ticketTimeline');
    if (!el) return;
    if (!state.ticketFormacion) {
      el.innerHTML = '<p class="text-slate-500 text-xs font-mono">Seleccioná un ticket para ver avances.</p>';
      return;
    }
    if (!state.ticketTimeline.length) {
      el.innerHTML = '<p class="text-slate-500 text-xs font-mono">Sin eventos todavía.</p>';
      return;
    }
    el.innerHTML = state.ticketTimeline.map((ev) => `
      <div class="pl-3 border-l border-cyan-500/30">
        <div class="flex justify-between gap-2">
          <p class="text-xs text-slate-200">${escapeHtml(ev.titulo)}</p>
          ${ev.nivel ? estadoBadge(ev.nivel) : ''}
        </div>
        <p class="text-[10px] text-slate-500 font-mono">${escapeHtml(ev.estado || '')}${ev.actor ? ` · ${escapeHtml(ev.actor)}` : ''}</p>
        ${ev.detalle ? `<p class="text-[11px] text-slate-400 mt-1">${escapeHtml(ev.detalle)}</p>` : ''}
      </div>`).join('');
  }

  function renderNotifications() {
    const el = $('ticketNotifications');
    if (!el) return;
    if (!state.notifications.length) {
      el.innerHTML = '<p class="text-slate-500 text-xs font-mono">Sin novedades.</p>';
      return;
    }
    el.innerHTML = state.notifications.slice(0, 5).map((n) => `
      <div class="p-2 rounded-lg border ${n.leida === 'No' ? 'border-amber-500/30 bg-amber-500/10' : 'border-slate-800 bg-slate-900/50'}">
        <div class="flex justify-between gap-2">
          <p class="text-xs text-slate-200">${escapeHtml(n.titulo)}</p>
          <span class="text-[9px] font-mono text-slate-500">${escapeHtml(n.leida)}</span>
        </div>
        <p class="text-[11px] text-slate-400 mt-1">${escapeHtml(n.mensaje)}</p>
      </div>`).join('');
  }

  async function selectTicket(ticketId) {
    const detail = await api(`/api/v1/tickets/${ticketId}`);
    state.ticketFormacion = detail.ticket;
    state.ticketTimeline = detail.timeline || [];
    renderTicketFormacion();
    renderTicketTimeline();
  }

  async function updateSelectedTicket() {
    const t = state.ticketFormacion;
    if (!t || !isAdmin()) return;
    const body = {
      nivel: $('ticketNivel')?.value || t.nivel,
      estado: $('ticketEstado')?.value || t.estado,
      proveedor: $('ticketProveedor')?.value || '',
      resolucion_tecnica: $('ticketResolucion')?.value || '',
      destino: ($('ticketNivel')?.value || t.nivel) === 'N2' ? (t.destino === 'cooperativa' ? 'imowi_noc' : t.destino) : 'cooperativa',
    };
    try {
      const res = await api(`/api/v1/tickets/${t.id}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      state.ticketFormacion = res.ticket;
      await selectTicket(t.id);
      await api('/api/v1/tickets').then((d) => { state.tickets = d.tickets || []; renderTickets(); });
      await api('/api/v1/tickets/notifications').then((d) => { state.notifications = d.notificaciones || []; renderNotifications(); });
      if (isAdmin()) await loadStats();
      appendTrace([`📬 Seguimiento actualizado para ${t.id}`]);
    } catch (e) {
      appendTrace([`❌ ${e.message}`]);
    }
  }

  function renderTickets() {
    const el = $('ticketsList');
    if (!state.tickets.length) {
      el.innerHTML = '<p class="text-slate-500 text-xs">Sin tickets.</p>';
      return;
    }
    el.innerHTML = state.tickets.slice(0, 10).map((t) => `
      <div class="p-2 rounded-lg bg-slate-900/60 border border-slate-800 cursor-pointer ticket-row" data-id="${t.id}">
        <div class="flex justify-between items-center gap-1">
          <span class="font-mono text-cyan-300 text-[10px]">${t.id}</span>
          <span class="flex gap-1">${t.nivel ? estadoBadge(t.nivel) : ''}${estadoBadge(t.estado)}</span>
        </div>
        <p class="text-[10px] text-slate-500 truncate">${escapeHtml(t.linea)}${t.destino ? ` · ${escapeHtml(t.destino)}` : ''}</p>
        ${t.organizacion ? `<p class="text-[9px] text-slate-600 truncate">${escapeHtml(t.organizacion)}</p>` : ''}
      </div>`).join('');
    el.querySelectorAll('.ticket-row').forEach((r) => {
      r.onclick = async () => {
        try {
          await selectTicket(r.dataset.id);
        } catch (e) {
          appendTrace([`❌ ${e.message}`]);
        }
      };
    });
  }

  function renderNocBoard() {
    if (!isAdmin()) return;
    const resumen = state.stats?.resumen || {};
    const tickets = state.tickets || [];
    const abiertos = tickets.filter((t) => t.estado !== 'Cerrado');
    const n2 = tickets.filter((t) => t.nivel === 'N2');
    const proveedores = tickets.filter((t) => t.proveedor);
    $('nocKpis').innerHTML = [
      ['Abiertos', resumen.abiertos ?? abiertos.length],
      ['N2', resumen.n2 ?? n2.length],
      ['Cerrados', resumen.cerrados ?? 0],
      ['Prom. hs', resumen.promedio_horas ?? 0],
    ].map(([label, value]) => `
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
        <p class="text-[10px] uppercase tracking-wider font-mono text-slate-500">${escapeHtml(label)}</p>
        <p class="text-2xl font-semibold text-slate-100 mt-1">${escapeHtml(value)}</p>
      </div>`).join('');

    const priority = [...abiertos].sort((a, b) => {
      const pa = (a.nivel === 'N2' ? 2 : 0) + (a.proveedor ? 1 : 0);
      const pb = (b.nivel === 'N2' ? 2 : 0) + (b.proveedor ? 1 : 0);
      return pb - pa;
    }).slice(0, 8);
    $('nocQueue').innerHTML = priority.length ? priority.map((t) => `
      <button type="button" class="w-full text-left p-3 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-cyan-500/40 noc-ticket-link" data-id="${escapeHtml(t.id)}">
        <div class="flex justify-between items-center gap-2">
          <span class="font-mono text-cyan-300 text-xs">${escapeHtml(t.id)}</span>
          <span class="flex gap-1">${estadoBadge(t.nivel)}${estadoBadge(t.estado)}</span>
        </div>
        <p class="text-[11px] text-slate-400 mt-1 truncate">${escapeHtml(t.organizacion || '')} · ${escapeHtml(t.linea || '')}</p>
        <p class="text-[10px] text-slate-500 mt-1 truncate">${escapeHtml(t.categoria || 'General')}${t.proveedor ? ` · ${escapeHtml(t.proveedor)}` : ''}</p>
      </button>`).join('') : '<p class="text-sm text-slate-500">Sin tickets abiertos.</p>';
    $('nocQueue')?.querySelectorAll('.noc-ticket-link').forEach((b) => {
      b.addEventListener('click', async () => {
        await selectTicket(b.dataset.id);
      });
    });

    const topCategorias = state.stats?.distribuciones?.categoria || [];
    const topEstados = state.stats?.distribuciones?.estado || [];
    $('nocSummary').innerHTML = `
      <div>
        <p class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">Categorías principales</p>
        ${miniList(topCategorias.slice(0, 5))}
      </div>
      <div>
        <p class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">Estados</p>
        ${miniList(topEstados.slice(0, 5))}
      </div>
      <div>
        <p class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">Proveedores sugeridos</p>
        ${miniList((state.stats?.distribuciones?.proveedor || []).slice(0, 5))}
      </div>
      <p class="text-[11px] text-slate-500">Los reclamos nuevos los generan las cooperativas desde su consola. El NOC administra, prioriza y actualiza seguimiento.</p>
    `;
  }

  function miniList(items) {
    if (!items.length) return '<p class="text-xs text-slate-600">Sin datos.</p>';
    return items.map((x) => `
      <div class="flex justify-between gap-2 text-xs py-1 border-b border-slate-800/60 last:border-b-0">
        <span class="text-slate-300 truncate">${escapeHtml(x.label)}</span>
        <span class="font-mono text-slate-500">${escapeHtml(x.count)}</span>
      </div>`).join('');
  }

  function renderTraces() {
    $('agentConsole').innerHTML = state.traces.map((t) => `<div class="text-slate-400 mb-0.5">${escapeHtml(t)}</div>`).join('');
    $('agentConsole').scrollTop = $('agentConsole').scrollHeight;
  }

  function appendTrace(lines) {
    state.traces.push(...(lines || []));
    if (state.traces.length > 150) state.traces = state.traces.slice(-150);
    renderTraces();
  }

  function renderTelemetry() {
    const el = $('telemetryGrid');
    el.innerHTML = state.telemetry.map((e) => `
      <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/70">
        <div class="flex justify-between mb-2"><span class="font-mono text-sm">${escapeHtml(e.elemento_red)}</span>${estadoBadge(e.estado_actual)}</div>
        <p class="text-xs font-mono text-slate-500">${escapeHtml(e.metrica)} = ${escapeHtml(e.valor_actual)}</p>
        <button type="button" class="sim-falla mt-3 w-full text-xs py-1.5 rounded border border-amber-500/30 text-amber-300" data-el="${escapeHtml(e.elemento_red)}">Simular falla</button>
      </div>`).join('');
    el.querySelectorAll('.sim-falla').forEach((b) => {
      b.onclick = () => simulateFailure(b.dataset.el);
    });
  }

  function renderKB() {
    $('kbList').innerHTML = state.kb.length
      ? state.kb.map((a) => `
        <article class="p-4 rounded-xl border border-slate-800 bg-slate-900/60">
          <div class="flex justify-between mb-1"><h4 class="text-sm font-medium">${escapeHtml(a.titulo)}</h4><span class="text-[10px] font-mono text-cyan-300">${escapeHtml(a.categoria)}</span></div>
          <p class="text-xs text-slate-400 line-clamp-3">${escapeHtml(a.contenido)}</p>
        </article>`).join('')
      : '<p class="text-slate-500 text-sm">Sin artículos.</p>';
  }

  function renderStats() {
    if (!state.stats) return;
    const s = state.stats;
    const r = s.resumen || {};
    $('statsKpis').innerHTML = [
      ['Reclamos', r.total || 0],
      ['Abiertos', r.abiertos || 0],
      ['Cerrados', r.cerrados || 0],
      ['N1', r.n1 || 0],
      ['N2', r.n2 || 0],
      ['Prom. hs', r.promedio_horas || 0],
    ].map(([label, value]) => `
      <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <p class="text-[10px] uppercase tracking-wider font-mono text-slate-500">${escapeHtml(label)}</p>
        <p class="text-2xl font-semibold text-slate-100 mt-1">${escapeHtml(value)}</p>
      </div>`).join('');

    renderColumnChart('chartDaily', (s.series?.diaria || []).slice(-30), { compactLabels: true });
    renderColumnChart('chartMonthly', s.series?.mensual || [], { compactLabels: false });
    renderBarList('chartCategory', s.distribuciones?.categoria || [], 'reclamos');
    renderBarList('chartNivel', s.distribuciones?.nivel || [], 'tickets');
    renderBarList('chartEstado', s.distribuciones?.estado || [], 'tickets');
    renderAvgList('chartAvgCategory', s.promedios?.por_categoria || []);
    renderBacklog(s.backlog || []);
    renderNocBoard();
  }

  function renderColumnChart(id, data, opts = {}) {
    const el = $(id);
    if (!el) return;
    if (!data.length) {
      el.innerHTML = '<p class="text-slate-500 text-sm">Sin datos.</p>';
      return;
    }
    const max = Math.max(...data.map((x) => x.count), 1);
    el.innerHTML = `
      <div class="h-full flex items-end gap-1 border-b border-slate-800 pb-6">
        ${data.map((x, i) => {
          const h = Math.max((x.count / max) * 100, x.count ? 8 : 2);
          const showLabel = !opts.compactLabels || i % 5 === 0 || i === data.length - 1;
          return `<div class="flex-1 h-full flex flex-col justify-end items-center min-w-0">
            <div title="${escapeHtml(x.label)}: ${x.count}" class="w-full rounded-t bg-cyan-400/70 border border-cyan-300/20" style="height:${h}%"></div>
            <span class="mt-1 text-[9px] font-mono text-slate-600 truncate w-full text-center">${showLabel ? escapeHtml(String(x.label).slice(5)) : ''}</span>
          </div>`;
        }).join('')}
      </div>`;
  }

  function renderBarList(id, data, unit) {
    const el = $(id);
    if (!el) return;
    if (!data.length) {
      el.innerHTML = '<p class="text-slate-500 text-sm">Sin datos.</p>';
      return;
    }
    const max = Math.max(...data.map((x) => x.count), 1);
    el.innerHTML = data.slice(0, 8).map((x) => {
      const w = Math.max((x.count / max) * 100, 4);
      return `<div>
        <div class="flex justify-between text-xs mb-1">
          <span class="text-slate-300 truncate">${escapeHtml(x.label)}</span>
          <span class="font-mono text-slate-500">${x.count} ${unit}</span>
        </div>
        <div class="h-2 rounded bg-slate-800 overflow-hidden">
          <div class="h-full rounded bg-violet-400/70" style="width:${w}%"></div>
        </div>
      </div>`;
    }).join('');
  }

  function renderAvgList(id, data) {
    const el = $(id);
    if (!el) return;
    if (!data.length) {
      el.innerHTML = '<p class="text-slate-500 text-sm">Sin datos.</p>';
      return;
    }
    const max = Math.max(...data.map((x) => x.avg_hours), 1);
    el.innerHTML = data.slice(0, 8).map((x) => {
      const w = Math.max((x.avg_hours / max) * 100, 4);
      return `<div>
        <div class="flex justify-between text-xs mb-1">
          <span class="text-slate-300 truncate">${escapeHtml(x.label)}</span>
          <span class="font-mono text-slate-500">${x.avg_hours} hs · ${x.count} casos</span>
        </div>
        <div class="h-2 rounded bg-slate-800 overflow-hidden">
          <div class="h-full rounded bg-amber-400/70" style="width:${w}%"></div>
        </div>
      </div>`;
    }).join('');
  }

  function renderBacklog(items) {
    const el = $('statsBacklog');
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<p class="text-slate-500 text-sm">Sin backlog abierto.</p>';
      return;
    }
    el.innerHTML = items.map((t) => `
      <button type="button" class="w-full text-left p-2 rounded-lg border border-slate-800 bg-slate-950/50 hover:border-cyan-500/40 stats-ticket-link" data-id="${escapeHtml(t.id)}">
        <div class="flex justify-between items-center gap-2">
          <span class="font-mono text-cyan-300 text-[11px]">${escapeHtml(t.id)}</span>
          <span class="text-[10px] text-slate-500">${escapeHtml(t.horas_abierto)} hs</span>
        </div>
        <div class="flex gap-1 mt-1">${estadoBadge(t.nivel)}${estadoBadge(t.estado)}</div>
        <p class="text-[10px] text-slate-500 mt-1 truncate">${escapeHtml(t.linea || '')} · ${escapeHtml(t.categoria || '')}</p>
      </button>`).join('');
    el.querySelectorAll('.stats-ticket-link').forEach((b) => {
      b.onclick = async () => {
        await selectTicket(b.dataset.id);
        switchTab('soporte');
      };
    });
  }

  async function loadStats() {
    const params = new URLSearchParams();
    const desde = $('statsDesde')?.value;
    const hasta = $('statsHasta')?.value;
    if (desde) params.set('desde', desde);
    if (hasta) params.set('hasta', hasta);
    const qs = params.toString();
    state.stats = await api(`/api/v1/analytics/tickets${qs ? `?${qs}` : ''}`);
    renderStats();
  }

  function renderTenantSelect() {
    const wrap = $('tenantSwitchWrap');
    if (!isAdmin()) {
      wrap.classList.add('hidden');
      return;
    }
    wrap.classList.remove('hidden');
    wrap.classList.add('flex');
    const sel = $('tenantSelect');
    sel.innerHTML = state.orgs.map((o) =>
      `<option value="${o.slug}" ${o.slug === state.tenantSlug ? 'selected' : ''}>${escapeHtml(o.nombre)}</option>`
    ).join('');
    sel.onchange = async () => {
      state.tenantSlug = sel.value;
      state.historial = [];
      state.traces = [];
      state.ticketFormacion = null;
      state.ticketTimeline = [];
      renderChat();
      renderTicketFormacion();
      await refreshData();
      appendTrace([`🔀 Vista NOC imowi → ${state.orgName}`]);
    };
  }

  async function loadSession() {
    const ctx = await api('/api/v1/session/context');
    state.rol = ctx.rol;
    applyBrand(ctx);
    applyAccessMode();
  }

  function applyAccessMode() {
    const admin = isAdmin();
    ['red', 'stats', 'kb'].forEach((name) => {
      $(`nav-${name}`)?.classList.toggle('hidden', !admin);
    });
    $('tenantSwitchWrap')?.classList.toggle('hidden', !admin);
    if ($('tenantSwitchLabel')) {
      $('tenantSwitchLabel').textContent = admin ? 'Vista global / cooperativa' : 'Mi cooperativa';
    }
    $('btnEscalar')?.classList.toggle('hidden', admin);
    $('kbForm')?.classList.toggle('hidden', !admin);
    $('adminNocBoard')?.classList.toggle('hidden', !admin);
    $('chatMessages')?.classList.toggle('hidden', admin);
    $('chatForm')?.classList.toggle('hidden', admin);
    $('supportMainTitle').textContent = admin ? 'Centro de Control NOC' : 'Copilot de Reclamos';
    $('supportMainSubtitle').textContent = admin
      ? 'Cola operativa · priorización · seguimiento'
      : 'Cargá el reclamo y seguí el estado del ticket';
    if (!admin && ['red', 'stats', 'kb'].some((name) => !$(`tab-${name}`)?.classList.contains('hidden'))) {
      switchTab('soporte');
    }
  }

  async function refreshData() {
    await loadSession();
    const optionalLoads = [
      api('/api/v1/tickets').then((d) => { state.tickets = d.tickets || []; renderTickets(); }),
      api('/api/v1/tickets/notifications').then((d) => { state.notifications = d.notificaciones || []; renderNotifications(); }),
    ];
    if (isAdmin()) {
      optionalLoads.push(
        api('/api/v1/telemetry').then((d) => { state.telemetry = d.elementos || []; renderTelemetry(); }),
        api('/api/v1/kb').then((d) => { state.kb = d.articulos || []; renderKB(); }),
        loadStats(),
      );
    }
    const results = await Promise.allSettled(optionalLoads);
    const failed = results
      .filter((r) => r.status === 'rejected')
      .map((r) => r.reason?.message || 'módulo no disponible');
    if (failed.length) {
      appendTrace(failed.map((m) => `⚠️ Carga parcial: ${m}`));
    }
    renderNocBoard();
  }

  async function sendMessage(forzar = false) {
    if (state.sending) return;
    const input = $('chatInput');
    const text = (input?.value || '').trim();
    if (!text && !forzar) return;
    state.sending = true;
    if (text) {
      state.historial.push({ rol: 'usuario', contenido: text });
      input.value = '';
      renderChat();
    }
    try {
      const res = await api('/api/v1/chat', {
        method: 'POST',
        body: JSON.stringify({
          historial: state.historial.slice(0, -1),
          mensaje: text,
          forzar_escalamiento: forzar,
          session_id: ensureSessionId(),
        }),
      });
      state.historial.push({ rol: 'asistente', contenido: res.respuesta });
      state.estadoConversacion = res.estado_conversacion || state.estadoConversacion;
      renderEstadoCaso();
      appendTrace(res.agent_traces);
      if (res.usar_ia === false) appendTrace(['💬 Motor: respuesta sin IA']);
      if (res.ficha_jsc) {
        state.fichaJsc = res.ficha_jsc;
        renderFichaJsc(res.ficha_jsc);
      }
      if (res.ticket) {
        state.ticketFormacion = res.ticket;
        await api('/api/v1/tickets').then((d) => { state.tickets = d.tickets || []; renderTickets(); });
        await api('/api/v1/tickets/notifications').then((d) => { state.notifications = d.notificaciones || []; renderNotifications(); });
        if (isAdmin()) await loadStats();
        await selectTicket(res.ticket.id);
      }
      renderChat();
      renderTicketFormacion();
    } catch (e) {
      appendTrace([`❌ ${e.message}`]);
    } finally {
      state.sending = false;
    }
  }

  async function simulateFailure(el) {
    appendTrace([`⚡ Simulando falla en ${el}…`]);
    try {
      const res = await api('/api/v1/telemetry/simulate', {
        method: 'POST',
        body: JSON.stringify({ elemento_red: el }),
      });
      appendTrace(res.reaccion_autonoma?.agent_traces || []);
      if (res.reaccion_autonoma?.ficha_jsc) renderFichaJsc(res.reaccion_autonoma.ficha_jsc);
      if (res.reaccion_autonoma?.ticket) {
        state.ticketFormacion = res.reaccion_autonoma.ticket;
        await selectTicket(res.reaccion_autonoma.ticket.id);
      }
      if (res.reaccion_autonoma?.respuesta) {
        state.historial.push({ rol: 'asistente', contenido: `[Proactivo] ${res.reaccion_autonoma.respuesta}` });
        renderChat();
      }
      await refreshData();
      renderTicketFormacion();
      switchTab('soporte');
    } catch (e) {
      appendTrace([`❌ ${e.message}`]);
    }
  }

  function switchTab(name) {
    ['soporte', 'red', 'stats', 'kb'].forEach((t) => {
      $(`tab-${t}`)?.classList.toggle('hidden', t !== name);
      const btn = $(`nav-${t}`);
      if (btn) {
        btn.classList.toggle('text-cyan-300', t === name);
        btn.classList.toggle('border-cyan-500/50', t === name);
        btn.classList.toggle('text-slate-500', t !== name);
      }
    });
    if (name === 'stats') renderStats();
  }

  async function boot() {
    await restoreSession();
    const tenants = await api('/api/v1/tenants');
    state.orgs = tenants.organizaciones || [];
    renderTenantSelect();
    await refreshData();
    renderFichaJsc(null);
    renderTicketFormacion();
    appendTrace(['🛰️ Operations Hub conectado.', '📡 Catálogo JSC (réplica demo) listo.']);
  }

  function bind() {
    $('loginForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      $('loginError').classList.add('hidden');
      try {
        await login($('loginUser').value.trim(), $('loginPass').value);
      } catch (err) {
        $('loginError').textContent = err.message;
        $('loginError').classList.remove('hidden');
      }
    });
    $('btnLogout')?.addEventListener('click', logout);
    $('chatForm')?.addEventListener('submit', (e) => { e.preventDefault(); sendMessage(false); });
    $('btnEscalar')?.addEventListener('click', () => sendMessage(true));
    $('nav-soporte')?.addEventListener('click', () => switchTab('soporte'));
    $('nav-red')?.addEventListener('click', () => switchTab('red'));
    $('nav-stats')?.addEventListener('click', () => switchTab('stats'));
    $('nav-kb')?.addEventListener('click', () => switchTab('kb'));
    $('btnClearTraces')?.addEventListener('click', () => { state.traces = []; renderTraces(); });
    $('statsFilters')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        if (isAdmin()) await loadStats();
        appendTrace(['📊 Estadísticas actualizadas']);
      } catch (err) {
        appendTrace([`❌ Estadísticas: ${err.message}`]);
      }
    });
    $('kbForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await api('/api/v1/kb', {
          method: 'POST',
          body: JSON.stringify({
            titulo: $('kbTitulo').value,
            categoria: $('kbCategoria').value,
            contenido: $('kbContenido').value,
          }),
        });
        $('kbTitulo').value = '';
        $('kbContenido').value = '';
        await refreshData();
        appendTrace(['📚 KB actualizada']);
      } catch (err) {
        appendTrace([`❌ KB: ${err.message}`]);
      }
    });
  }

  bind();
  switchTab('soporte');
  if (state.token) {
    showApp(true);
    boot().catch(() => logout());
  }
})();
