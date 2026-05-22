#!/usr/bin/env node
/**
 * Genera config.js para Netlify con la URL pública de la API (Render, etc.).
 * Variable de entorno: IMOWI_API_URL=https://tu-api.onrender.com
 */
const fs = require('fs');
const path = require('path');

const apiUrl = (process.env.IMOWI_API_URL || '').replace(/\/$/, '');
const out = path.join(__dirname, '..', 'config.js');

const content = `// Auto-generado en build de Netlify — no editar a mano en prod
window.IMOWI_API_URL = ${JSON.stringify(apiUrl)};
`;

fs.writeFileSync(out, content, 'utf8');
console.log(`config.js → IMOWI_API_URL=${apiUrl || '(vacío, usa origin local)'}`);
