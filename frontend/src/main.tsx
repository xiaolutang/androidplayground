/**
 * main.tsx — 应用入口
 *
 * 挂载顺序：
 * 1. dev 模式 + VITE_USE_MOCK !== 'false' → 动态 import MSW browser worker
 * 2. QueryClientProvider → AntdApp → ConfigProvider(zhCN) → RouterProvider
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { RouterProvider } from 'react-router-dom';
import { router } from '@/App';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

async function enableMockWorker() {
  if (
    import.meta.env.DEV &&
    import.meta.env.VITE_USE_MOCK !== 'false'
  ) {
    const { worker } = await import('@/mocks/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
    });
  }
}

enableMockWorker().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <AntdApp>
          <ConfigProvider locale={zhCN}>
            <RouterProvider router={router} />
          </ConfigProvider>
        </AntdApp>
      </QueryClientProvider>
    </React.StrictMode>,
  );
});
