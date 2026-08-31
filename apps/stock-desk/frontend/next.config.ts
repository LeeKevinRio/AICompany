import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

// Pin the workspace root to this app directory. Without this, a stray
// lockfile anywhere above (e.g. an accidental repo-root package-lock.json)
// makes Next infer the monorepo root and watch the entire repo — including
// the backend's venv and its SQLite db that the scheduler rewrites every
// minute — driving the dev server's file watcher into unbounded memory
// growth until the process dies (observed: 31 GB heap OOM on Windows).
const appRoot = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Do not generate AGENTS.md / CLAUDE.md into the app directory (they are
  // also gitignored; this stops them from being created at all).
  agentRules: false,
  outputFileTracingRoot: appRoot,
  turbopack: {
    root: appRoot,
  },
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
