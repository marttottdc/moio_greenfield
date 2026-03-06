# Design Guidelines: moio CRM React Client

## Design Approach
**Selected System**: Radiant-inspired modern productivity interface combining Fluent Design's information density with contemporary visual polish, subtle gradients, and BentoCard layouts.

**Core Principles**:
- Premium productivity: Information-dense with elevated visual treatment
- Modern depth: Subtle gradients and layering for hierarchy
- Bento layouts: Asymmetric card grids for dashboard appeal
- Polished efficiency: Beautiful AND functional

## Colors (Brand Implementation)
- Primary: #58a6ff (moio blue)
- Success: #74c365 (green)
- Warning: #ffba08 (yellow)
- Danger: #ff6b6b (red)
- Sidebar/Dark: #2f3542
- Backgrounds: White (#ffffff), Light gray (#f8f9fa)
- Borders: #e1e4e8
- Text: #1f2937 (primary), #6b7280 (secondary)

**Gradient Applications**:
- Sidebar header: Linear gradient from #2f3542 to slightly lighter variation
- Card hover states: Subtle shine overlay
- Primary buttons: Gradient from #58a6ff to #4a96e8
- Success states: Gradient from #74c365 to #68b85c

## Typography System
**Font Family**: Inter (Google Fonts CDN - 400, 500, 600, 700)

**Hierarchy**:
- Dashboard Headers: text-3xl font-bold with letter-spacing tighter
- Page Titles: text-2xl font-semibold
- Section Headers: text-lg font-semibold
- Card Titles: text-base font-semibold
- Body: text-sm
- Labels: text-xs font-medium uppercase tracking-wider
- Metrics (large): text-4xl font-bold with tabular-nums

## Layout System
**Spacing**: Tailwind units 2, 4, 6, 8, 12, 16, 20, 24

**Primary Structure**:
- Sidebar: Fixed w-64 with gradient background
- Main: flex-1 with p-8 container max-w-[1600px]
- Dashboard sections: space-y-8
- Card grids: gap-6

**BentoCard Grid Patterns** (Dashboard):
```
Primary Dashboard Layout:
- Stats overview: grid-cols-4 gap-4 (4 equal metric cards)
- Main content: grid-cols-3 gap-6 with spanning elements
  - Large feature card: col-span-2 row-span-2
  - Smaller cards: col-span-1
  - Wide elements: col-span-3 for tables/lists

Campaign Dashboard:
- Hero metrics: grid-cols-3 gap-4
- Campaign cards: grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6
```

## Component Library

### Navigation Sidebar
- Width: w-64 fixed with gradient background (#2f3542 to darker)
- Logo zone: h-16 px-6 with subtle bottom border
- Nav items: mx-3 px-3 py-2.5 rounded-lg
- Icons: Heroicons w-5 h-5
- Active: Background with #58a6ff tint, white text
- Inactive: Light gray text with hover brightness
- Section dividers: my-4 border-t with reduced opacity

### BentoCards (Dashboard)
**Metric Cards** (small):
- p-6 rounded-xl border shadow-sm
- Gradient overlay on hover
- Icon: w-10 h-10 in top-right with brand color background, rounded-lg
- Value: text-3xl font-bold tabular-nums
- Label: text-sm text-gray-600 mt-1
- Trend: text-xs with arrow icon, color-coded

**Feature Cards** (large span):
- p-8 rounded-xl border shadow-md
- Header with icon + title + action button
- Content area with charts/lists
- Footer with metadata or CTAs
- Subtle gradient background wash

**Activity/List Cards**:
- Compact p-6 with scrollable content
- Header with title + "View all" link
- List items: py-3 border-b with avatar/icon + text + metadata
- Max 5 items visible, subtle fade at bottom

### Data Tables
- Container: rounded-xl border shadow-sm with white background
- Toolbar: p-4 border-b with search (w-80) + filters flex justify-between
- Header: Sticky bg-gray-50 with px-6 py-3
- Rows: px-6 py-4 hover:bg-gray-50 transition
- Actions: Right column with icon buttons (w-8 h-8 rounded-md)
- Pagination: p-4 border-t flex justify-between items-center

### Forms & Inputs
**Text Inputs**:
- h-11 px-4 rounded-lg border
- Focus: ring-2 ring-[#58a6ff] ring-opacity-50 border-[#58a6ff]
- Labels: text-sm font-medium mb-2 block

**Buttons**:
- Primary: px-6 py-2.5 rounded-lg font-medium gradient background, white text, shadow-sm
- Secondary: Same size, border-2 border-gray-300, hover:border-[#58a6ff]
- Icon-only: w-10 h-10 rounded-lg
- Buttons on images: backdrop-blur-md bg-white/90 border border-white/20

**Dropdowns**:
- h-11 px-4 rounded-lg border with chevron-down icon
- Menu: mt-2 rounded-lg shadow-xl border p-1
- Items: px-3 py-2 rounded-md hover:bg-gray-100

### Workflow Builder
**Canvas**: 
- Full height bg-gray-50 with subtle dot pattern
- Zoom: Fixed bottom-right z-20 with rounded-lg controls
- Grid snap visualization

**Node Palette** (left sidebar):
- w-72 bg-white border-r p-4
- Categories: Collapsible with header (font-semibold text-xs uppercase)
- Node items: p-3 rounded-lg border mb-2 with drag handle + icon + label
- Hover: shadow-md transform

**Nodes**:
- min-w-64 rounded-xl shadow-lg border-2 p-4
- Header: Icon (w-6 h-6) + title + close button
- Ports: w-3 h-3 rounded-full on edges
- Selected: border-[#58a6ff] shadow-[#58a6ff]/20
- Categories color-coded with subtle backgrounds

### Status & Indicators
**Badges**: px-3 py-1 rounded-full text-xs font-semibold
- Active: bg-[#74c365] text-white
- Paused: bg-[#ffba08] text-gray-900
- Error: bg-[#ff6b6b] text-white
- Draft: bg-gray-200 text-gray-700

**Loading States**: Shimmer effect with gradient animation

## Responsive Behavior
- Sidebar: Collapse to w-20 icons-only at lg breakpoint
- Bento grids: Collapse to grid-cols-1 below md
- Tables: Horizontal scroll with sticky first column on mobile
- Mobile nav: Full-height overlay drawer

## Icons & Assets
**Icons**: Heroicons (CDN)
- Navigation/Cards: w-5 h-5
- Buttons: w-4 h-4
- Large features: w-12 h-12

**No Hero Images**: Productivity CRM - focus on data visualization, charts (Chart.js/Recharts), and functional UI. Dashboard uses BentoCard layouts instead of hero sections.

## Polish Details
- Transitions: transition-all duration-200 on hover states
- Shadows: Layered (shadow-sm on cards, shadow-md on hover, shadow-xl on modals)
- Borders: Consistent 1px with #e1e4e8
- Rounded corners: rounded-lg (8px) standard, rounded-xl (12px) for larger cards
- Micro-interactions: Scale on button press, smooth color transitions