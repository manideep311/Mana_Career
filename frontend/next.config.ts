import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  outputFileTracingRoot: process.cwd(),
  // Don't advertise the framework (nginx also strips it in production).
  poweredByHeader: false,
};

export default config;
