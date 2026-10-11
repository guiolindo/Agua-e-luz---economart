const { chromium } = require('playwright');
const G = (process.env.GEM_DIR || '/tmp/gemini_battery') + '/';
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  const p = await b.newPage({ viewport: { width: 972, height: 1200 }, deviceScaleFactor: 1.5 });
  for (const k of ['cemig', 'coelba', 'energisa', 'cemiggt']) {
    await p.goto('file://' + G + k + '.html'); await p.waitForTimeout(250);
    await p.screenshot({ path: G + k + '.png', fullPage: true });
  }
  await p.goto('file://' + G + 'coelba.html'); await p.pdf({ path: G + 'coelba.pdf', format: 'A4', printBackground: true });
  await b.close();
})();
