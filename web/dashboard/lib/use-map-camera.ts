"use client";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { animate, useMotionValue, useReducedMotion } from "framer-motion";
import { constrainCamera, zoomCamera, type Camera, type Size } from "./map-camera";
import { motionTokens } from "./motion";

type Point = { x: number; y: number };
export function useMapCamera() {
  const viewport = useRef<HTMLDivElement>(null);
  const size = useRef<Size>({ width: 1, height: 1 });
  const reduced = useReducedMotion();
  const x = useMotionValue(0), y = useMotionValue(0), scale = useMotionValue(1);
  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const animation = useRef<{ stop: () => void }[]>([]);
  const points = useRef(new Map<number, Point>());
  const gesture = useRef<{ camera: Camera; midpoint: Point; distance: number; dragged: boolean } | null>(null);
  const suppressClick = useRef(false);
  const desired = useRef<Camera>({ x: 0, y: 0, scale: 1 });
  const snapshot = () => ({ x: x.get(), y: y.get(), scale: scale.get() });
  function stop() { animation.current.forEach((control) => control.stop()); animation.current = []; }
  function move(camera: Camera, smooth = false) {
    stop(); const next = constrainCamera(camera, size.current);
    desired.current = next;
    setZoom(next.scale);
    if (smooth && !reduced) {
      const transition = { duration: motionTokens.duration.normal, ease: motionTokens.easing.smooth };
      animation.current = [animate(x, next.x, transition), animate(y, next.y, transition), animate(scale, next.scale, transition)];
    } else { x.set(next.x); y.set(next.y); scale.set(next.scale); }
  }
  const action = useRef({ snapshot, move });
  action.current = { snapshot, move };
  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const observer = new ResizeObserver(() => {
      if (!node.clientWidth || !node.clientHeight) return;
      const previous = size.current;
      size.current = { width: node.clientWidth, height: node.clientHeight };
      // Preserve normalized framing while the adjacent details pane changes width.
      const camera = desired.current;
      action.current.move({ ...camera, x: camera.x * size.current.width / previous.width, y: camera.y * size.current.height / previous.height }, true);
    });
    observer.observe(node);
    // Native listener is deliberately non-passive: wheel zoom must never scroll the document.
    function wheel(event: WheelEvent) {
      event.preventDefault();
      const rect = node!.getBoundingClientRect();
      const camera = action.current.snapshot();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      action.current.move(zoomCamera(camera, camera.scale * Math.exp(-delta * .002), { x: event.clientX - rect.left, y: event.clientY - rect.top }, size.current));
    }
    node.addEventListener("wheel", wheel, { passive: false });
    return () => { observer.disconnect(); node.removeEventListener("wheel", wheel); animation.current.forEach((control) => control.stop()); };
  }, []);
  function measure() {
    const values = [...points.current.values()];
    const first = values[0], second = values[1];
    return second ? { midpoint: { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 }, distance: Math.hypot(first.x - second.x, first.y - second.y) } : { midpoint: first, distance: 0 };
  }
  function point(event: ReactPointerEvent): Point {
    const rect = viewport.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }
  function down(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    stop(); points.current.set(event.pointerId, point(event));
    const geometry = measure();
    gesture.current = { ...geometry, camera: snapshot(), dragged: points.current.size > 1 };
    suppressClick.current = points.current.size > 1;
    if (points.current.size > 1) { for (const id of points.current.keys()) viewport.current?.setPointerCapture(id); setDragging(true); }
  }
  function drag(event: ReactPointerEvent<HTMLDivElement>) {
    const start = gesture.current;
    if (!points.current.has(event.pointerId) || !start) return;
    points.current.set(event.pointerId, point(event));
    const geometry = measure();
    const dx = geometry.midpoint.x - start.midpoint.x, dy = geometry.midpoint.y - start.midpoint.y;
    if (!start.dragged && Math.hypot(dx, dy) < 5) return;
    start.dragged = true; suppressClick.current = true; setDragging(true);
    viewport.current?.setPointerCapture(event.pointerId);
    if (geometry.distance && start.distance) {
      const camera = zoomCamera(start.camera, start.camera.scale * geometry.distance / start.distance, start.midpoint, size.current);
      move({ ...camera, x: camera.x + dx, y: camera.y + dy });
    } else move({ ...start.camera, x: start.camera.x + dx, y: start.camera.y + dy });
  }
  function up(event: ReactPointerEvent<HTMLDivElement>) {
    if (!points.current.has(event.pointerId)) return;
    points.current.delete(event.pointerId);
    if (viewport.current?.hasPointerCapture(event.pointerId)) viewport.current.releasePointerCapture(event.pointerId);
    if (points.current.size) gesture.current = { ...measure(), camera: snapshot(), dragged: true };
    else { gesture.current = null; setDragging(false); }
  }
  function center(left: number, top: number) {
    const next = Math.max(1.6, scale.get());
    move({ scale: next, x: size.current.width * (.5 - left * next), y: size.current.height * (.5 - top * next) }, true);
  }
  function zoomBy(factor: number) { move(zoomCamera(snapshot(), scale.get() * factor, { x: size.current.width / 2, y: size.current.height / 2 }, size.current), true); }
  return {
    viewport, x, y, scale, zoom, dragging, center, zoomBy,
    reset: () => move({ x: 0, y: 0, scale: 1 }, true),
    events: {
      onPointerDown: down, onPointerMove: drag, onPointerUp: up, onPointerCancel: up,
      onClickCapture: (event: React.MouseEvent) => { if (event.detail && suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } },
    },
  };
}
