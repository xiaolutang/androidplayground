/**
 * App.tsx — 路由表 + 布局（Sider 导航 + Content）
 *
 * 路由（React Router 7 库模式 createBrowserRouter）：
 * - /               → 重定向到 /reports
 * - /reports        → 报告列表
 * - /reports/:id    → 报告详情
 * - /reports/:id/clarify → 追问
 * - /gaps           → 缺口管理
 */

import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  BugOutlined,
  AlertOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { Link, useLocation } from 'react-router-dom';
import type { MenuProps } from 'antd';
import { ReportListPage } from '@/routes/ReportListPage';
import { ReportDetailPage } from '@/routes/ReportDetailPage';
import { GapViewPage } from '@/routes/GapViewPage';
import { ClarifyPage } from '@/routes/ClarifyPage';

const { Sider, Header, Content } = Layout;

const menuItems: MenuProps['items'] = [
  {
    key: '/reports',
    icon: <BugOutlined />,
    label: <Link to="/reports">报告列表</Link>,
  },
  {
    key: '/gaps',
    icon: <AlertOutlined />,
    label: <Link to="/gaps">缺口管理</Link>,
  },
  {
    key: '/clarify',
    icon: <QuestionCircleOutlined />,
    label: '澄清请求',
    disabled: true,
  },
];

function AppLayout() {
  const location = useLocation();

  // 高亮当前菜单项：取路径第一段
  const selectedKey =
    '/' + (location.pathname.split('/')[1] ?? 'reports');

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible breakpoint="lg">
        <div
          style={{
            height: 48,
            margin: 16,
            color: '#fff',
            fontWeight: 700,
            fontSize: 16,
            textAlign: 'center',
            lineHeight: '48px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          Bug Fix Agent
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 18, fontWeight: 600 }}>
            客户端 Bug 修复 Agent
          </span>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/reports" replace /> },
      { path: 'reports', element: <ReportListPage /> },
      { path: 'reports/:id', element: <ReportDetailPage /> },
      { path: 'reports/:id/clarify', element: <ClarifyPage /> },
      { path: 'gaps', element: <GapViewPage /> },
      { path: '*', element: <Navigate to="/reports" replace /> },
    ],
  },
]);
