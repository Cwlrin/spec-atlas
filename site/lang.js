/*
 * 语言两态：zh | en。
 *
 * 规则集中在这一个文件里，页面只声明状态：「<html data-lang>」决定显示哪一版文案，
 * CSS 负责把另一版藏起来。切换只改属性、不跳转也不刷新，所以切换后仍停在当前字段页。
 * 选择记在 localStorage；读不到（首次访问、被隐私模式禁写）就回默认中文。
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "spec-atlas.lang";
  var DEFAULT_LANG = "zh";
  var LANGS = ["zh", "en"];

  function normalize(value) {
    return LANGS.indexOf(value) === -1 ? DEFAULT_LANG : value;
  }

  function stored(storage) {
    try {
      return normalize(storage ? storage.getItem(STORAGE_KEY) : null);
    } catch (error) {
      return DEFAULT_LANG;
    }
  }

  function save(storage, lang) {
    try {
      if (storage) {
        storage.setItem(STORAGE_KEY, normalize(lang));
      }
    } catch (error) {
      /* 禁写 localStorage 时保持本次选择即可，不该让页面挂掉。 */
    }
  }

  function apply(root, lang) {
    var next = normalize(lang);
    root.setAttribute("data-lang", next);
    root.setAttribute("lang", next === "en" ? "en" : "zh-CN");
    var document_ = root.ownerDocument;
    var title = root.getAttribute("data-title-" + next);
    if (document_ && title) {
      document_.title = title;
    }
    return next;
  }

  function paint(controls, lang) {
    for (var i = 0; i < controls.length; i += 1) {
      var active = controls[i].getAttribute("data-lang-set") === lang;
      controls[i].setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function set(lang, root, storage) {
    var scope = root || document.documentElement;
    var next = apply(scope, lang);
    save(storage || window.localStorage, next);
    if (typeof document !== "undefined") {
      paint(document.querySelectorAll("[data-lang-set]"), next);
    }
    return next;
  }

  function wire() {
    var controls = document.querySelectorAll("[data-lang-set]");
    for (var i = 0; i < controls.length; i += 1) {
      controls[i].addEventListener("click", function () {
        set(this.getAttribute("data-lang-set"));
      });
    }
    return controls;
  }

  function boot() {
    var lang = apply(document.documentElement, stored(window.localStorage));
    paint(wire(), lang);
  }

  global.SpecAtlasLang = {
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT_LANG: DEFAULT_LANG,
    LANGS: LANGS,
    normalize: normalize,
    stored: stored,
    save: save,
    apply: apply,
    set: set
  };

  if (typeof document !== "undefined") {
    /* 脚本放在 head：解析到这里就先把语言定下来，避免英文读者看到一闪而过的中文。 */
    apply(document.documentElement, stored(window.localStorage));
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }
})(typeof window !== "undefined" ? window : this);
