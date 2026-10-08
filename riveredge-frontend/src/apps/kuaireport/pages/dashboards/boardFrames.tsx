import React, { useLayoutEffect, useRef, useState } from 'react';
import { FullscreenExitOutlined, FullscreenOutlined } from '@ant-design/icons';

export type FrameVariant = 'bevel' | 'bracket' | 'rail' | 'module' | 'blade';

const VARIANTS: FrameVariant[] = ['bevel', 'bracket', 'rail', 'module', 'blade'];
const STEP = 4;
const GAP = 12;
const INKS = [2, 3, 4];
const SQUARE = 8;

type Arm = { ratio: number; min: number; max: number };
type Cell = { width: number; height: number; gap: number };
type Band = { seg: number; gap: number; height: number };
type Hatch = { count: number; length: number; gap: number; thickness: number };
type Metrics = {
  cut: number;
  arm: Arm;
  armCross: number;
  armWidth: number;
  ringInset: number;
  cap: number;
  rule: number;
  cell: Cell;
  band: Band;
  bladeRun: Arm;
  bladeSlope: number;
  hatch: Hatch;
};

const REGULAR: Metrics = {
  cut: 16,
  arm: { ratio: 0.18, min: 64, max: 160 },
  armCross: 16,
  armWidth: 4,
  ringInset: 8,
  cap: 16,
  rule: 4,
  cell: { width: 32, height: 20, gap: 8 },
  band: { seg: 64, gap: 16, height: 8 },
  bladeRun: { ratio: 0.09, min: 20, max: 48 },
  bladeSlope: 2,
  hatch: { count: 3, length: 28, gap: 8, thickness: 8 },
};
const PANEL: Metrics = {
  cut: 24,
  arm: { ratio: 0.18, min: 64, max: 160 },
  armCross: 24,
  armWidth: 8,
  ringInset: 16,
  cap: 24,
  rule: 8,
  cell: { width: 32, height: 20, gap: 8 },
  band: { seg: 64, gap: 16, height: 12 },
  bladeRun: { ratio: 0.09, min: 20, max: 48 },
  bladeSlope: 2,
  hatch: { count: 2, length: 16, gap: 8, thickness: 8 },
};
const CARD: Metrics = {
  cut: 16,
  arm: { ratio: 0.18, min: 40, max: 96 },
  armCross: 16,
  armWidth: 4,
  ringInset: 12,
  cap: 16,
  rule: 4,
  cell: { width: 24, height: 12, gap: 8 },
  band: { seg: 32, gap: 8, height: 6 },
  bladeRun: { ratio: 0.12, min: 16, max: 32 },
  bladeSlope: 2,
  hatch: { count: 3, length: 20, gap: 8, thickness: 8 },
};
const COMPACT: Metrics = {
  cut: 8,
  arm: { ratio: 0.18, min: 24, max: 64 },
  armCross: 8,
  armWidth: 2,
  ringInset: 4,
  cap: 8,
  rule: 2,
  cell: { width: 16, height: 8, gap: 8 },
  band: { seg: 16, gap: 8, height: 4 },
  bladeRun: { ratio: 0.2, min: 8, max: 16 },
  bladeSlope: 2,
  hatch: { count: 2, length: 16, gap: 4, thickness: 4 },
};

const METRICS: Record<string, Metrics> = { regular: REGULAR, panel: PANEL, card: CARD, compact: COMPACT };

type Corner = 'tl' | 'tr' | 'br' | 'bl';
type Ink = { d: string; ink: number };
type Pad = { top: number; right: number; bottom: number; left: number };
type Body = { d: string; stroked: boolean };
type Plate = { d: string; stroked: boolean };

function variantOf(value: unknown, fallback: FrameVariant = 'bevel'): FrameVariant {
  return typeof value === 'string' && VARIANTS.includes(value as FrameVariant) ? (value as FrameVariant) : fallback;
}

function metrics(scale: string): Metrics {
  return METRICS[scale] || REGULAR;
}

function scaled(spec: Arm, size: number): number {
  const next = Math.round((size * spec.ratio) / STEP) * STEP;
  return Math.min(spec.max, Math.max(spec.min, next));
}

function cutPath(width: number, height: number, cuts: { tl?: number; tr?: number; br?: number; bl?: number }, inset = 0): string {
  const left = inset;
  const top = inset;
  const right = width - inset;
  const bottom = height - inset;
  const tl = cuts.tl ?? 0;
  const tr = cuts.tr ?? 0;
  const br = cuts.br ?? 0;
  const bl = cuts.bl ?? 0;
  return [
    `M ${left + tl} ${top}`,
    `L ${right - tr} ${top}`,
    tr ? `L ${right} ${top + tr}` : '',
    `L ${right} ${bottom - br}`,
    br ? `L ${right - br} ${bottom}` : '',
    `L ${left + bl} ${bottom}`,
    bl ? `L ${left} ${bottom - bl}` : '',
    `L ${left} ${top + tl}`,
    'Z',
  ]
    .filter(Boolean)
    .join(' ');
}

function rect(x: number, y: number, width: number, height: number): string {
  return `M ${x} ${y} L ${x + width} ${y} L ${x + width} ${y + height} L ${x} ${y + height} Z`;
}

