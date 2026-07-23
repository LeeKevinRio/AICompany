import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // typescript@7.0.2 (native Go rewrite) does not yet expose the legacy
  // CommonJS compiler API that next@16.2.11's internal build-time
  // type-checker probes for, which crashes `next build`. Type safety is
  // still enforced via `npm run typecheck` (`tsc --noEmit`), which works
  // correctly against typescript@7.0.2 and must pass before merge.
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
