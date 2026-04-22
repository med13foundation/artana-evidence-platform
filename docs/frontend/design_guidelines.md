# MED13 Foundation Design Guidelines: The Science Engine

## Design Philosophy: "Soft Clinical"

The design system for the MED13 Science Engine is built on a **"Soft Clinical"** aesthetic. It aims to bridge the gap between high-velocity scientific research and the deeply personal, human experience of rare disease families.

**Design Tone Keywords:**
💞 *Warm • Inclusive • Trustworthy • Hopeful • Connected • Human-Centered*

## 1. Color System: "Stability meets Hope"

The palette evokes optimism, empathy, and clarity - balancing medical trust with human warmth.

**Primary Palette:**
- **Soft Teal (Primary Science)** `#68B0AB` (HSL: 176 31% 55%) - The anchor for "Science." Associated with clarity, renewal, and precision. Professional but significantly warmer and more modern than "Hospital Blue."
- **Coral-Peach (The Human Factor)** `#FFB6A0` (HSL: 12 100% 81%) - Used for family insights, support indicators, and phenotypes. Provides emotional contrast to data-heavy sections.
- **Sunlight Yellow (Exploration)** `#FFD166` (HSL: 43 100% 70%) - Reserved for "Exploration" and "Hypotheses." Mimics sunlight, visually highlighting areas where new knowledge is being "illuminated."

## 2. Typography: "The Narrative of Discovery"

Communicate clarity and care at first glance with humanistic, approachable type.

**Font Families:**
- **UI & Data**: Inter - Used for all UI controls and dense data. Highly legible with a large x-height, essential for complex genetic data.
- **Headings**: Nunito Sans - Rounded, humanistic, family-friendly typeface that softens the interface.
- **Narrative Intros/Display**: Playfair Display - Elegant serif that evokes the feeling of a prestigious scientific journal, giving research a sense of weight and importance.

## 3. Component Architecture: "Tactile Intelligence"

- **Rounded Corners**: We avoid sharp 90-degree corners.
  - `rounded-3xl` (24px): Main platform containers and high-level sections.
  - `rounded-xl` (12px): Interactive cards and primary UI blocks.
  - This reduces "visual friction" and makes the complex "Science Engine" feel more organic.
- **Shadow System**:
  - `brand-sm` to `brand-lg`: Low-opacity, large-blur shadows give components a "floating" look.
  - Signifies a dynamic, layered interface where knowledge is constantly re-ordered.

## 4. Evidence & Claims Styling

- **Reasoning Blocks**: Subtle `bg-brand-primary/5` tint. This "scientific highlight" sets apart interpretation from raw data, maintaining high standards of provenance.
- **Autonomy Toggles (L0-L3)**: Styled like physical hardware switches to emphasize the "Engine" aspect where users choose how much "power" to give the AI.

## 5. Layout & Workflow Modes

The "dual-sidebar" layout allows for three distinct modes of work:
1. **Focus Mode**: Both sidebars collapsed for deep data analysis (Graph/Feed).
2. **Context Mode**: Left sidebar open for program navigation.
3. **Collaborative Mode**: Right chat open to treat the AI as a co-investigator.
