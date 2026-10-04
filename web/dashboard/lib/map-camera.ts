export type Camera = { x: number; y: number; scale: number };
export type Size = { width: number; height: number };
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 3.5;
export function constrainCamera(camera: Camera, size: Size): Camera {
  const scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, camera.scale));
  return {
    scale,
    x: Math.max(size.width * (1 - scale), Math.min(0, camera.x)),
    y: Math.max(size.height * (1 - scale), Math.min(0, camera.y)),
  };
}
// Preserve the map point under the cursor or pinch midpoint while zooming.
export function zoomCamera(camera: Camera, scale: number, point: { x: number; y: number }, size: Size): Camera {
  const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, scale));
  const ratio = next / camera.scale;
  return constrainCamera({ scale: next, x: point.x - (point.x - camera.x) * ratio, y: point.y - (point.y - camera.y) * ratio }, size);
}
