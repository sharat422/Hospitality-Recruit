// Local browser smoke checks. Every external request is intercepted; no live data is changed.
const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:5173';

(async () => {
  const browser = await chromium.launch({ channel: process.env.SMOKE_BROWSER || 'msedge', headless: true });
  const results = [];
  try {
    const source = fs.readFileSync('src/AppRouter.tsx', 'utf8');
    const routes = [...source.matchAll(/path="([^"]+)"/g)].map(m => m[1]).filter(p => p !== '*').map(p => p.replace(/:[^/]+/g, 'audit-id'));
    const envText = ['.env', '.env.local'].filter(fs.existsSync).map(p => fs.readFileSync(p, 'utf8')).join('\n');
    const supabaseUrl = envText.match(/^VITE_SUPABASE_URL\s*=\s*["']?([^\s"']+)/m)?.[1];
    if (!supabaseUrl) throw new Error('Set VITE_SUPABASE_URL in .env.local before running smoke tests.');
    const storageKey = `sb-${new URL(supabaseUrl).hostname.split('.')[0]}-auth-token`;
    const permissions = [...new Set([...source.matchAll(/permission="([^"]+)"/g)].map(m => m[1]))];
    for (const authenticated of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' });
      if (authenticated) {
        const user = { id: 'audit-user', aud: 'authenticated', role: 'authenticated', email: 'audit@example.test', user_metadata: {} };
        const exp = Math.floor(Date.now() / 1000) + 3600;
        const encode = x => Buffer.from(JSON.stringify(x)).toString('base64url');
        const token = `${encode({alg:'HS256',typ:'JWT'})}.${encode({sub:user.id,aud:'authenticated',exp})}.audit`;
        await context.addInitScript(({storageKey, session}) => localStorage.setItem(storageKey, JSON.stringify(session)), {storageKey, session:{access_token:token,refresh_token:'audit-only',expires_at:exp,expires_in:3600,token_type:'bearer',user}});
      }
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path.endsWith('/rbac/me')) return route.fulfill({json:{userId:'audit-user',orgId:'audit-org',role:'OWNER',permissions,activePropertyId:null,propertyIds:[],departmentIds:[],departmentId:null}});
        if (path.endsWith('/hotels/properties')) return route.fulfill({json:{properties:[],active_property_id:null}});
        // Exercise explicit API failure states, not fabricated business success.
        if (path.startsWith('/api/') || url.origin !== new URL(base).origin) return route.fulfill({status:404,json:{detail:'Offline smoke fixture: no live service connection'}});
        return route.continue();
      });
      await context.routeWebSocket('**/*', socket => socket.close());
      const page = await context.newPage();
      for (const path of routes) {
        const errors = [];
        const onError = error => errors.push(error.message);
        page.on('pageerror', onError);
        try {
          await page.goto(base + path, {waitUntil:'networkidle',timeout:30000});
          await page.waitForTimeout(350);
          const content = await page.locator('body').innerText();
          assert(content.trim().length > 0, 'Page rendered a blank body');
          assert.equal(errors.length,0,errors.join('; '));
          results.push({path, authenticated, status:'passed', finalPath:new URL(page.url()).pathname});
        } catch (error) { results.push({path, authenticated, status:'failed',error:error.message}); }
        page.off('pageerror',onError);
      }
      await context.close();
    }
  } finally { await browser.close(); }
  fs.writeFileSync('smoke-results.json', JSON.stringify({scope:'Mobile-width route rendering, anonymous redirects and authenticated API error states; mocked network, not live E2E',results},null,2));
  console.log(`${results.filter(r=>r.status==='passed').length}/${results.length} browser smoke checks passed`);
  for (const result of results.filter(r=>r.status==='failed')) console.log(JSON.stringify(result));
  if(results.some(r=>r.status==='failed')) process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1});
