import React, { useRef } from 'react';
import Lottie from 'lottie-react';
import assistAnimation from '../../../static/lottie/assist.json';

type KuAiLottieMarkProps = {
  size?: number;
  className?: string;
  /** 悬停时从首帧重播（顶栏入口） */
  hoverPlay?: boolean;
};

/** KU-AI 顶栏同款 Lottie 机器人标识（默认静态首帧，完整耳机与紫圆，不裁切） */
export function KuAiLottieMark({
  size = 54,
  className,
  hoverPlay = false,
}: KuAiLottieMarkProps) {
  const lottieRef = useRef<any>(null);

  const hoverHandlers = hoverPlay
    ? {
        onMouseEnter: () => lottieRef.current?.goToAndPlay?.(0, true),
        onMouseLeave: () => lottieRef.current?.goToAndStop?.(0, true),
      }
    : {};

  return (
    <span
      className={className}
      style={{
        width: size,
        height: size,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        lineHeight: 0,
        flexShrink: 0,
      }}
      {...hoverHandlers}
    >
      <Lottie
        lottieRef={lottieRef}
        animationData={assistAnimation}
        loop={hoverPlay}
        autoplay={false}
        style={{ width: size, height: size, display: 'block' }}
      />
    </span>
  );
}