function chevron(x: number, y: number, length: number, thickness: number, cut: number, dir: number): string {
  return [
    `M ${x + dir * cut} ${y}`,
    `L ${x + dir * length} ${y}`,
    `L ${x + dir * length} ${y + thickness}`,
    `L ${x + dir * cut} ${y + thickness}`,
    `L ${x} ${y + thickness - cut}`,
    `L ${x} ${y + cut}`,
    'Z',
  ].join(' ');
}

function cornerFold(width: number, height: number, corner: Corner, size: number, inset = 0): string {
  const x = corner === 'tl' || corner === 'bl' ? inset : width - inset;
  const y = corner === 'tl' || corner === 'tr' ? inset : height - inset;
  const sx = corner === 'tl' || corner === 'bl' ? 1 : -1;
  const sy = corner === 'tl' || corner === 'tr' ? 1 : -1;
  return [`M ${x} ${y + sy * size}`, `L ${x + sx * size} ${y}`, `L ${x + sx * size * 2} ${y}`, `L ${x} ${y + sy * size * 2}`, 'Z'].join(' ');
}

function cornerArm(width: number, height: number, corner: Corner, arm: number, cross: number, thick: number, inset = 0): string {
  const x = corner === 'tl' || corner === 'bl' ? inset : width - inset;
  const y = corner === 'tl' || corner === 'tr' ? inset : height - inset;
  const sx = corner === 'tl' || corner === 'bl' ? 1 : -1;
  const sy = corner === 'tl' || corner === 'tr' ? 1 : -1;
  return [
    `M ${x} ${y}`,
    `L ${x + sx * arm} ${y}`,
    `L ${x + sx * arm} ${y + sy * cross}`,
    `L ${x + sx * thick} ${y + sy * cross}`,
    `L ${x + sx * thick} ${y + sy * arm}`,
    `L ${x} ${y + sy * arm}`,
    'Z',
  ].join(' ');
}

function ring(width: number, height: number, inset: number, thick: number): string {
  const left = inset;
  const top = inset;
  const right = width - inset;
  const bottom = height - inset;
  return [
    `M ${left} ${top}`,
    `L ${right} ${top}`,
    `L ${right} ${bottom}`,
    `L ${left} ${bottom}`,
    'Z',
    `M ${left + thick} ${top + thick}`,
    `L ${left + thick} ${bottom - thick}`,
    `L ${right - thick} ${bottom - thick}`,
    `L ${right - thick} ${top + thick}`,
    'Z',
  ].join(' ');
}

function cells(spec: { x: number; y: number; width: number; height: number; gap: number; count: number; dir: number }): string[] {
  const paths: string[] = [];
  for (let index = 0; index < spec.count; index += 1) {
    const offset = index * (spec.width + spec.gap);
    const x = spec.dir === 1 ? spec.x + offset : spec.x - offset - spec.width;
    paths.push(rect(x, spec.y, spec.width, spec.height));
  }
  return paths;
}

function bandSegments(spec: { x: number; y: number; width: number; height: number; seg: number; gap: number }): { d: string; distance: number }[] {
  const step = spec.seg + spec.gap;
  const count = Math.max(1, Math.floor((spec.width + spec.gap) / step));
  const used = count * spec.seg + (count - 1) * spec.gap;
  const x = spec.x + Math.round((spec.width - used) / (STEP * 2)) * STEP * 2;
  const mid = (count - 1) / 2;
  const items: { d: string; distance: number }[] = [];
  for (let index = 0; index < count; index += 1) {
    items.push({ d: rect(x + index * step, spec.y, spec.seg, spec.height), distance: Math.round(Math.abs(index - mid)) });
  }
  return items;
}

function bladeBody(width: number, height: number, run: number, slope: number, inset = 0): string {
  const left = inset;
  const top = inset;
  const right = width - inset;
  const bottom = height - inset;
  const rise = Math.min(slope * run, height - inset * 2);
  return [
    `M ${left + run} ${top}`,
    `L ${right} ${top}`,
    `L ${right} ${bottom - rise}`,
    `L ${right - run} ${bottom}`,
    `L ${left} ${bottom}`,
    `L ${left} ${top + rise}`,
    'Z',
  ].join(' ');
}

function hatchMarks(x: number, y: number, dir: number, hatch: Hatch): string[] {
  const marks: string[] = [];
  for (let index = 0; index < hatch.count; index += 1) {
    const length = hatch.length - index * STEP;
    const start = x + dir * index * (hatch.thickness + hatch.gap);
    const end = start + dir * length;
    const bottom = y + length;
    marks.push(
      [`M ${start} ${y}`, `L ${end} ${bottom}`, `L ${end - dir * hatch.thickness} ${bottom}`, `L ${start - dir * hatch.thickness} ${y}`, 'Z'].join(' '),
    );
  }
  return marks;
}

function cornerSquare(width: number, height: number, size: number, inset = 0): string {
  return rect(width - inset - size - SQUARE, height - inset - SQUARE, SQUARE, SQUARE);
}

function hexChannels(color: string): { r: number; g: number; b: number } | null {
  const raw = color.replace('#', '').trim();
  const hex = raw.length === 3 ? raw.split('').map((part) => part + part).join('') : raw;
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return null;
  return { r: parseInt(hex.slice(0, 2), 16), g: parseInt(hex.slice(2, 4), 16), b: parseInt(hex.slice(4, 6), 16) };
}

