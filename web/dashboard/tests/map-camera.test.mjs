import assert from "node:assert/strict";
import test from "node:test";
import { constrainCamera, zoomCamera } from "../lib/map-camera.ts";

const size = { width: 800, height: 600 };
test("panning cannot expose space outside the ward", () => {
  assert.deepEqual(constrainCamera({ x: 200, y: -2000, scale: 2 }, size), { x: 0, y: -600, scale: 2 });
  assert.deepEqual(constrainCamera({ x: -9000, y: 4000, scale: 3.5 }, size), { x: -2000, y: 0, scale: 3.5 });
});
test("zoom preserves the map point under a cursor or pinch midpoint", () => {
  const camera = { x: -150, y: -120, scale: 2 };
  const point = { x: 400, y: 300 };
  const next = zoomCamera(camera, 2.5, point, size);
  assert.equal((point.x - camera.x) / camera.scale, (point.x - next.x) / next.scale);
  assert.equal((point.y - camera.y) / camera.scale, (point.y - next.y) / next.scale);
});
test("zoom limits and fitting the ward restore bounded coordinates", () => {
  assert.deepEqual(constrainCamera({ x: -99, y: -90, scale: .2 }, size), { x: 0, y: 0, scale: 1 });
  assert.equal(zoomCamera({ x: 0, y: 0, scale: 1 }, 99, { x: 0, y: 0 }, size).scale, 3.5);
  assert.deepEqual(zoomCamera({ x: -200, y: -100, scale: 2 }, 1, { x: 400, y: 300 }, size), { x: 0, y: 0, scale: 1 });
});
