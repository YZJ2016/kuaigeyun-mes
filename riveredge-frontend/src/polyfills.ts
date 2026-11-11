/**
 * 第三方产物（如 @svar-ui/react-gantt）会调用 ES2023 Array 方法。
 * 旧 Chromium / 内网浏览器无原生实现时，须在入口最先补齐，否则应用加载报错。
 */

function installArrayToSorted(): void {
  if (typeof Array === 'undefined') return;
  if (typeof (Array.prototype as { toSorted?: unknown }).toSorted === 'function') return;
  Object.defineProperty(Array.prototype, 'toSorted', {
    configurable: true,
    writable: true,
    value: function toSorted<T>(
      this: T[],
      compareFn?: (a: T, b: T) => number,
    ): T[] {
      return this.slice().sort(compareFn);
    },
  });
}

installArrayToSorted();