function mix(color: string, alpha: number, fallback: string): string {
  const rgb = hexChannels(color);
  return rgb ? `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})` : fallback;
}

function tint(color: string, toward: { r: number; g: number; b: number }, percent: number, fallback: string): string {
  const rgb = hexChannels(color);
  if (!rgb) return fallback;
  const ratio = percent / 100;
  const channel = (from: number, to: number) => Math.round(from * ratio + to * (1 - ratio));
  return `rgb(${channel(rgb.r, toward.r)}, ${channel(rgb.g, toward.g)}, ${channel(rgb.b, toward.b)})`;
}

export function accentStyle(color: string | undefined): React.CSSProperties {
  const accent = color && hexChannels(color) ? color : '#00d4ff';
  const style: Record<string, string> = { '--kb-accent': accent };
  for (const stop of [10, 12, 14, 15, 16, 18, 22, 28, 32, 35, 40, 45, 55]) {
    style[`--kb-accent-${stop}`] = mix(accent, stop / 100, `rgba(0, 212, 255, ${stop / 100})`);
  }
  style['--kb-accent-tag-text'] = tint(accent, { r: 255, g: 255, b: 255 }, 85, '#d4f4ff');
  style['--kb-accent-glow'] = mix(accent, 0.35, 'rgba(0, 212, 255, 0.35)');
  style['--kb-accent-on-white-12'] = tint(accent, { r: 255, g: 255, b: 255 }, 12, '#e6f4ff');
  style['--kb-accent-bar-start'] = mix(accent, 0.55, 'rgba(0, 212, 255, 0.55)');
  return style as React.CSSProperties;
}

function useMeasure<T extends HTMLElement = HTMLDivElement>(initial: { w: number; h: number }) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState(initial);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const apply = (width: number, height: number) => {
      if (width > 0 && height > 0) {
        setSize((current) => (current.w === width && current.h === height ? current : { w: width, h: height }));
      }
    };
    apply(node.clientWidth, node.clientHeight);
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.borderBoxSize?.[0];
      if (box) apply(Math.round(box.inlineSize), Math.round(box.blockSize));
      else apply(node.clientWidth, node.clientHeight);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, size };
}

