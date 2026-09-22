import React from 'react';
import { Tooltip } from 'antd';
import { KuAiLottieMark } from '../components/ai-assistant/KuAiLottieMark';

type Props = {
  tooltip: string;
  onClick: () => void;
  /** 深色/彩色顶栏：浅色实心圆底，避免紫黑耳机融进海军蓝 */
  isDarkHeader?: boolean;
};

/** 顶栏 AI 入口：默认静态首帧，悬停时从第 0 帧重播，离开停回首帧 */
export const AiAssistantHeaderButton = React.memo(function AiAssistantHeaderButton({
  tooltip,
  onClick,
  isDarkHeader = false,
}: Props) {
  return (
    <Tooltip title={tooltip}>
      <span className="ai-assistant-lottie-btn-wrapper">
        <span
          role="button"
          tabIndex={0}
          onClick={onClick}
          onKeyDown={(e) => e.key === 'Enter' && onClick()}
          className={
            isDarkHeader ? 'ai-assistant-lottie-btn ai-assistant-lottie-btn--dark-header' : 'ai-assistant-lottie-btn'
          }
        >
          <KuAiLottieMark size={54} hoverPlay />
        </span>
      </span>
    </Tooltip>
  );
});
