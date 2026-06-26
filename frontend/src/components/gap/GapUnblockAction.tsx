/**
 * GapUnblockAction — 补齐操作按钮 + 确认弹窗
 *
 * status != waiting → return null
 * status = waiting → Button 触发 Drawer/Form：
 *   - action_taken（必填，默认回填 gap.waiting_reason）
 *   - evidence（必填）
 *
 * 提交 → useUnblockGap().mutate
 * 纯交互组件，不直接 fetch。
 */

import { useState } from 'react';
import { Button, Drawer, Form, Input, message } from 'antd';
import type { CapabilityGap, UnblockRequest } from '@/types/gap';
import { useUnblockGap } from '@/hooks/useGaps';

const { TextArea } = Input;

interface GapUnblockActionProps {
  gap: CapabilityGap;
}

export function GapUnblockAction({ gap }: GapUnblockActionProps) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<UnblockRequest>();
  const [submitting, setSubmitting] = useState(false);
  const mutation = useUnblockGap();

  if (gap.status !== 'waiting') {
    return null;
  }

  const onFinish = async (values: UnblockRequest) => {
    setSubmitting(true);
    try {
      await mutation.mutateAsync({ id: gap.id, body: values });
      message.success('补齐成功');
      form.resetFields();
      setOpen(false);
    } catch (err) {
      const apiErr = err as { message?: string };
      message.error(apiErr?.message ?? '补齐失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>
        补齐
      </Button>
      <Drawer
        title="补齐缺口"
        open={open}
        onClose={() => setOpen(false)}
        width={400}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ action_taken: gap.waiting_reason ?? '' }}
          disabled={submitting}
        >
          <Form.Item
            name="action_taken"
            label="补齐动作"
            rules={[{ required: true, message: '请填写补齐动作' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="evidence"
            label="证据"
            rules={[{ required: true, message: '请填写证据' }]}
          >
            <TextArea rows={3} placeholder="补齐依据/文档链接" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting}>
              提交补齐
            </Button>
          </Form.Item>
        </Form>
      </Drawer>
    </>
  );
}
