import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  turbopack: { root: path.resolve(process.cwd(), "..") },
  devIndicators: false,
  poweredByHeader: false,
};
export default config;
