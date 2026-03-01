/**
 * Monochrome-first token set. Color appears only where it carries meaning:
 * a streak, a due date, an error. Everything else is ink on paper.
 *
 * Contrast was checked against the surface each token is used on. `inkFaint`
 * clears 3:1 only, so it is reserved for decorative glyphs sitting beside a
 * visible text label, never for text that has to be read on its own.
 */

const light = {
  canvas: "#FBFBFA",
  surface: "#FFFFFF",
  sunken: "#F3F3F1",
  hairline: "#E7E7E3",
  hairlineStrong: "#D5D5CF",

  ink: "#191918",
  inkMuted: "#66665F",
  inkFaint: "#8E8E85",

  fill: "#191918",
  onFill: "#FBFBFA",

  positive: "#1C7A4B",
  caution: "#8A5A0B",
  critical: "#B0261E",

  positiveWash: "#EBF4EF",
  cautionWash: "#F8F1E3",
  criticalWash: "#FBEDEB",

  overlay: "rgba(25, 25, 24, 0.34)",
};

const dark = {
  canvas: "#0A0A0B",
  surface: "#141416",
  sunken: "#1B1B1E",
  hairline: "#27272B",
  hairlineStrong: "#3A3A40",

  ink: "#F5F5F6",
  inkMuted: "#A2A2A9",
  inkFaint: "#6E6E76",

  fill: "#F5F5F6",
  onFill: "#0A0A0B",

  positive: "#5CCB8D",
  caution: "#DFAA4A",
  critical: "#EF7B72",

  positiveWash: "#12241B",
  cautionWash: "#241D10",
  criticalWash: "#2A1715",

  overlay: "rgba(0, 0, 0, 0.6)",
};

export type Palette = typeof light;
export const palettes = { light, dark };

/** 4pt rhythm. Section spacing tiers are 16 / 24 / 32. */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

export const radius = {
  xs: 6,
  sm: 8,
  md: 10,
  lg: 14,
  xl: 20,
  full: 999,
} as const;

/** Icon sizes are tokens so strokes stay on the same optical rhythm. */
export const iconSize = { sm: 16, md: 20, lg: 24 } as const;

/** Press feedback lands inside 150ms; entrances get a little longer. */
export const duration = { press: 120, enter: 220, exit: 160 } as const;

/** Smallest comfortable tap target on either platform. */
export const HIT = 44;
