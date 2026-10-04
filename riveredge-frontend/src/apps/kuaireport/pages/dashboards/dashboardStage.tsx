import React, { useEffect, useState } from 'react';
import { getFileDownloadUrlWithToken } from '../../../../services/file';
import { DashboardWidgets, FlowBoard, type DashboardWidget } from './DashboardWidgets';

export const CANVAS_WIDTH = 1920;
export const CANVAS_HEIGHT = 1080;

export const DATA_WIDGET_TYPES = new Set(['metric', 'table', 'chart', 'card_list', 'resource_list']);

export type PagePadding = { top: number; right: number; bottom: number; left: number };

export type PageGradient =
  | 'cyanRadial'
  | 'blueWash'
  | 'deepVoid'
  | 'horizonBand'
  | 'cornerBeam'
  | 'top-left'
  | 'top-right'
  | 'center'
  | 'none';

export type PageTexture = 'none' | 'grid' | 'fineGrid' | 'scanlines' | 'noise' | 'dots';

export type PageTheme = {
  background: string;
  gradient: PageGradient;
  image_url: string;
  image_file_uuid: string;
  image_fit: 'cover' | 'contain' | 'fill';
  image_position: 'center' | 'top' | 'bottom' | 'left' | 'right';
  mask_color: string;
  mask_opacity: number;
  texture: PageTexture;
  padding: PagePadding;
};

export const DEFAULT_THEME: PageTheme = {
  background: '#00D4FF',
  gradient: 'top-left',
  image_url: '',
  image_file_uuid: '',
  image_fit: 'cover',
  image_position: 'center',
  mask_color: '#000000',
  mask_opacity: 0,
  texture: 'grid',
  padding: { top: 16, right: 16, bottom: 16, left: 16 },
};

function num(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function parseTheme(raw: unknown): PageTheme {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const pad = obj.padding && typeof obj.padding === 'object' ? (obj.padding as Record<string, unknown>) : {};
  const gradient = obj.gradient;
  const fit = obj.image_fit;
  const position = obj.image_position;
  const texture = obj.texture;
  const gradients: PageGradient[] = [
    'cyanRadial',
    'blueWash',
    'deepVoid',
    'horizonBand',
    'cornerBeam',
    'top-left',
    'top-right',
    'center',
    'none',
  ];
  const textures: PageTexture[] = ['none', 'grid', 'fineGrid', 'scanlines', 'noise', 'dots'];
  return {
    background: typeof obj.background === 'string' && obj.background ? obj.background : DEFAULT_THEME.background,
    gradient: gradients.includes(gradient as PageGradient) ? (gradient as PageGradient) : DEFAULT_THEME.gradient,
    image_url: typeof obj.image_url === 'string' ? obj.image_url : '',
    image_file_uuid: typeof obj.image_file_uuid === 'string' ? obj.image_file_uuid : '',
    image_fit: fit === 'contain' || fit === 'fill' || fit === 'cover' ? fit : 'cover',
    image_position:
      position === 'top' || position === 'bottom' || position === 'left' || position === 'right' || position === 'center'
        ? position
        : 'center',
    mask_color: typeof obj.mask_color === 'string' && obj.mask_color ? obj.mask_color : '#000000',
    mask_opacity: Math.min(100, Math.max(0, num(obj.mask_opacity, 0))),
    texture: textures.includes(texture as PageTexture) ? (texture as PageTexture) : 'grid',
    padding: {
      top: Math.max(0, num(pad.top, DEFAULT_THEME.padding.top)),
      right: Math.max(0, num(pad.right, DEFAULT_THEME.padding.right)),
      bottom: Math.max(0, num(pad.bottom, DEFAULT_THEME.padding.bottom)),
      left: Math.max(0, num(pad.left, DEFAULT_THEME.padding.left)),
    },
  };
}

export function isCanvasLayout(layout: unknown): boolean {
  return Boolean(layout && typeof layout === 'object' && (layout as { mode?: string }).mode === 'canvas');
}

export function isFlowLayout(layout: unknown): boolean {
  return Boolean(layout && typeof layout === 'object' && (layout as { compose?: string }).compose === 'flow');
}

export function contentBox(theme: PageTheme): { width: number; height: number } {
  return {
    width: Math.max(320, CANVAS_WIDTH - theme.padding.left - theme.padding.right),
    height: Math.max(180, CANVAS_HEIGHT - theme.padding.top - theme.padding.bottom),
  };
}

function glowBackground(theme: PageTheme): string {
  const color = theme.background || '#00D4FF';
  const fade = 'rgba(7, 20, 38, 0)';
  const base = '#071426';
  if (theme.gradient === 'none') return base;
  if (theme.gradient === 'blueWash') return `linear-gradient(180deg, ${color} 0%, ${fade} 42%), ${base}`;
  if (theme.gradient === 'horizonBand') return `linear-gradient(0deg, ${color} 0%, ${fade} 38%), ${base}`;
  if (theme.gradient === 'cornerBeam') return `linear-gradient(135deg, ${color} 0%, ${fade} 46%), ${base}`;
  const at =
    theme.gradient === 'top-right' ? '100% 0%' : theme.gradient === 'center' ? '50% 40%' : theme.gradient === 'deepVoid' ? '50% 0%' : '0% 0%';
  return `radial-gradient(circle at ${at}, ${color} 0%, ${fade} 46%), ${base}`;
}

function textureStyle(theme: PageTheme): React.CSSProperties | null {
  if (theme.texture === 'none') return null;
  if (theme.texture === 'dots') {
    return {
      backgroundImage: 'radial-gradient(rgba(255,255,255,0.28) 1px, transparent 1px)',
      backgroundSize: '18px 18px',
    };
  }
  if (theme.texture === 'fineGrid') {
    return {
      backgroundImage:
        'linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)',
      backgroundSize: '16px 16px',
    };
  }
  if (theme.texture === 'scanlines') {
    return { backgroundImage: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.08) 0 1px, transparent 1px 4px)' };
  }
  if (theme.texture === 'noise') {
    return {
      backgroundImage: 'radial-gradient(rgba(255,255,255,0.2) 0.6px, transparent 0.6px)',
      backgroundSize: '3px 3px',
    };
  }
  return {
    backgroundImage:
      'linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)',
    backgroundSize: '40px 40px',
  };
}

