/**
 * Bootstrap loader for Baileys on Node.js 18.
 * Ensures WebCrypto polyfill is loaded before any ESM imports.
 */
const nodeCrypto = require('node:crypto');
if (!globalThis.crypto) {
  globalThis.crypto = nodeCrypto.webcrypto || nodeCrypto;
}

import('./index.js').catch((err) => {
  console.error('[WhatsApp Bridge Fatal Loader Error]:', err);
  process.exit(1);
});
