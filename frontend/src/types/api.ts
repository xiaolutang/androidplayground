/**
 * 通用 API 响应/错误类型
 */

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
  field_errors?: Record<string, string>;
}

/** 后端返回的 errors 列表项（validation error） */
export interface ApiFieldError {
  loc: string[];
  msg: string;
  type: string;
}