export function useThemeImageUrl(theme: PageTheme): string {
  const [url, setUrl] = useState('');
  useEffect(() => {
    const direct = theme.image_url.trim();
    if (/^https?:\/\//i.test(direct)) {
      setUrl(direct);
      return undefined;
    }
    if (!theme.image_file_uuid) {
      setUrl('');
      return undefined;
    }
    let cancelled = false;
    getFileDownloadUrlWithToken(theme.image_file_uuid)
      .then((value) => {
        if (!cancelled) setUrl(value || '');
      })
      .catch(() => {
        if (!cancelled) setUrl('');
      });
    return () => {
      cancelled = true;
    };
  }, [theme.image_url, theme.image_file_uuid]);
  return url;
}

/** 1920×1080 画布。子节点坐标系是扣除页边距后的内容区。 */
export function DashboardStage({
  theme,
  imageUrl,
  scale,
  children,
  onPointerDown,
  onDragOver,
  onDrop,
}: {
  theme: PageTheme;
  imageUrl: string;
  scale: number;
  children?: React.ReactNode;
  onPointerDown?: React.PointerEventHandler<HTMLDivElement>;
  onDragOver?: React.DragEventHandler<HTMLDivElement>;
  onDrop?: React.DragEventHandler<HTMLDivElement>;
}) {
  const box = contentBox(theme);
  const texture = textureStyle(theme);
  const fit = theme.image_fit === 'fill' ? '100% 100%' : theme.image_fit;
  return (
    <div style={{ width: CANVAS_WIDTH * scale, height: CANVAS_HEIGHT * scale, flex: 'none' }}>
      <div
        data-board-stage
        onPointerDown={onPointerDown}
        onDragOver={onDragOver}
        onDrop={onDrop}
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          position: 'relative',
          overflow: 'hidden',
          background: glowBackground(theme),
          boxShadow: '0 0 0 1px rgba(0,0,0,0.25)',
        }}
      >
        {imageUrl ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: `url("${imageUrl.replace(/"/g, '')}")`,
              backgroundSize: fit,
              backgroundPosition: theme.image_position,
              backgroundRepeat: 'no-repeat',
            }}
          />
        ) : null}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: theme.mask_color,
            opacity: theme.mask_opacity / 100,
            pointerEvents: 'none',
          }}
        />
        {texture ? (
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', ...texture }} />
        ) : null}
        <div
          style={{
            position: 'absolute',
            top: theme.padding.top,
            left: theme.padding.left,
            width: box.width,
            height: box.height,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

export function DashboardCanvasFrame({
  theme,
  widgets,
  shareToken,
  flow = false,
}: {
  theme: PageTheme;
  widgets: DashboardWidget[];
  shareToken?: string;
  flow?: boolean;
}) {
  const imageUrl = useThemeImageUrl(theme);
  const hostRef = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const box = contentBox(theme);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const measure = () => {
      const rect = host.getBoundingClientRect();
      const next = Math.min(rect.width / CANVAS_WIDTH, rect.height / CANVAS_HEIGHT);
      setScale(next > 0 ? next : 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={hostRef}
      style={{
        width: '100%',
        height: '100vh',
        background: '#000',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <DashboardStage theme={theme} imageUrl={imageUrl} scale={scale}>
        {flow ? (
          <FlowBoard widgets={widgets} shareToken={shareToken} accent={theme.background} />
        ) : (
          <DashboardWidgets
            widgets={widgets}
            shareToken={shareToken}
            canvas={{ width: box.width, height: box.height }}
            accent={theme.background}
          />
        )}
      </DashboardStage>
    </div>
  );
}
