import { resolve } from 'node:path';
import { buildApp } from './api/app.js';
import { JsonPlayerRepository } from './store/players.js';

const port = Number(process.env.PORT ?? 3000);
// Bind to loopback by default; set HOST=0.0.0.0 to test from other devices on the LAN.
const host = process.env.HOST ?? '127.0.0.1';
const dataFile = resolve(process.env.DATA_FILE ?? 'data/players.json');
const webglDir = resolve(process.env.WEBGL_DIR ?? '../client/Build/WebGL');
const corsOrigin = process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',').map((s) => s.trim()) : true;

const repo = new JsonPlayerRepository(dataFile);
const { app } = await buildApp({ repo, corsOrigin, webglDir, logger: true });

const shutdown = async (): Promise<void> => {
  await app.close();
  repo.close();
  process.exit(0);
};
process.on('SIGINT', () => void shutdown());
process.on('SIGTERM', () => void shutdown());

await app.listen({ port, host });
