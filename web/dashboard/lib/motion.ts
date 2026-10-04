// Shared tokens; Framer Motion is the user's requested animation engine.
export const motionTokens = {
  duration: { fast: .18, normal: .35, telemetry: .6, pulse: 2.4 },
  distance: { sm: 8, md: 16 },
  scale: { press: .98, hover: 1.05 },
  easing: { smooth: [.22, 1, .36, 1] as [number, number, number, number] },
};
export const springs = { snappy: { type: "spring" as const, stiffness: 300, damping: 30 } };
