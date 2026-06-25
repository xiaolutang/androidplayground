/**
 * RegressionFeedbackForm — 回归反馈表单
 *
 * 仅在 PR 已提交后阶段显示（allowed 5 态）：
 * pr_open / draft_pr / concluded / reflected / reflowed
 *
 * 其余 9 态隐藏入口（return null）。
 * 纯展示+交互组件，不直接 fetch，数据经 useRegressionFeedback hook。
 */

import { useState } from 'react';
import { Form, Select, Input, Button, message, Card } from 'antd';
import type { BugReportStatus, RegressionFeedbackRequest } from '@/types/report';
import { canShowRegressionFeedback } from '@/utils/format';
import { useRegressionFeedback } from '@/hooks/useRegressionFeedback';

const { TextArea } = Input;

interface RegressionFeedbackFormProps {
  reportId: string;
  status: BugReportStatus;
  onDone?: () => void;
}

export function RegressionFeedbackForm({
  reportId,
  status,
  onDone,
}: RegressionFeedbackFormProps) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const mutation = useRegressionFeedback(reportId);

  // 其余 9 态隐藏入口
  if (!canShowRegressionFeedback(status)) {
    return null;
  }

  const onFinish = async (values: RegressionFeedbackRequest) => {
    setSubmitting(true);
    try {
      const result = await mutation.mutateAsync(values);
      if (result.reflow_scheduled) {
        message.success('回归反馈已提交，已触发回流');
      } else {
        message.success('回归反馈已提交');
      }
      form.resetFields();
      onDone?.();
    } catch (err) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr?.status === 409) {
        message.warning('当前状态不允许此操作');
      } else {
        message.error(apiErr?.message ?? '提交失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card title="回归反馈" size="small">
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        disabled={submitting}
      >
        <Form.Item
          name="outcome"
          label="结果"
          rules={[{ required: true, message: '请选择结果' }]}
        >
          <Select placeholder="选择结果">
            <Select.Option value="regression">回归</Select.Option>
            <Select.Option value="safe">安全</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="evidence"
          label="证据"
          rules={[{ required: true, message: '请填写证据' }]}
        >
          <TextArea rows={3} placeholder="日志/截图/issue 链接" />
        </Form.Item>
        <Form.Item name="bucket_dim" label="分桶维度（可选）">
          <Input placeholder="如：模块/版本" />
        </Form.Item>
        <Form.Item name="bucket_value" label="分桶值（可选）">
          <Input placeholder="如：v1.2.0" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            提交反馈
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
}
