/**
 * MSW server — vitest 用（node 环境）
 *
 * 供 test/setup.ts 启动：
 *   beforeAll: server.listen({ onUnhandledRequest: 'error' })
 *   afterEach: server.resetHandlers()
 *   afterAll: server.close()
 */

import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
