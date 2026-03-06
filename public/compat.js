/**
 * compat.js — 浏览器兼容性修复
 *
 * 1. Firefox 115 ESR 中文 IME 输入修复（React 受控组件兼容）
 * 2. Chrome 109 (Win7 最高版本) API polyfill
 */

// =============================================================================
// Part A: Firefox IME 输入修复
//
// 根本原因：React 18 的受控组件在 IME 组合过程中执行 textarea.value = state，
// 会导致浏览器取消 IME 组合，用户选的中文字被拼音覆盖。
//
// 修复策略：
//   1. 拦截 HTMLTextAreaElement.prototype.value 的 setter，在 IME 组合期间
//      阻止 React 写入 value（保护浏览器的原生 IME 文本替换）
//   2. compositionend 后通过 setTimeout 恢复正常，并派发 input 事件让
//      React 同步最终的中文文本
//   3. 在捕获阶段拦截 Enter keydown，防止 IME 选字时触发消息发送
// =============================================================================
(function () {
  // 设为 true 可在控制台看到调试日志
  var COMPAT_DEBUG = false;

  if (COMPAT_DEBUG) {
    console.log("[compat.js] 脚本已加载, UA:", navigator.userAgent);
  }

  // --- 保存原始的 value getter/setter（必须在 React 加载前执行） ---
  var textareaDesc = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    "value"
  );
  var nativeGet = textareaDesc.get;
  var nativeSet = textareaDesc.set;

  // 当前正在进行 IME 组合的元素（null 表示无组合）
  var composingEl = null;

  // --- 组合事件监听（捕获阶段，先于 React） ---
  document.addEventListener(
    "compositionstart",
    function (e) {
      if (e.target instanceof HTMLTextAreaElement) {
        composingEl = e.target;
        if (COMPAT_DEBUG) {
          console.log("[compat.js] compositionstart, 开始保护 textarea value");
        }
      }
    },
    true
  );

  document.addEventListener(
    "compositionend",
    function (e) {
      if (composingEl === e.target) {
        var el = e.target;
        // 读取浏览器完成 IME 替换后的真实值（中文字符）
        var finalValue = nativeGet.call(el);
        if (COMPAT_DEBUG) {
          console.log("[compat.js] compositionend, 最终值:", finalValue);
        }
        // 延迟解除保护，确保当前事件循环中 React 的 re-render 不会覆盖值
        setTimeout(function () {
          composingEl = null;
          if (COMPAT_DEBUG) {
            console.log("[compat.js] 保护已解除, 派发 input 事件同步 React");
          }
          // 用原始 setter 写入最终值，再派发 input 事件让 React 同步状态
          nativeSet.call(el, finalValue);
          var inputEvent = new Event("input", { bubbles: true });
          el.dispatchEvent(inputEvent);
        }, 0);
      }
    },
    true
  );

  // 安全措施：如果元素在组合中失焦，解除保护
  document.addEventListener(
    "blur",
    function (e) {
      if (composingEl === e.target) {
        composingEl = null;
        if (COMPAT_DEBUG) {
          console.log("[compat.js] blur 时解除保护");
        }
      }
    },
    true
  );

  // --- 拦截 textarea.value setter ---
  Object.defineProperty(HTMLTextAreaElement.prototype, "value", {
    get: nativeGet,
    set: function (val) {
      if (composingEl === this) {
        // IME 组合中，阻止 React 覆盖 textarea 的值
        if (COMPAT_DEBUG) {
          console.log("[compat.js] 已拦截 React 对 value 的写入:", val);
        }
        return;
      }
      nativeSet.call(this, val);
    },
    configurable: true,
    enumerable: true,
  });

  // --- Enter 键拦截（防止 IME 选字时触发发送） ---
  document.addEventListener(
    "keydown",
    function (e) {
      var composing = composingEl || e.isComposing || e.keyCode === 229;
      if (composing && (e.key === "Enter" || e.keyCode === 13)) {
        e.stopPropagation();
        if (COMPAT_DEBUG) {
          console.log("[compat.js] 已拦截 Enter keydown (IME 组合中)");
        }
      }
    },
    true
  );
})();

// =============================================================================
// Part B: Chrome 109 API Polyfills
//
// Chrome 110+ 新增的 Array 方法 (Change Array by Copy proposal)
// Chrome 117+ 新增的 Object.groupBy / Map.groupBy
// =============================================================================

// --- Array.prototype.toSorted (Chrome 110+) ---
if (!Array.prototype.toSorted) {
  Array.prototype.toSorted = function (compareFn) {
    var copy = this.slice();
    if (compareFn) {
      copy.sort(compareFn);
    } else {
      copy.sort();
    }
    return copy;
  };
}

// --- Array.prototype.toReversed (Chrome 110+) ---
if (!Array.prototype.toReversed) {
  Array.prototype.toReversed = function () {
    return this.slice().reverse();
  };
}

// --- Array.prototype.toSpliced (Chrome 110+) ---
if (!Array.prototype.toSpliced) {
  Array.prototype.toSpliced = function (start, deleteCount) {
    var copy = this.slice();
    var args = [start, deleteCount];
    for (var i = 2; i < arguments.length; i++) {
      args.push(arguments[i]);
    }
    copy.splice.apply(copy, args);
    return copy;
  };
}

// --- Array.prototype.with (Chrome 110+) ---
if (!Array.prototype.with) {
  Array.prototype.with = function (index, value) {
    var copy = this.slice();
    if (index < 0) {
      index = copy.length + index;
    }
    if (index < 0 || index >= copy.length) {
      throw new RangeError("Invalid index: " + index);
    }
    copy[index] = value;
    return copy;
  };
}

// --- Array.prototype.findLast / findLastIndex (Chrome 97+, but polyfill for safety) ---
if (!Array.prototype.findLast) {
  Array.prototype.findLast = function (callbackFn, thisArg) {
    for (var i = this.length - 1; i >= 0; i--) {
      if (callbackFn.call(thisArg, this[i], i, this)) {
        return this[i];
      }
    }
    return undefined;
  };
}

if (!Array.prototype.findLastIndex) {
  Array.prototype.findLastIndex = function (callbackFn, thisArg) {
    for (var i = this.length - 1; i >= 0; i--) {
      if (callbackFn.call(thisArg, this[i], i, this)) {
        return i;
      }
    }
    return -1;
  };
}

// --- Object.groupBy (Chrome 117+) ---
if (typeof Object.groupBy !== "function") {
  Object.groupBy = function (iterable, callbackFn) {
    var result = Object.create(null);
    var index = 0;
    for (var item of iterable) {
      var key = callbackFn(item, index++);
      if (!(key in result)) {
        result[key] = [];
      }
      result[key].push(item);
    }
    return result;
  };
}

// --- Map.groupBy (Chrome 117+) ---
if (typeof Map.groupBy !== "function") {
  Map.groupBy = function (iterable, callbackFn) {
    var map = new Map();
    var index = 0;
    for (var item of iterable) {
      var key = callbackFn(item, index++);
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key).push(item);
    }
    return map;
  };
}

// --- structuredClone (Chrome 98+, but polyfill for older environments) ---
if (typeof structuredClone !== "function") {
  window.structuredClone = function (value) {
    return JSON.parse(JSON.stringify(value));
  };
}
