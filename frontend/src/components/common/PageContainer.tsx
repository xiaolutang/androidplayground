/**
 * PageContainer — 统一页面容器：标题 + loading + error + empty 三态
 *
 * 纯展示组件，数据全部经 props 注入。
 */

import type { ReactNode } from 'react';
import { Skeleton, Result, Empty, Button, Typography } from 'antd';

const { Title } = Typography;

interface PageContainerProps<T> {
  title?: string;
  loading: boolean;
  error: unknown;
  data: T | undefined;
  empty?: (data: T) => boolean;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}

function isEmpty<T>(data: T | undefined, emptyFn?: (data: T) => boolean): boolean {
  if (data === undefined || data === null) return true;
  if (Array.isArray(data) && data.length === 0) return true;
  if (emptyFn) return emptyFn(data);
  return false;
}

export function PageContainer<T>({
  title,
  loading,
  error,
  data,
  empty,
  onRetry,
  children,
}: PageContainerProps<T>) {
  if (loading) {
    return (
      <div>
        {title && <Title level={3}>{title}</Title>}
        <Skeleton active />
      </div>
    );
  }

  if (error) {
    const err = error as { message?: string; status?: number };
    return (
      <Result
        status={err?.status === 404 ? '404' : 'error'}
        title="请求失败"
        subTitle={err?.message ?? '未知错误'}
        extra={
          onRetry && (
            <Button type="primary" onClick={onRetry}>
              重试
            </Button>
          )
        }
      />
    );
  }

  if (isEmpty(data, empty)) {
    return (
      <div>
        {title && <Title level={3}>{title}</Title>}
        <Empty description="暂无数据" />
      </div>
    );
  }

  return (
    <div>
      {title && <Title level={3}>{title}</Title>}
      {children(data as T)}
    </div>
  );
}
