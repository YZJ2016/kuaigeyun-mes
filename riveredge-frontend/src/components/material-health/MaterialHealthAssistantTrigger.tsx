import React, { useEffect, useState } from 'react';

const KUAIAI_MATERIAL_HEALTH = import.meta.glob(
  '../../apps/kuaiai/components/material-health/MaterialHealthAssistant.tsx',
);

export interface MaterialHealthAssistantTriggerProps {
  groupId?: number;
  onOpenMaterial?: (materialUuid: string) => void;
  hideTrigger?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/** 未安装或未组装 kuaiai 时静默不渲染，避免主仓对专业应用产生静态强耦合。 */
export function MaterialHealthAssistantTrigger(
  props: MaterialHealthAssistantTriggerProps,
) {
  const [Inner, setInner] = useState<React.ComponentType<MaterialHealthAssistantTriggerProps> | null>(
    null,
  );

  useEffect(() => {
    const loader = Object.values(KUAIAI_MATERIAL_HEALTH)[0];
    if (!loader) return;
    let active = true;
    void loader().then((mod) => {
      if (!active) return;
      const exported = mod as {
        MaterialHealthAssistantTrigger?: React.ComponentType<MaterialHealthAssistantTriggerProps>;
      };
      if (exported.MaterialHealthAssistantTrigger) {
        setInner(() => exported.MaterialHealthAssistantTrigger ?? null);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  if (!Inner) return null;
  return <Inner {...props} />;
}

export default MaterialHealthAssistantTrigger;
