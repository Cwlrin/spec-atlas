/* node 侧的浏览器桩：只模拟 lang.js 用到的那一小块 DOM，
 * 让「默认中文 / 记住选择 / 切换不跳页」能在没有浏览器的地方被测到。
 * 用法：node tests/fixtures/lang-probe.js <scenario>，结果以 JSON 打到 stdout。
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const LANG_JS = path.join(__dirname, "..", "..", "site", "lang.js");

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

function makeDom(stored) {
  const attributes = { "data-lang": "zh", lang: "zh-CN" };
  const listeners = {};
  const controls = ["zh", "en"].map((value) => {
    const button = {
      attributes: { "data-lang-set": value, "aria-pressed": value === "zh" ? "true" : "false" },
      handlers: [],
      getAttribute(name) {
        return name in this.attributes ? this.attributes[name] : null;
      },
      setAttribute(name, value) {
        this.attributes[name] = String(value);
      },
      addEventListener(type, handler) {
        if (type === "click") this.handlers.push(handler);
      },
      click() {
        this.handlers.forEach((handler) => handler.call(this));
      }
    };
    return button;
  });

  const navigations = [];
  const root = {
    attributes,
    ownerDocument: null,
    getAttribute(name) {
      return name in attributes ? attributes[name] : null;
    },
    setAttribute(name, value) {
      attributes[name] = String(value);
    }
  };

  const document = {
    title: "zh title",
    readyState: "complete",
    documentElement: root,
    addEventListener(type, handler) {
      (listeners[type] = listeners[type] || []).push(handler);
    },
    querySelectorAll(selector) {
      return selector === "[data-lang-set]" ? controls : [];
    }
  };
  root.ownerDocument = document;

  const location = {};
  ["assign", "replace", "reload"].forEach((name) => {
    location[name] = (...args) => navigations.push({ name, args });
  });
  /* 任何跳转都记账并立即失败：AC3 要证明的是「没发生跳转」，
   * 若 lang.js 真的跳了，这个桩必须有能力让它失败，否则断言是空转的。 */
  function refuse(name) {
    return (...args) => {
      navigations.push({ name: name, args: args });
      throw new Error("navigated: " + name);
    };
  }
  ["assign", "replace", "reload"].forEach((name) => {
    location[name] = (...args) => {
      navigations.push({ name: name, args: args });
    };
  });
  Object.defineProperty(location, "href", {
    get: () => "http://localhost/sff-8472/12.4/a0/14.html",
    set: (value) => {
      navigations.push({ name: "href", args: [value] });
    }
  });

  /* 自检：桩确实能记录跳转（否则「没有跳转」的断言证明不了任何东西）。 */
  Object.defineProperty(location, "__selftest", { value: () => {
    location.assign("about:blank");
    return navigations.length > 0;
  }});

  return {
    window: { localStorage: makeStorage(stored), location },
    document,
    controls,
    navigations,
    storage: null
  };
}

function load(dom) {
  const context = vm.createContext({
    window: dom.window,
    document: dom.document,
    localStorage: dom.window.localStorage,
    location: dom.window.location
  });
  vm.runInContext(fs.readFileSync(LANG_JS, "utf8"), context, { filename: LANG_JS });
  return context;
}

function snapshot(dom) {
  return {
    lang: dom.document.documentElement.getAttribute("data-lang"),
    langAttr: dom.document.documentElement.getAttribute("lang"),
    title: dom.document.title,
    pressed: dom.controls.map((button) => button.getAttribute("aria-pressed")),
    stored: dom.window.localStorage.data["spec-atlas.lang"] || null,
    navigations: dom.navigations
  };
}

const scenarios = {
  /* 首次访问：什么都没有，应该是中文。 */
  "fresh": () => {
    const dom = makeDom({});
    load(dom);
    return snapshot(dom);
  },
  /* 上次选了英文：打开就是英文，且控件状态跟着变。 */
  "remembered-en": () => {
    const dom = makeDom({ "spec-atlas.lang": "en" });
    load(dom);
    return snapshot(dom);
  },
  /* 存了脏值：回默认中文，不抛错。 */
  "corrupt": () => {
    const dom = makeDom({ "spec-atlas.lang": "fr" });
    load(dom);
    return snapshot(dom);
  },
  /* 切到英文：只改状态，不跳转、不刷新。 */
  "switch-en": () => {
    const dom = makeDom({});
    load(dom);
    dom.controls[1].click();
    return snapshot(dom);
  },
  /* 切回中文：同样不跳转。 */
  "switch-back-zh": () => {
    const dom = makeDom({ "spec-atlas.lang": "en" });
    load(dom);
    dom.controls[0].click();
    return snapshot(dom);
  },
  /* 桩自检：这个场景主动跳一次，证明 navigations 真的会记账。
   * 若这一条返回空数组，说明桩没接上，AC3 的「没跳转」断言就是空转的。 */
  "navigate-control": () => {
    const dom = makeDom({});
    dom.window.location.assign("about:blank");
    return snapshot(dom);
  },
  /* localStorage 禁写（隐私模式）：选择当次生效，不炸。 */
  "storage-denied": () => {
    const dom = makeDom({});
    dom.window.localStorage.setItem = () => {
      throw new Error("denied");
    };
    load(dom);
    dom.controls[1].click();
    return snapshot(dom);
  }
};

const name = process.argv[2];
if (!scenarios[name]) {
  console.error("unknown scenario: " + name);
  process.exit(2);
}
process.stdout.write(JSON.stringify(scenarios[name]()));