function FrameSvg({
  id,
  width,
  height,
  body,
  decor,
  extra,
  className,
}: {
  id: string;
  width: number;
  height: number;
  body: Body;
  decor: Ink[];
  extra?: Ink[];
  className: string;
}) {
  const accent = 'var(--kb-accent, #00d4ff)';
  return (
    <svg className={`${className}-svg`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={accent} stopOpacity={className.includes('panel') ? 0.16 : 0.3} />
          <stop offset="100%" stopColor={accent} stopOpacity={className.includes('panel') ? 0.04 : 0.06} />
        </linearGradient>
      </defs>
      <path className={`${className}-body`} d={body.d} fill={`url(#${id})`} stroke={body.stroked ? accent : 'none'} strokeWidth={body.stroked ? 1 : 0} />
      {decor.map((item, index) => (
        <path key={index} className={`kb-ink kb-ink--${item.ink}`} d={item.d} />
      ))}
      {(extra || []).map((item, index) => (
        <path key={`x${index}`} className={`kb-ink kb-ink--${item.ink}`} d={item.d} />
      ))}
    </svg>
  );
}

const BUTTON_H = 40;
const BUTTON_PAD = 44;

function buttonShape(kind: FrameVariant, width: number): { body: Body; decor: Ink[] } {
  const span = Math.max(112, Math.round(width));
  if (kind === 'bracket') {
    const spec = metrics('compact');
    const arm = scaled(spec.arm, BUTTON_H);
    return {
      body: { d: cutPath(span, BUTTON_H, {}), stroked: false },
      decor: [
        { d: ring(span, BUTTON_H, spec.ringInset, 1), ink: 4 },
        ...(['tl', 'tr', 'br', 'bl'] as Corner[]).map((corner) => ({
          d: cornerArm(span, BUTTON_H, corner, arm, spec.armCross, spec.armWidth),
          ink: 2,
        })),
      ],
    };
  }
  if (kind === 'rail') {
    const spec = metrics('compact');
    return {
      body: { d: rect(spec.cap, spec.rule, span - spec.cap * 2, BUTTON_H - spec.rule * 2), stroked: false },
      decor: [
        { d: rect(0, 0, span, spec.rule), ink: 3 },
        { d: rect(0, BUTTON_H - spec.rule, span, spec.rule), ink: 2 },
        { d: rect(0, 0, spec.cap, BUTTON_H), ink: 2 },
        { d: rect(span - spec.cap, 0, spec.cap, BUTTON_H), ink: 2 },
      ],
    };
  }
  if (kind === 'module') {
    const spec = metrics('compact');
    const y = (BUTTON_H - spec.cell.height) / 2;
    const inner = BUTTON_PAD - 12 - STEP;
    return {
      body: { d: cutPath(span, BUTTON_H, {}), stroked: true },
      decor: [
        ...cells({ ...spec.cell, y, count: 1, x: 8, dir: 1 }).map((d) => ({ d, ink: 2 })),
        ...cells({ ...spec.cell, y, count: 1, x: span - 8, dir: -1 }).map((d) => ({ d, ink: 2 })),
        { d: rect(inner, 0, 2, BUTTON_H), ink: 4 },
        { d: rect(span - inner - 2, 0, 2, BUTTON_H), ink: 4 },
      ],
    };
  }
  if (kind === 'blade') {
    const spec = metrics('compact');
    const run = scaled(spec.bladeRun, BUTTON_H);
    const y = (BUTTON_H - spec.hatch.length) / 2;
    const marks = [BUTTON_PAD - 12 - spec.hatch.length, span - BUTTON_PAD + 12].flatMap((x) =>
      hatchMarks(x, y, 1, spec.hatch).map((d, index) => ({ d, ink: INKS[index] || 4 })),
    );
    return { body: { d: bladeBody(span, BUTTON_H, run, spec.bladeSlope), stroked: true }, decor: marks };
  }
  const cut = metrics('compact').cut;
  const length = BUTTON_PAD - 12 - cut - 4;
  const y = (BUTTON_H - 16) / 2;
  return {
    body: { d: cutPath(span, BUTTON_H, { tl: cut, tr: cut, br: cut, bl: cut }), stroked: true },
    decor: [
      { d: chevron(cut + 4, y, length, 16, cut / 2, 1), ink: 2 },
      { d: chevron(span - cut - 4, y, length, 16, cut / 2, -1), ink: 2 },
    ],
  };
}

export function BoardButton({
  label,
  variant,
  active,
  disabled,
  onClick,
}: {
  label: string;
  variant?: unknown;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const reactId = React.useId().replace(/:/g, '');
  const { ref, size } = useMeasure<HTMLButtonElement>({ w: 140, h: BUTTON_H });
  const shape = buttonShape(variantOf(variant), size.w);
  return (
    <button
      ref={ref}
      type="button"
      className={['kb-board-button', active ? 'is-active' : '', disabled ? 'is-readonly' : ''].filter(Boolean).join(' ')}
      style={{ padding: `0 ${BUTTON_PAD}px`, height: BUTTON_H }}
      aria-label={label}
      onClick={disabled ? undefined : onClick}
    >
      <FrameSvg id={`kb-board-button-${reactId}`} width={size.w} height={BUTTON_H} body={shape.body} decor={shape.decor} className="kb-board-button" />
      <span className="kb-board-button-label">
        {active ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
        <span>{label}</span>
      </span>
    </button>
  );
}

const TITLE_W = 720;
const TITLE_H = 52;
const PLATE_H = 44;
const TITLE_MID = TITLE_W / 2;
const TITLE_BAND = 120;
const TITLE_DROP = TITLE_H - PLATE_H;

function titlePlate(kind: FrameVariant): { plate: Plate; decor: Ink[]; band: string } {
  const side = 16;
  const wing = 112;
  const pair = (draw: (x: number, dir: number) => string, ink: number): Ink[] => [
    { d: draw(side, 1), ink },
    { d: draw(TITLE_W - side, -1), ink },
  ];
  if (kind === 'bracket') {
    const spec = metrics('regular');
    const arm = scaled(spec.arm, PLATE_H);
    const thick = spec.armWidth;
    return {
      plate: { d: cutPath(TITLE_W, PLATE_H, {}), stroked: false },
      decor: [
        { d: ring(TITLE_W, PLATE_H, spec.ringInset, 1), ink: 4 },
        ...(['tl', 'tr', 'br', 'bl'] as Corner[]).map((corner) => ({
          d: cornerArm(TITLE_W, PLATE_H, corner, arm, spec.armCross, spec.armWidth),
          ink: 2,
        })),
      ],
      band: [
        `M ${TITLE_MID - TITLE_BAND} ${PLATE_H}`,
        `L ${TITLE_MID - TITLE_BAND} ${TITLE_H}`,
        `L ${TITLE_MID - TITLE_BAND + thick} ${TITLE_H}`,
        `L ${TITLE_MID - TITLE_BAND + thick} ${PLATE_H + thick}`,
        `L ${TITLE_MID + TITLE_BAND - thick} ${PLATE_H + thick}`,
        `L ${TITLE_MID + TITLE_BAND - thick} ${TITLE_H}`,
        `L ${TITLE_MID + TITLE_BAND} ${TITLE_H}`,
        `L ${TITLE_MID + TITLE_BAND} ${PLATE_H}`,
        'Z',
      ].join(' '),
    };
  }
  if (kind === 'rail') {
    const spec = metrics('regular');
    const cap = 40;
    return {
      plate: { d: rect(spec.cap, spec.rule, TITLE_W - spec.cap * 2, PLATE_H - spec.rule * 2), stroked: false },
      decor: [
        { d: rect(0, 0, TITLE_W, spec.rule), ink: 3 },
        { d: rect(0, PLATE_H - spec.rule, TITLE_W, spec.rule), ink: 2 },
        { d: rect(0, 0, spec.cap, PLATE_H), ink: 2 },
        { d: rect(TITLE_W - spec.cap, 0, spec.cap, PLATE_H), ink: 2 },
        ...pair((x, dir) => rect(dir === 1 ? x + 8 : x - 8 - cap, 14, cap, 2), 3),
        ...pair((x, dir) => rect(dir === 1 ? x + 8 : x - 8 - cap + 12, 26, cap - 12, 2), 4),
      ],
      band: [rect(TITLE_MID - TITLE_BAND, PLATE_H, TITLE_BAND * 2, TITLE_DROP), rect(TITLE_MID - TITLE_BAND - spec.cap, PLATE_H, spec.cap, TITLE_DROP), rect(TITLE_MID + TITLE_BAND, PLATE_H, spec.cap, TITLE_DROP)].join(' '),
    };
  }
  if (kind === 'module') {
    const spec = metrics('regular');
    const y = (PLATE_H - spec.cell.height) / 2;
    const edge = side + wing + 16;
    const row = { y, count: 3, ...spec.cell };
    return {
      plate: { d: cutPath(TITLE_W, PLATE_H, {}), stroked: true },
      decor: [
        ...cells({ ...row, x: side, dir: 1 }).map((d, index) => ({ d, ink: INKS[INKS.length - 1 - index] || 2 })),
        ...cells({ ...row, x: TITLE_W - side, dir: -1 }).map((d, index) => ({ d, ink: INKS[INKS.length - 1 - index] || 2 })),
        { d: rect(edge, 0, 2, PLATE_H), ink: 3 },
        { d: rect(TITLE_W - edge - 2, 0, 2, PLATE_H), ink: 3 },
      ],
      band: [rect(TITLE_MID - TITLE_BAND, PLATE_H, 64, TITLE_DROP), rect(TITLE_MID - 40, PLATE_H, 80, TITLE_DROP), rect(TITLE_MID + 56, PLATE_H, 64, TITLE_DROP)].join(' '),
    };
  }
  if (kind === 'blade') {
    const spec = metrics('regular');
    const run = scaled(spec.bladeRun, PLATE_H);
    const decor: Ink[] = [];
    [side + 24, TITLE_W - side - wing + 24].forEach((x) => {
      hatchMarks(x, 8, 1, spec.hatch).forEach((d, index) => decor.push({ d, ink: INKS[index] || 4 }));
    });
    return {
      plate: { d: bladeBody(TITLE_W, PLATE_H, run, spec.bladeSlope), stroked: true },
      decor,
      band: [`M ${TITLE_MID - TITLE_BAND + TITLE_DROP} ${PLATE_H}`, `L ${TITLE_MID + TITLE_BAND + TITLE_DROP} ${PLATE_H}`, `L ${TITLE_MID + TITLE_BAND} ${TITLE_H}`, `L ${TITLE_MID - TITLE_BAND} ${TITLE_H}`, 'Z'].join(' '),
    };
  }
  const cut = metrics('regular').cut;
  const y = (PLATE_H - 16) / 2;
  return {
    plate: { d: cutPath(TITLE_W, PLATE_H, { tl: cut, tr: cut, br: cut, bl: cut }), stroked: true },
    decor: [
      ...pair((x, dir) => chevron(x, y, wing, 16, cut / 2, dir), 2),
      ...pair((x, dir) => rect(dir === 1 ? x : x - wing + 24, y + 16 + 8, wing - 24, 2), 3),
    ],
    band: [`M ${TITLE_MID - TITLE_BAND} ${PLATE_H}`, `L ${TITLE_MID + TITLE_BAND} ${PLATE_H}`, `L ${TITLE_MID + TITLE_BAND - TITLE_DROP} ${TITLE_H}`, `L ${TITLE_MID - TITLE_BAND + TITLE_DROP} ${TITLE_H}`, 'Z'].join(' '),
  };
}

export function BoardTitle({
  title,
  subtitle,
  variant,
  animate = true,
}: {
  title: string;
  subtitle?: string;
  variant?: unknown;
  animate?: boolean;
}) {
  const reactId = React.useId().replace(/:/g, '');
  const plate = titlePlate(variantOf(variant));
  const accent = 'var(--kb-accent, #00d4ff)';
  const core = rect(TITLE_MID - 32, PLATE_H, 64, TITLE_DROP);
  return (
    <div className="kb-board-title-root">
      <div className={`kb-board-title${animate ? ' is-animated' : ''}`} style={{ width: `min(${TITLE_W}px, 100%)` }}>
        <svg className="kb-board-title-svg" viewBox={`0 0 ${TITLE_W} ${TITLE_H}`} preserveAspectRatio="none" aria-hidden>
          <defs>
            <linearGradient id={`kb-board-title-${reactId}`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor={accent} stopOpacity={0.3} />
              <stop offset="100%" stopColor={accent} stopOpacity={0.06} />
            </linearGradient>
          </defs>
          <path className="kb-board-title-plate" d={plate.plate.d} fill={`url(#kb-board-title-${reactId})`} stroke={plate.plate.stroked ? accent : 'none'} strokeWidth={plate.plate.stroked ? 1 : 0} />
          <g className="kb-board-title-decor">
            {plate.decor.map((item, index) => (
              <path key={index} className={`kb-ink kb-ink--${item.ink}`} d={item.d} />
            ))}
          </g>
          <path className="kb-ink kb-ink--2" d={plate.band} />
          <path className="kb-ink kb-ink--1" d={core} />
        </svg>
        <div className="kb-board-title-text">{title}</div>
      </div>
      {subtitle ? <div className="kb-board-title-sub">{subtitle}</div> : null}
    </div>
  );
}

const PANEL_INSET = 4;
const PANEL_TITLE_H = 32;
const PANEL_TITLE_TOP = 16;
const PANEL_TITLE_BOTTOM = PANEL_TITLE_TOP + PANEL_TITLE_H;

function titleBox(width: number, x: number) {
  return { titleX: x, titleWidth: Math.max(80, width - x - GAP), titleY: PANEL_TITLE_TOP };
}

function titleSpan(width: number): number {
  return Math.min(Math.max(Math.round((width * 0.34) / STEP) * STEP, 120), 280);
}

function groupBands(items: { d: string; distance: number }[]): Ink[] {
  const mid = Math.round((items.length - 1) / 2);
  const groups = new Map<number, string[]>();
  items.forEach((item, index) => {
    if (index === mid) return;
    const ink = INKS[Math.min(item.distance, INKS.length - 1)];
    groups.set(ink, [...(groups.get(ink) || []), item.d]);
  });
  return [...groups.entries()].map(([ink, paths]) => ({ d: paths.join(' '), ink }));
}

function panelShapeResolved(kind: FrameVariant, w: number, h: number, titled: boolean) {
  if (kind === 'rail') {
    const spec = metrics('panel');
    const span = titleSpan(w);
    const top = PANEL_INSET;
    const bottom = h - PANEL_INSET - spec.rule;
    const innerH = Math.max(0, bottom - top - spec.rule);
    const innerW = w - PANEL_INSET * 2;
    return {
      body: { d: rect(PANEL_INSET, top + spec.rule, innerW, innerH), stroked: false },
      decor: [
        { d: rect(PANEL_INSET, top, innerW, spec.rule), ink: 3 },
        { d: rect(PANEL_INSET, bottom, innerW, spec.rule), ink: 2 },
        { d: rect(PANEL_INSET, bottom - STEP - spec.rule / 2, innerW, spec.rule / 2), ink: 4 },
        { d: rect(PANEL_INSET, top + spec.rule, 1, innerH), ink: 3 },
        { d: rect(w - PANEL_INSET - 1, top + spec.rule, 1, innerH), ink: 3 },
        { d: rect(PANEL_INSET, top + spec.rule, spec.cap, spec.cap), ink: 2 },
        { d: rect(w - PANEL_INSET - spec.cap, bottom - spec.cap, spec.cap, spec.cap), ink: 1 },
      ],
      titleBand: titled
        ? [
            { d: rect(0, PANEL_TITLE_BOTTOM - spec.rule, span, spec.rule), ink: 2 },
            { d: rect(span, PANEL_TITLE_BOTTOM - spec.rule, spec.cap, spec.rule), ink: 4 },
          ]
        : [],
      ...titleBox(span, spec.cap + GAP + STEP),
      pad: { top: titled ? PANEL_TITLE_BOTTOM + GAP : spec.rule + 12, right: spec.cap + 12, bottom: spec.rule + 12, left: spec.cap + 12 },
    };
  }
  if (kind === 'module') {
    const spec = metrics('panel');
    const span = titleSpan(w);
    const cellY = Math.round((PANEL_TITLE_H - spec.cell.height) / 2 / STEP) * STEP;
    const segments = bandSegments({
      x: PANEL_INSET + spec.band.gap,
      y: h - spec.band.height - PANEL_INSET,
      width: w - (PANEL_INSET + spec.band.gap) * 2,
      height: spec.band.height,
      seg: spec.band.seg,
      gap: spec.band.gap,
    });
    const mid = Math.round((segments.length - 1) / 2);
    const titleX = 12 + spec.cell.width + GAP;
    return {
      body: { d: cutPath(w, h, {}, PANEL_INSET), stroked: true },
      decor: [...groupBands(segments), { d: segments[mid].d, ink: 1 }],
      titleBand: titled
        ? [
            { d: cells({ ...spec.cell, y: PANEL_TITLE_TOP + cellY, count: 1, x: 12, dir: 1 })[0], ink: 2 },
            { d: rect(0, PANEL_TITLE_BOTTOM - 2, w, 2), ink: 4 },
            { d: rect(span + spec.cell.width + GAP, PANEL_TITLE_TOP, 2, PANEL_TITLE_H), ink: 4 },
          ]
        : [],
      ...titleBox(span + spec.cell.width + GAP, titleX),
      pad: { top: titled ? PANEL_TITLE_BOTTOM + GAP : 16, right: 16, bottom: spec.band.height + 12, left: 16 },
    };
  }
  if (kind === 'blade') {
    const spec = metrics('panel');
    const run = scaled(spec.bladeRun, Math.min(w, h));
    const rise = run * spec.bladeSlope;
    const span = titleSpan(w);
    const tip = PANEL_TITLE_H / spec.bladeSlope;
    return {
      body: { d: bladeBody(w, h, run, spec.bladeSlope, PANEL_INSET), stroked: true },
      decor: [
        ...hatchMarks(w - PANEL_INSET - spec.hatch.thickness * 2, h - PANEL_INSET - rise + spec.hatch.thickness, -1, spec.hatch).map((d, index) => ({
          d,
          ink: INKS[index] || 4,
        })),
        { d: cornerSquare(w, h, run + 8, PANEL_INSET), ink: 1 },
      ],
      titleBand: titled
        ? [
            { d: [`M ${tip} ${PANEL_TITLE_TOP}`, `L ${span} ${PANEL_TITLE_TOP}`, `L ${span - tip} ${PANEL_TITLE_BOTTOM}`, `L 0 ${PANEL_TITLE_BOTTOM}`, 'Z'].join(' '), ink: 4 },
            { d: rect(0, PANEL_TITLE_BOTTOM - 2, span - tip, 2), ink: 3 },
          ]
        : [],
      ...titleBox(span, tip + GAP + STEP),
      pad: { top: titled ? PANEL_TITLE_BOTTOM + GAP : GAP, right: run + 12, bottom: GAP, left: run + 12 },
    };
  }
  const cut = metrics('panel').cut;
  const span = titleSpan(w);
  const notch = Math.min(cut, PANEL_TITLE_H / 2);
  return {
    body: { d: cutPath(w, h, { tl: cut, tr: cut, br: cut, bl: cut }, PANEL_INSET), stroked: true },
    decor: [
      { d: cornerFold(w, h, 'tl', cut, PANEL_INSET), ink: 2 },
      { d: cornerFold(w, h, 'br', cut, PANEL_INSET), ink: 1 },
    ],
    titleBand: titled
      ? [
          {
            d: [`M ${notch} ${PANEL_TITLE_TOP}`, `L ${span} ${PANEL_TITLE_TOP}`, `L ${span} ${PANEL_TITLE_BOTTOM - notch}`, `L ${span - notch} ${PANEL_TITLE_BOTTOM}`, `L ${notch} ${PANEL_TITLE_BOTTOM}`, `L 0 ${PANEL_TITLE_BOTTOM - notch}`, `L 0 ${PANEL_TITLE_TOP + notch}`, 'Z'].join(' '),
            ink: 4,
          },
          { d: rect(notch, PANEL_TITLE_BOTTOM - 2, span - notch * 2, 2), ink: 3 },
        ]
      : [],
    ...titleBox(span, PANEL_INSET + cut * 2 + GAP),
    pad: {
      top: titled ? PANEL_TITLE_BOTTOM + GAP : cut + 8,
      right: cut + 8,
      bottom: cut + 8,
      left: cut + 8,
    },
  };
}

export function PanelFrame({
  title,
  variant,
  animate,
  flip,
  fill,
  minHeight = 120,
  children,
}: {
  title?: string;
  variant?: unknown;
  animate?: boolean;
  flip?: boolean;
  fill?: boolean;
  minHeight?: number;
  children?: React.ReactNode;
}) {
  const reactId = React.useId().replace(/:/g, '');
  const { ref, size } = useMeasure({ w: 504, h: 300 });
  const kind = variantOf(variant);
  const shaped = kind === 'bracket' ? panelBracket(size.w, size.h, Boolean(title)) : panelShapeResolved(kind, Math.max(200, size.w), Math.max(120, size.h), Boolean(title));
  return (
    <div
      ref={ref}
      className={['kb-panel-frame', animate ? 'is-animated' : '', flip ? 'is-flip-x' : '', fill ? 'kb-panel-frame--fill' : ''].filter(Boolean).join(' ')}
      style={{ minHeight: fill ? 0 : minHeight, height: fill ? '100%' : undefined }}
    >
      <FrameSvg
        id={`kb-panel-frame-${reactId}`}
        width={Math.max(200, size.w)}
        height={Math.max(120, size.h)}
        body={shaped.body}
        decor={shaped.decor}
        extra={shaped.titleBand}
        className="kb-panel-frame"
      />
      {title ? (
        <div className="kb-panel-frame-title" style={{ width: shaped.titleWidth, height: PANEL_TITLE_H, left: shaped.titleX, top: shaped.titleY }}>
          {title}
        </div>
      ) : null}
      <div className="kb-panel-frame-content" style={{ paddingTop: shaped.pad.top, paddingRight: shaped.pad.right, paddingBottom: shaped.pad.bottom, paddingLeft: shaped.pad.left }}>
        {children}
      </div>
    </div>
  );
}

function panelBracket(width: number, height: number, titled: boolean) {
  const spec = metrics('panel');
  const w = Math.max(200, Math.round(width));
  const h = Math.max(120, Math.round(height));
  const span = titleSpan(w);
  const inset = Math.max(spec.ringInset, PANEL_INSET);
  const arm = scaled(spec.arm, w);
  return {
    body: { d: cutPath(w, h, {}, PANEL_INSET), stroked: false },
    decor: [
      { d: ring(w, h, inset, 1), ink: 4 },
      ...(['tl', 'tr', 'br', 'bl'] as Corner[]).map((corner) => ({
        d: cornerArm(w, h, corner, arm, spec.armCross, spec.armWidth, PANEL_INSET),
        ink: corner === 'br' ? 1 : 2,
      })),
    ] as Ink[],
    titleBand: titled
      ? [
          { d: rect(inset + 8, PANEL_TITLE_BOTTOM - 2, span, 2), ink: 3 },
          { d: rect(inset + 8, PANEL_TITLE_BOTTOM - 10, spec.armWidth, 10), ink: 2 },
        ]
      : [],
    ...titleBox(span, inset + GAP + STEP),
    pad: {
      top: titled ? PANEL_TITLE_BOTTOM + GAP : inset + 12,
      right: inset + 12,
      bottom: inset + 12,
      left: inset + 16,
    },
  };
}

const CARD_PAD: Pad = { top: 20, right: 16, bottom: 16, left: 16 };

function indicatorShape(kind: FrameVariant, width: number, height: number): { body: Body; decor: Ink[]; pad: Pad } {
  const w = Math.max(120, Math.round(width));
  const h = Math.max(72, Math.round(height));
  if (kind === 'bracket') {
    const spec = metrics('card');
    const inset = Math.max(spec.ringInset, PANEL_INSET);
    const arm = scaled(spec.arm, w);
    return {
      body: { d: cutPath(w, h, {}, PANEL_INSET), stroked: false },
      decor: [
        { d: ring(w, h, inset, 1), ink: 4 },
        ...(['tl', 'tr', 'br', 'bl'] as Corner[]).map((corner) => ({
          d: cornerArm(w, h, corner, arm, spec.armCross, spec.armWidth, PANEL_INSET),
          ink: corner === 'br' ? 1 : 2,
        })),
      ],
      pad: { ...CARD_PAD, left: inset + 12, right: inset + 12 },
    };
  }
  if (kind === 'rail') {
    const spec = metrics('card');
    const top = PANEL_INSET;
    const bottom = h - PANEL_INSET - spec.rule;
    const innerH = Math.max(0, bottom - top - spec.rule);
    const innerW = w - PANEL_INSET * 2;
    return {
      body: { d: rect(PANEL_INSET, top + spec.rule, innerW, innerH), stroked: false },
      decor: [
        { d: rect(PANEL_INSET, top, innerW, spec.rule), ink: 3 },
        { d: rect(PANEL_INSET, bottom, innerW, spec.rule), ink: 2 },
        { d: rect(PANEL_INSET, bottom - STEP - spec.rule / 2, innerW, spec.rule / 2), ink: 4 },
        { d: rect(PANEL_INSET, top + spec.rule, 1, innerH), ink: 3 },
        { d: rect(w - PANEL_INSET - 1, top + spec.rule, 1, innerH), ink: 3 },
        { d: rect(PANEL_INSET, top + spec.rule, spec.cap, spec.cap), ink: 2 },
        { d: rect(w - PANEL_INSET - spec.cap, bottom - spec.cap, spec.cap, spec.cap), ink: 1 },
      ],
      pad: { ...CARD_PAD, top: spec.rule + 16, left: spec.cap + 12, right: spec.cap + 12 },
    };
  }
  if (kind === 'module') {
    const spec = metrics('card');
    const ruleY = 8 + spec.band.height + 8;
    const segments = bandSegments({
      x: PANEL_INSET + spec.band.gap,
      y: 8,
      width: w - (PANEL_INSET + spec.band.gap) * 2,
      height: spec.band.height,
      seg: spec.band.seg,
      gap: spec.band.gap,
    });
    const mid = Math.round((segments.length - 1) / 2);
    return {
      body: { d: cutPath(w, h, {}, PANEL_INSET), stroked: true },
      decor: [...groupBands(segments), { d: segments[mid].d, ink: 1 }, { d: rect(PANEL_INSET, ruleY, w - PANEL_INSET * 2, 2), ink: 4 }],
      pad: { ...CARD_PAD, top: ruleY + 8 },
    };
  }
  if (kind === 'blade') {
    const spec = metrics('card');
    const run = scaled(spec.bladeRun, Math.min(w, h));
    return {
      body: { d: bladeBody(w, h, run, spec.bladeSlope, PANEL_INSET), stroked: true },
      decor: [
        ...hatchMarks(run + 8, 8, 1, spec.hatch).map((d, index) => ({ d, ink: INKS[index] || 4 })),
        { d: cornerSquare(w, h, run + 8, PANEL_INSET), ink: 1 },
      ],
      pad: { ...CARD_PAD, left: run + 16, right: run + 16 },
    };
  }
  const cut = metrics('card').cut;
  return {
    body: { d: cutPath(w, h, { tl: cut, tr: cut, br: cut, bl: cut }, PANEL_INSET), stroked: true },
    decor: [
      { d: cornerFold(w, h, 'tl', cut, PANEL_INSET), ink: 2 },
      { d: cornerFold(w, h, 'br', cut, PANEL_INSET), ink: 1 },
    ],
    pad: CARD_PAD,
  };
}

export function IndicatorFrame({
  title,
  value,
  unit,
  variant,
  color,
}: {
  title?: string;
  value: string;
  unit?: string;
  variant?: unknown;
  color?: string;
}) {
  const reactId = React.useId().replace(/:/g, '');
  const { ref, size } = useMeasure({ w: 240, h: 120 });
  const shaped = indicatorShape(variantOf(variant), size.w, size.h);
  return (
    <div ref={ref} className="kb-indicator-frame" style={color ? ({ '--kb-accent': color } as React.CSSProperties) : undefined}>
      <FrameSvg id={`kb-indicator-frame-${reactId}`} width={Math.max(120, size.w)} height={Math.max(72, size.h)} body={shaped.body} decor={shaped.decor} className="kb-indicator-frame" />
      <div className="kb-indicator-frame-content" style={{ paddingTop: shaped.pad.top, paddingRight: shaped.pad.right, paddingBottom: shaped.pad.bottom, paddingLeft: shaped.pad.left }}>
        {title ? <div className="kb-indicator-frame-title">{title}</div> : null}
        <div className="kb-indicator-frame-value-row">
          <span className="kb-indicator-frame-value">{value}</span>
          {unit ? <span className="kb-indicator-frame-unit">{unit}</span> : null}
        </div>
      </div>
    </div>
  );
}
