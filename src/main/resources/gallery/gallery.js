(() => {
  'use strict';
  const content = document.querySelector('#content');
  const categoryLabels = { journey: 'Journey', place: 'Place', people: 'People' };
  const entryIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const tokenPattern = /^[A-Za-z0-9_-]{22,64}$/;
  const versionPattern = /^[0-9a-f]{64}$/i;
  const refreshInterval = 4000;
  let currentController;
  let refreshController;
  let refreshTimer;
  let activeRoute;
  let activeView;
  let entries = [];
  let activeCategory = 'all';

  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = text;
    return result;
  }

  function texturedButton(className, label) {
    const button = node('button', className);
    button.type = 'button';
    button.append(node('span', 'button-label', label));
    return button;
  }

  function heading(title, eyebrow = 'THE EXHIBITION') {
    const wrapper = node('div', 'page-heading');
    wrapper.append(node('p', 'eyebrow', eyebrow), node('h1', '', title));
    return wrapper;
  }

  function state(title, detail = '', isError = false) {
    content.setAttribute('aria-busy', 'false');
    const panel = node('div', 'state-panel');
    panel.setAttribute('role', isError ? 'alert' : 'status');
    panel.append(node('span', 'empty-block'), node('p', 'state-title', title));
    if (detail) panel.append(node('p', 'state-detail', detail));
    if (!isError) return panel;
    const retry = texturedButton('stone-button error-actions', 'Try again');
    retry.addEventListener('click', () => loadRoute());
    panel.append(retry);
    return panel;
  }

  function loading() {
    content.setAttribute('aria-busy', 'true');
    const panel = node('div', 'state-panel');
    panel.setAttribute('role', 'status');
    panel.append(node('span', 'loading-block'), node('p', '', 'Opening the gallery…'));
    content.replaceChildren(heading('Build gallery.'), panel);
  }

  async function readJson(path, signal) {
    const response = await fetch(path, { signal, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer' });
    if (response.status === 404) throw new Error('missing');
    if (!response.ok) throw new Error('unavailable');
    return response.json();
  }

  function validImage(image, entryId) {
    if (!image || !Number.isInteger(image.slot) || image.slot < 1 || image.slot > 3) return false;
    if (typeof image.url !== 'string') return false;
    let imageUrl;
    try { imageUrl = new URL(image.url, location.origin); }
    catch { return false; }
    if (imageUrl.origin !== location.origin || imageUrl.hash) return false;
    if (imageUrl.pathname !== `/api/entries/${entryId}/images/${image.slot}`) return false;
    return [...imageUrl.searchParams].every(([key, value]) => imageUrl.searchParams.getAll(key).length === 1
      && ((key === 'token' && tokenPattern.test(value)) || (key === 'version' && versionPattern.test(value))));
  }

  function normalizeEntry(entry) {
    if (!entry || typeof entry.id !== 'string' || !entryIdPattern.test(entry.id)) return null;
    const category = String(entry.category || '').toLowerCase();
    if (!categoryLabels[category]) return null;
    const title = typeof entry.title === 'string' ? entry.title.trim().slice(0, 100) : '';
    const images = Array.isArray(entry.images) ? entry.images.filter(image => validImage(image, entry.id)).slice(0, 3)
      .map(image => ({ slot: image.slot, url: image.url, revision: versionPattern.test(image.revision || '') ? image.revision : '' })) : [];
    const renderer = typeof entry.renderer === 'string' ? entry.renderer.slice(0, 400) : '';
    return { id: entry.id, category, title: title || `${categoryLabels[category]} build`, images, renderer, submitted: entry.submitted === true };
  }

  function buildImage(image, title, isLazy = true) {
    const element = node('img', 'build-image image-loading');
    const imageUrl = new URL(image.url, location.origin);
    if (image.revision) imageUrl.searchParams.set('version', image.revision);
    element.src = imageUrl.pathname + imageUrl.search;
    element.alt = `${title}, camera ${image.slot}`;
    element.loading = isLazy ? 'lazy' : 'eager';
    element.decoding = 'async';
    element.addEventListener('load', () => element.classList.remove('image-loading'));
    element.addEventListener('error', () => element.replaceWith(node('span', 'image-unavailable', 'This view is unavailable.')));
    return element;
  }

  function buildCard(entry) {
    const card = node('a', 'build-card');
    card.href = `/entries/${entry.id}`;
    card.dataset.entryId = entry.id;
    const view = node('div', 'card-view');
    if (entry.images.length) view.append(buildImage(entry.images[0], entry.title));
    else view.append(node('span', 'image-unavailable', 'Views are being prepared.'));
    view.append(node('span', 'camera-count', `${entry.images.length} ${entry.images.length === 1 ? 'VIEW' : 'VIEWS'}`));
    const info = node('div', 'card-info');
    const label = node('div');
    label.append(node('span', 'card-category', categoryLabels[entry.category]), node('h2', 'card-title', entry.title));
    const arrow = node('span', 'card-arrow');
    arrow.setAttribute('aria-hidden', 'true');
    info.append(label, arrow);
    card.append(view, info);
    return card;
  }

  function updateGrid(grid, count) {
    const focusedId = document.activeElement.closest('.build-card')?.dataset.entryId;
    const filtered = entries.filter(entry => activeCategory === 'all' || entry.category === activeCategory);
    count.textContent = `${filtered.length} ${filtered.length === 1 ? 'BUILD' : 'BUILDS'}`;
    grid.replaceChildren(...filtered.map(buildCard));
    grid.className = filtered.length ? `gallery-grid${filtered.length >= 3 ? ' has-feature' : ''}` : '';
    if (!filtered.length) grid.append(state('No submitted builds yet.', activeCategory === 'all' ? 'The exhibition is waiting for its first entry.' : `Submitted ${categoryLabels[activeCategory]} entries will appear here.`));
    if (focusedId) grid.querySelector(`[data-entry-id="${focusedId}"]`)?.focus({ preventScroll: true });
  }

  function normalizeEntries(data) {
    const source = Array.isArray(data) ? data : data.entries;
    if (!Array.isArray(source)) throw new Error('unavailable');
    return source.slice(0, 1000).map(normalizeEntry).filter(Boolean);
  }

  function gallery(data) {
    entries = normalizeEntries(data);
    let signature = JSON.stringify(entries);
    const toolbar = node('div', 'gallery-toolbar');
    const filters = node('div', 'filters');
    filters.setAttribute('role', 'group');
    filters.setAttribute('aria-label', 'Filter builds by category');
    const count = node('span', 'entry-count');
    count.setAttribute('aria-live', 'polite');
    const grid = node('div', 'gallery-grid');
    for (const [key, label] of Object.entries({ all: 'All builds', ...categoryLabels })) {
      const button = texturedButton('filter', label);
      button.setAttribute('aria-pressed', String(activeCategory === key));
      button.addEventListener('click', () => {
        activeCategory = key;
        filters.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        updateGrid(grid, count);
      });
      filters.append(button);
    }
    toolbar.append(filters, count);
    content.replaceChildren(heading('Build gallery.'), toolbar, grid);
    content.setAttribute('aria-busy', 'false');
    updateGrid(grid, count);
    document.title = 'Build gallery';
    return { update(nextData) {
      const nextEntries = normalizeEntries(nextData);
      const nextSignature = JSON.stringify(nextEntries);
      if (nextSignature === signature) return;
      entries = nextEntries;
      signature = nextSignature;
      updateGrid(grid, count);
    } };
  }

  function detailUpdater(entry, isPrivate, selectedSlot) {
    const signature = JSON.stringify(entry);
    return { update(nextData) {
      const nextEntry = normalizeEntry(nextData);
      if (!nextEntry) throw new Error('unavailable');
      if (JSON.stringify(nextEntry) === signature) return;
      const focusedSlot = document.activeElement.closest('.camera-button')?.dataset.slot;
      const hasBackFocus = document.activeElement.classList.contains('back-link');
      const view = detail(nextData, isPrivate, selectedSlot());
      if (focusedSlot) content.querySelector(`[data-slot="${focusedSlot}"]`)?.focus({ preventScroll: true });
      if (hasBackFocus) content.querySelector('.back-link')?.focus({ preventScroll: true });
      return view;
    } };
  }

  function detail(data, isPrivate, preferredSlot) {
    const entry = normalizeEntry(data);
    if (!entry) throw new Error('unavailable');
    let selectedSlot = preferredSlot;
    const back = node('a', 'back-link', 'All builds');
    back.href = '/gallery';
    const title = heading(entry.title, categoryLabels[entry.category].toUpperCase());
    title.className = 'detail-heading';
    const titleGroup = node('div');
    titleGroup.append(...title.childNodes);
    title.append(titleGroup);
    if (isPrivate) title.append(node('span', 'privacy-label', entry.submitted ? 'SUBMITTED PREVIEW' : 'PRIVATE DRAFT'));
    const figure = node('figure', 'detail-stage');
    const frame = node('div', 'detail-image-frame');
    const caption = node('figcaption', 'detail-caption');
    const label = node('span');
    const position = node('span');
    caption.append(label, position);
    figure.append(frame, caption);
    const strip = node('div', 'camera-strip');
    strip.setAttribute('role', 'group');
    strip.setAttribute('aria-label', 'Saved camera views');
    const selectImage = index => {
      const image = entry.images[index];
      selectedSlot = image.slot;
      frame.replaceChildren(buildImage(image, entry.title, false));
      label.textContent = `Camera ${image.slot} · Server-rendered block preview`;
      position.textContent = `${index + 1} / ${entry.images.length}`;
      strip.querySelectorAll('button').forEach((button, buttonIndex) => button.setAttribute('aria-pressed', String(index === buttonIndex)));
    };
    entry.images.forEach((image, index) => {
      const button = node('button', 'camera-button');
      button.type = 'button';
      button.dataset.slot = image.slot;
      button.setAttribute('aria-label', `Show camera ${image.slot}`);
      button.append(buildImage(image, entry.title), node('span', '', `CAMERA ${image.slot}`));
      button.addEventListener('click', () => selectImage(index));
      strip.append(button);
    });
    content.replaceChildren(back, title);
    if (entry.images.length) {
      content.append(figure, strip);
      selectImage(Math.max(0, entry.images.findIndex(image => image.slot === selectedSlot)));
    } else content.append(state('Views are being prepared.', 'This preview updates automatically when your camera images are ready.'));
    if (entry.renderer && entry.images.length) content.append(node('p', 'draft-note', entry.renderer));
    if (isPrivate) content.append(node('p', 'draft-note', `Anyone with this private link can view this preview.${entry.submitted ? '' : ' Images show the last capture; submitting refreshes every view.'}`));
    content.setAttribute('aria-busy', 'false');
    document.title = `${entry.title} · Build gallery`;
    return detailUpdater(entry, isPrivate, () => selectedSlot);
  }

  function resolveRoute() {
    const parts = location.pathname.split('/').filter(Boolean);
    if (parts.length === 1 && parts[0] === 'gallery') return { api: '/api/entries', kind: 'gallery' };
    if (parts.length === 2 && parts[0] === 'entries' && entryIdPattern.test(parts[1])) {
      return { api: `/api/entries/${parts[1]}`, kind: 'entry' };
    }
    if (parts.length === 2 && parts[0] === 'preview' && tokenPattern.test(parts[1])) {
      return { api: `/api/preview/${parts[1]}`, kind: 'private' };
    }
    throw new Error('missing');
  }

  function showRouteError(error) {
    const isMissing = error.message === 'missing';
    content.replaceChildren(heading('Build gallery.'), state(isMissing ? 'This build is unavailable.' : 'The gallery is resting.', isMissing ? 'The entry may be private, withdrawn, or this link has expired.' : 'Please try again in a moment.', !isMissing));
    if (isMissing) { activeRoute = null; activeView = null; }
  }

  function stopRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = null;
    refreshController?.abort();
    refreshController = null;
  }

  function scheduleRefresh() {
    if (!activeRoute || document.hidden || refreshTimer || refreshController || currentController) return;
    refreshTimer = setTimeout(() => { refreshTimer = null; refreshRoute(); }, refreshInterval);
  }

  function applyRouteData(route, data) {
    if (activeView) { activeView = activeView.update(data) || activeView; return; }
    activeView = route.kind === 'gallery' ? gallery(data) : detail(data, route.kind === 'private');
  }

  async function refreshRoute() {
    if (!activeRoute || document.hidden || refreshController || currentController) return;
    const route = activeRoute;
    const controller = new AbortController();
    refreshController = controller;
    try {
      const data = await readJson(route.api, controller.signal);
      if (!controller.signal.aborted && route === activeRoute && !document.hidden) applyRouteData(route, data);
    } catch (error) {
      if (!controller.signal.aborted && route === activeRoute && error.message === 'missing') showRouteError(error);
    } finally {
      if (refreshController === controller) refreshController = null;
      if (route === activeRoute) scheduleRefresh();
    }
  }

  async function loadRoute() {
    stopRefresh();
    currentController?.abort();
    const controller = new AbortController();
    currentController = controller;
    activeRoute = null;
    activeView = null;
    loading();
    try {
      const route = resolveRoute();
      activeRoute = route;
      if (document.hidden) return;
      const data = await readJson(route.api, controller.signal);
      if (!controller.signal.aborted && route === activeRoute) applyRouteData(route, data);
    } catch (error) {
      if (!controller.signal.aborted) showRouteError(error);
    } finally {
      if (currentController === controller) currentController = null;
      scheduleRefresh();
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.hash) return;
    if (!/^\/(gallery|entries\/|preview\/)/.test(url.pathname)) return;
    event.preventDefault();
    history.pushState({}, '', url.pathname);
    loadRoute();
    window.scrollTo(0, 0);
    content.focus({ preventScroll: true });
  });
  window.addEventListener('popstate', loadRoute);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stopRefresh(); currentController?.abort(); return; }
    refreshRoute();
  });
  loadRoute();
})();
