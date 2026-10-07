'use strict';

// Run before the stylesheet so the first paint already uses the chosen theme.
(() => {
  const storageKey = 'caos.theme';
  const choices = new Set(['system', 'light', 'dark']);
  const root = document.documentElement;
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  let control = null;

  function t(source, params = {}) {
    if (window.CaosI18n) return window.CaosI18n.t(source, params);
    return source.replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`);
  }

  function normalize(value) {
    return choices.has(value) ? value : 'system';
  }

  try {
    preference = normalize(window.localStorage.getItem(storageKey));
  } catch {
    // Private browsing or storage policies must not prevent the app from opening.
  }

  function applyTheme() {
    const theme = preference === 'system' ? (systemTheme.matches ? 'dark' : 'light') : preference;
    root.dataset.theme = theme;
    root.dataset.themePreference = preference;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#101c20' : '#f6f7f3';
    if (control) {
      control.value = preference;
      const themeName = t(theme === 'dark' ? 'scuro' : 'chiaro');
      control.title = preference === 'system'
        ? t('Segue il tema del dispositivo: {theme}', { theme: themeName })
        : t('Tema {theme}', { theme: themeName });
    }
  }

  applyTheme();

  function connectControl() {
    control = document.getElementById('theme-preference');
    if (!control) return;
    applyTheme();
    control.addEventListener('change', () => {
      preference = normalize(control.value);
      applyTheme();
      try {
        window.localStorage.setItem(storageKey, preference);
      } catch {
        // Keep the current selection usable even if it cannot be saved.
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connectControl, { once: true });
  } else {
    connectControl();
  }

  const followSystem = () => {
    if (preference === 'system') applyTheme();
  };
  if (systemTheme.addEventListener) systemTheme.addEventListener('change', followSystem);
  else systemTheme.addListener(followSystem);
  window.addEventListener('caos:languagechange', applyTheme);

  window.addEventListener('storage', (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    try {
      if (event.storageArea !== window.localStorage) return;
    } catch {
      return;
    }
    preference = normalize(event.newValue);
    applyTheme();
  });
})();
