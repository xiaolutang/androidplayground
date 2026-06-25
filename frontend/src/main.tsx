import React from 'react';
import ReactDOM from 'react-dom/client';

// FE01 骨架占位 — FE11 会替换为完整 Provider 树（QueryClientProvider + RouterProvider + AntdApp）
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <h1>boot ok</h1>
  </React.StrictMode>,
);
