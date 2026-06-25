/**
 * vitest setup — jsdom + jest-dom + MSW server lifecycle + DOM polyfills
 *
 * beforeAll: server.listen（未处理请求 → error）
 * afterEach: server.resetHandlers（每例隔离）
 * afterAll: server.close
 */

import '@testing-library/jest-dom';
import { server } from '@/mocks/server';

// ---------------------------------------------------------------------------
// jsdom 缺失的 API polyfills（antd / @rc-component 依赖）
// ---------------------------------------------------------------------------

// ResizeObserver
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
}

// window.matchMedia
if (typeof window.matchMedia === 'undefined') {
  window.matchMedia = ((query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// IntersectionObserver（部分 antd 组件可能用到）
if (typeof globalThis.IntersectionObserver === 'undefined') {
  class MockIntersectionObserver {
    readonly root = null;
    readonly rootMargin = '0px';
    readonly thresholds: ReadonlyArray<number> = [0];
    constructor(
      _callback: IntersectionObserverCallback,
      _options?: IntersectionObserverInit,
    ) {}
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  globalThis.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
}

// ---------------------------------------------------------------------------
// MSW server lifecycle
// ---------------------------------------------------------------------------
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
