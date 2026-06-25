/**
 * 统一 fetch 封装 — 全应用唯一 fetch 出口
 *
 * 分层：hooks → services/*Api → apiClient → 后端
 *
 * 错误码映射：
 * - 400 → 参数错误（解析 field_errors）
 * - 404 → 报告/缺口不存在
 * - 409 → 当前状态不允许此操作（状态冲突）
 * - 5xx → 服务器错误（antd message 全局通知）
 * - 网络断开（fetch reject）→ status=0
 */

import { message } from 'antd';
import type { ApiError } from '@/types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

interface ApiClientOptions extends RequestInit {
  params?: Record<string, string | number | undefined>;
}

function buildUrl(path: string, params?: ApiClientOptions['params']): string {
  const base = BASE_URL + path;
  if (!params) return base;

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `${base}?${qs}` : base;
}

function parseFieldErrors(detail: unknown): Record<string, string> | undefined {
  if (!Array.isArray(detail)) return undefined;
  const result: Record<string, string> = {};
  for (const err of detail) {
    if (
      err &&
      typeof err === 'object' &&
      'loc' in err &&
      'msg' in err
    ) {
      const loc = (err as { loc: unknown[] }).loc;
      const lastKey = loc[loc.length - 1];
      if (typeof lastKey === 'string') {
        result[lastKey] = String((err as { msg: unknown }).msg);
      }
    }
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

async function handleError(res: Response): Promise<never> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // 非 JSON 响应
  }

  const status = res.status;
  let apiError: ApiError;

  switch (true) {
    case status === 400: {
      const detail = (body as { detail?: unknown })?.detail;
      apiError = {
        status: 400,
        code: 'BAD_REQUEST',
        message: '参数错误',
        field_errors: parseFieldErrors(detail),
      };
      break;
    }
    case status === 404:
      apiError = {
        status: 404,
        code: 'NOT_FOUND',
        message: '报告/缺口不存在',
      };
      break;
    case status === 409:
      apiError = {
        status: 409,
        code: 'STATE_CONFLICT',
        message: '当前状态不允许此操作',
      };
      break;
    case status >= 500:
      apiError = {
        status,
        code: 'SERVER_ERROR',
        message: '服务器错误，请稍后重试',
      };
      // 5xx 触发 antd message 全局通知
      message.error(apiError.message);
      break;
    default:
      apiError = {
        status,
        code: 'UNKNOWN',
        message: `请求失败 (${status})`,
      };
  }

  throw apiError;
}

export async function apiClient<T>(
  path: string,
  options?: ApiClientOptions,
): Promise<T> {
  const { params, headers, ...rest } = options ?? {};

  let res: Response;
  try {
    res = await fetch(buildUrl(path, params), {
      ...rest,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...headers,
      },
    });
  } catch {
    // 网络断开
    const networkError: ApiError = {
      status: 0,
      code: 'NETWORK_ERROR',
      message: '网络断开，请检查连接',
    };
    message.error(networkError.message);
    throw networkError;
  }

  if (!res.ok) {
    await handleError(res);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
