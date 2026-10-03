// Usage: npm run simulate -- [games] [firstSeed]
import { simulate } from '../src/game/simulate.js';

const games = Number(process.argv[2] ?? 200);
const firstSeed = Number(process.argv[3] ?? 1);
const started = Date.now();
const stats = simulate(games, firstSeed);
console.log(JSON.stringify({ ...stats, ms: Date.now() - started }, null, 2));
