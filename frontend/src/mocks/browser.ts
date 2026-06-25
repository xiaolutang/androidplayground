/**
 * MSW browser worker — dev 用
 *
 * main.tsx dev 模式动态启用：
 *   const { worker } = await import('@/mocks/browser')
 *   worker.start({ onUnhandledRequest: 'bypass' })
 */

import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

export const worker = setupWorker(...handlers);
