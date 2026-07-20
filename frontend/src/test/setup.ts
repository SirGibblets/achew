import '@testing-library/jest-dom/vitest';

// Node's experimental localStorage global (undefined without --localstorage-file)
// shadows jsdom's window.localStorage; provide an in-memory implementation.
if (typeof globalThis.localStorage?.getItem !== 'function') {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => {
      store.delete(key);
    },
    setItem: (key, value) => {
      store.set(key, String(value));
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage,
    configurable: true,
    writable: true,
  });
}

// jsdom lacks the Web Animations API used by Svelte transitions.
if (!Element.prototype.animate) {
  Element.prototype.animate = function (): Animation {
    const animation = {
      cancel() {},
      finish() {},
      pause() {},
      play() {},
      reverse() {},
      onfinish: null as (() => void) | null,
      oncancel: null,
      currentTime: 0,
      startTime: 0,
      playbackRate: 1,
      pending: false,
      playState: 'finished',
      effect: null,
      timeline: null,
      id: '',
      finished: Promise.resolve(),
      ready: Promise.resolve(),
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => true,
      commitStyles() {},
      persist() {},
      updatePlaybackRate() {},
    };
    queueMicrotask(() => animation.onfinish?.());
    return animation as unknown as Animation;
  };
}

// jsdom's <dialog> lacks showModal/close.
if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    if (!this.open) return;
    this.open = false;
    this.dispatchEvent(new Event('close'));
  };
}

// jsdom throws "not implemented" for scrolling APIs.
window.scrollTo = () => {};
window.scrollBy = () => {};
Element.prototype.scrollTo = () => {};
Element.prototype.scrollIntoView = () => {};

if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => true,
    }) as MediaQueryList;
}
