/*
 * 首次访问提示条：只关心「第一次来就说明白，关过就别再烦人」。
 *
 * 规则集中在这一个文件里，页面只提供两个钩子：
 *   [data-first-visit-notice] 提示条本体，[data-notice-dismiss] 关闭按钮。
 * 关掉的标记写 localStorage；读不到（首次访问、隐私模式禁写）就当没关过，
 * 但禁写时当次仍然要能关掉——不能让页面因为存不下来就卡住。
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "spec-atlas.notice";
  var DONE = "1";

  function dismissed(storage) {
    try {
      return storage ? storage.getItem(STORAGE_KEY) === DONE : false;
    } catch (error) {
      return false;
    }
  }

  function remember(storage) {
    try {
      if (storage) {
        storage.setItem(STORAGE_KEY, DONE);
      }
    } catch (error) {
      /* 禁写时只保证本次关掉即可，不该让页面挂掉。 */
    }
  }

  function hide(bar) {
    bar.setAttribute("data-first-visit-notice", "dismissed");
    bar.hidden = true;
    if (bar.style) {
      bar.style.display = "none";
    }
    if (typeof bar.remove === "function") {
      bar.remove();
    }
    var parent = bar.parentNode;
    if (parent && typeof parent.removeChild === "function") {
      parent.removeChild(bar);
    }
  }

  function show(bar) {
    /* 页面里默认 hidden：到这里才揭开，回访者不会看到它闪一下。 */
    bar.hidden = false;
    bar.removeAttribute("hidden");
    if (bar.style) {
      bar.style.display = "";
    }
  }

  function start() {
    var bars = document.querySelectorAll("[data-first-visit-notice]");
    if (!bars.length) {
      return;
    }
    var storage = global.localStorage;
    for (var i = 0; i < bars.length; i += 1) {
      var bar = bars[i];
      if (dismissed(storage)) {
        hide(bar);
        continue;
      }
      show(bar);
      wire(bar, storage);
    }
  }

  function wire(bar, storage) {
    var buttons = bar.querySelectorAll
      ? bar.querySelectorAll("[data-notice-dismiss]")
      : [];
    if (!buttons.length && typeof document !== "undefined") {
      buttons = document.querySelectorAll("[data-notice-dismiss]");
    }
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") {
          event.preventDefault();
        }
        remember(storage);
        hide(bar);
      });
    }
  }

  global.SpecAtlasNotice = {
    STORAGE_KEY: STORAGE_KEY,
    dismissed: dismissed,
    remember: remember,
    hide: hide,
    start: start
  };

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }
})(typeof window !== "undefined" ? window : this);