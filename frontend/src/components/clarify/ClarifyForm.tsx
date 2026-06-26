/**
 * ClarifyForm — 追问候选表单
 *
 * 空 options → antd Empty「暂无可追问项」+ 返回按钮
 * 非空 → antd Form：每个 ClarifyOption 渲染 question + options Radio / Input
 *
 * 提交 → useSubmitClarify(reportId).mutate
 * 成功 → onSubmitted()
 * 纯交互组件，不直接 fetch。
 */

import { useState } from 'react';
import { Form, Input, Button, Empty, message, Typography } from 'antd';
import type { ClarifyOption, ClarifyAnswerItem } from '@/types/report';
import { useSubmitClarify } from '@/hooks/useClarify';

const { Title } = Typography;

interface ClarifyFormProps {
  reportId: string;
  options: ClarifyOption[];
  onSubmitted?: () => void;
}

export function ClarifyForm({
  reportId,
  options,
  onSubmitted,
}: ClarifyFormProps) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const mutation = useSubmitClarify(reportId);

  // 空候选场景
  if (!options || options.length === 0) {
    return (
      <div>
        <Empty description="暂无可追问项" />
        {onSubmitted && (
          <Button onClick={onSubmitted} style={{ marginTop: 16 }}>
            返回报告
          </Button>
        )}
      </div>
    );
  }

  const onFinish = async (values: Record<string, string>) => {
    const answers: ClarifyAnswerItem[] = Object.entries(values)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([optionId, value]) => ({
        option_id: optionId,
        value: String(value),
      }));

    if (answers.length === 0) {
      message.warning('请至少回答一个问题');
      return;
    }

    setSubmitting(true);
    try {
      const result = await mutation.mutateAsync({ answers });
      if (result.accepted) {
        message.success('追问已提交');
        onSubmitted?.();
      } else {
        message.warning('追问未被接受');
      }
    } catch (err) {
      const apiErr = err as { message?: string };
      message.error(apiErr?.message ?? '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <Title level={4}>追问</Title>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        disabled={submitting}
      >
        {options.map((opt) => (
          <Form.Item
            key={opt.id}
            name={opt.id}
            label={opt.question}
            rules={[{ required: true, message: '请填写此项' }]}
          >
            <Input placeholder={opt.context ?? '请输入'} />
          </Form.Item>
        ))}
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            提交追问
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}
