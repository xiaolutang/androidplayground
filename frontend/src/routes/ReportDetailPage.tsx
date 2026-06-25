/**
 * ReportDetailPage — 报告详情页
 *
 * 组合：ReportHeader + HypothesisTree + TrajectoryTimeline + RegressionFeedbackForm
 * 数据通过 useReport + useTrajectory hooks 获取，不直接调 apiClient。
 */

import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Card, Divider, Typography } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useReport, useTrajectory } from '@/hooks/useReport';
import { PageContainer } from '@/components/common/PageContainer';
import { ReportHeader } from '@/components/report/ReportHeader';
import { HypothesisTree } from '@/components/report/HypothesisTree';
import { TrajectoryTimeline } from '@/components/report/TrajectoryTimeline';
import { RegressionFeedbackForm } from '@/components/report/RegressionFeedbackForm';
import { buildTreeFromTrajectory } from '@/utils/treeBuilder';

const { Title } = Typography;

export function ReportDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
    refetch: refetchReport,
  } = useReport(id);

  const {
    data: trajectory,
    isLoading: trajLoading,
    error: trajError,
  } = useTrajectory(id);

  // 从 trajectory 构建 hypothesis 树用于 HypothesisTree 组件
  const hypotheses = trajectory
    ? buildTreeFromTrajectory(trajectory.nodes, trajectory.edges).map((n) => n.hypothesis)
    : [];

  return (
    <div>
      <PageContainer
        loading={reportLoading}
        error={reportError}
        data={report}
        onRetry={() => refetchReport()}
      >
        {(r) => (
          <Space direction="vertical" style={{ width: '100%' }}>
            <ReportHeader report={r} />

            {r.pr_url && (
              <div>
                <Button
                  type="link"
                  href={r.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  icon={<QuestionCircleOutlined />}
                >
                  查看 PR
                </Button>
              </div>
            )}

            {/* 追问入口 */}
            <Button
              onClick={() => navigate(`/reports/${id}/clarify`)}
            >
              追问
            </Button>

            <Divider />

            {/* 假设树 */}
            <Card title="假设树" size="small">
              {trajLoading ? (
                <div style={{ color: '#999' }}>加载中...</div>
              ) : trajError ? (
                <div style={{ color: '#999' }}>暂无假设数据</div>
              ) : (
                <HypothesisTree hypotheses={hypotheses} />
              )}
            </Card>

            {/* 轨迹时间线 */}
            {trajectory && trajectory.nodes.length > 0 && (
              <Card title="轨迹时间线" size="small">
                <TrajectoryTimeline
                  nodes={trajectory.nodes}
                  edges={trajectory.edges}
                />
              </Card>
            )}

            {/* 回归反馈表单（仅 allowed 5 态显示） */}
            <RegressionFeedbackForm
              reportId={id}
              status={r.status}
              onDone={() => refetchReport()}
            />
          </Space>
        )}
      </PageContainer>
    </div>
  );
}
