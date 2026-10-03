// Alert pictures (FR-14): plain inline SVG, no external images. The label comes
// from the strings file so it is translated with everything else.

import { escapeHtml, t } from "/shared/core.js";

const DRAW = {
  occlusion: `
    <rect x="20" y="10" width="44" height="56" rx="8" class="pic-line"/>
    <path d="M42 66 V92 Q42 108 58 108 H74 L90 92 L104 120 Q110 132 124 132 H150" class="pic-line pic-thick"/>
    <circle cx="90" cy="96" r="18" class="pic-warn"/>
    <path d="M90 86 V98 M90 104 V105" class="pic-line pic-warn-mark"/>`,
  bag_empty: `
    <path d="M50 14 H110 V70 Q110 96 80 96 Q50 96 50 70 Z" class="pic-line"/>
    <path d="M80 96 V140" class="pic-line pic-thick"/>
    <path d="M58 82 Q80 90 102 82" class="pic-line pic-dash"/>
    <text x="80" y="60" text-anchor="middle" class="pic-text">0</text>`,
  low_battery: `
    <rect x="22" y="44" width="104" height="56" rx="8" class="pic-line"/>
    <rect x="126" y="60" width="12" height="24" rx="3" class="pic-line"/>
    <rect x="32" y="54" width="18" height="36" rx="3" class="pic-warn"/>`,
  sensor_mismatch: `
    <path d="M50 14 H110 V70 Q110 96 80 96 Q50 96 50 70 Z" class="pic-line"/>
    <path d="M80 96 V140" class="pic-line pic-thick"/>
    <text x="80" y="70" text-anchor="middle" class="pic-text">?</text>`,
};

export function alertPicture(alarm) {
  const body = DRAW[alarm] || DRAW.sensor_mismatch;
  return (
    `<svg class="alert-pic" viewBox="0 0 160 150" role="img" aria-label="${escapeHtml(t(`pic_${alarm}`))}">` +
    `${body}</svg>`
  );
}
