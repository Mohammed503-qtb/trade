import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // watcher v2: تغطية inbox إضافة إلى upload
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // يسمح لمصادر المعاينة (space-z.ai) بتحميل أصول dev دون تحذيرات أصل متقاطع
  allowedDevOrigins: ["*.space-z.ai"],
};

export default nextConfig;
