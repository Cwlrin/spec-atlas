/* node 侧的浏览器桩：只模拟 notice.js 用到的那一小块 DOM，
 * 让「首次出现 / 关掉后不再出现」能在没有浏览器的地方被测到。
 * 用法：node tests/fixtures/notice-probe.js <scenario>，结果以 JSON 打到 stdout。
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const NOTICE_JS = path.join(__dirname, "..", "..", "site", "notice.js");

function makeStorage(initial) {
  const data = Object.assign({}, initial || {});
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = String(value);
    },
    data
  };
}

function makeElement(attributes) {
  const attrs = Object.assign({}, attributes || {});
  const handlers = {};
  const element = {
    attributes: attrs,
    handlers: handlers,
    hidden: false,
    style: {},
    getAttribute(name) {
      return name in attrs ? attrs[name] : null;
    },
    setAttribute(name, value) {
      attrs[name] = String(value);
    },
    removeAttribute(name) {
      delete attrs[name];
    },
    addEventListener(type, handler) {
      (handlers[type] = handlers[type] || []).push(handler);
    },
    dispatch(type) {
      (handlers[type] || []).forEach((handler) => handler.call(element, { type }));
    },
    /* 关掉之后的样子：从可见文档里消失。 */
    remove() {
      element.removed = true;
    }
  };
  return element;
}

function makeDom(stored) {
  /* 与模板一致：提示条默认带 hidden，由脚本决定是否揭开。 */
  const dismiss = makeElement({ "data-notice-dismiss": "" });
  const notice = makeElement({ "data-first-visit-notice": "", hidden: "" });
  /* 关闭按钮必须在提示条内部：拖到外面就不是「关这条提示」了。 */
  const parents = new Map([[dismiss, notice]]);
  /* 真 DOM 里元素自己也有 querySelectorAll：关闭按钮是在提示条内部找的。 */
  notice.querySelectorAll = (selector) =>
    selector === "[data-notice-dismiss]" ? [dismiss] : [];
  dismiss.querySelectorAll = (selector) => (parents.get(dismiss) === notice ? [] : []);

  const document = {
    readyState: "complete",
    documentElement: makeElement({ "data-lang": "zh" }),
    addEventListener(type, handler) {
      (listeners[type] = listeners[type] || []).push(handler);
    },
    querySelectorAll(selector) {
      if (selector === "[data-first-visit-notice]") return [notice];
      if (selector === "[data-notice-dismiss]") return [dismiss];
      return [];
    },
    querySelector(selector) {
      if (selector === "[data-first-visit-notice]") return notice;
      return null;
    }
  };
  const listeners = {};
  document.parentElement = (node) => parents.get(node) || null;
  document.removeChild = (node) => {
    node.removed = true;
  };

  const storage = makeStorage(stored);
  const window = { localStorage: storage, document };

  return { window, document, notice, dismiss, storage, listeners };
}

function load(dom) {
  const context = vm.createContext({
    window: dom.window,
    document: dom.document,
    localStorage: dom.storage
  });
  vm.runInContext(fs.readFileSync(NOTICE_JS, "utf8"), context, { filename: NOTICE_JS });
  /* 若脚本监听 DOMContentLoaded 而不是立即跑，补一次事件。 */
  (dom.listeners.DOMContentLoaded || []).forEach((handler) => handler({ type: "DOMContentLoaded" }));
  return context;
}

function snapshot(dom) {
  /* 可见 = 没被移除、hidden 已摘掉、状态不是 dismissed。
     模板默认带 hidden，所以「显示」必须是脚本主动揭开的结果。 */
  const visible = dom.notice.removed !== true &&
    dom.notice.hidden !== true &&
    dom.notice.getAttribute("hidden") === null &&
    dom.notice.getAttribute("data-first-visit-notice") !== "dismissed";
  return {
    notice: visible ? "shown" : "dismissed",
    revealed: visible,
    stored: dom.storage.data["spec-atlas.notice"] || null,
    dismisses: dom.dismiss.handlers ? (dom.dismiss.handlers.click || []).length : 0,
    display: dom.notice.style.display || null
  };
}

const scenarios = {
  /* 首次访问：什么都没有，提示条应当出现，且不写任何标记。 */
  "fresh": () => {
    const dom = makeDom({});
    load(dom);
    return snapshot(dom);
  },
  /* 点关闭：提示条消失，标记写入本机。 */
  "dismiss-click": () => {
    const dom = makeDom({});
    load(dom);
    dom.dismiss.dispatch("click");
    return snapshot(dom);
  },
  /* 上次关过：带着标记重新进站，提示条不再出现。 */
  "dismissed-before": () => {
    const dom = makeDom({ "spec-atlas.notice": "1" });
    load(dom);
    return snapshot(dom);
  },
  /* 存了脏值：当没关过处理，提示条出现。 */
  "corrupt": () => {
    const dom = makeDom({ "spec-atlas.notice": "banana" });
    load(dom);
    return snapshot(dom);
  },
  /* 读 localStorage 这一步就抛（禁 cookie / 沙箱）：首次访问仍要看到提示条。 */
  "storage-blocked": () => {
    const dom = makeDom({});
    Object.defineProperty(dom.window, "localStorage", {
      get() {
        throw new Error("blocked");
      }
    });
    load(dom);
    return snapshot(dom);
  },
  /* localStorage 禁写（隐私模式）：当次仍能关掉，不炸。 */
  "storage-denied": () => {
    const dom = makeDom({});
    dom.storage.setItem = () => {
      throw new Error("denied");
    };
    load(dom);
    dom.dismiss.dispatch("click");
    return snapshot(dom);
  }
};

const name = process.argv[2];
if (!scenarios[name]) {
  console.error("unknown scenario: " + name);
  process.exit(2);
}
process.stdout.write(JSON.stringify(scenarios[name]()));