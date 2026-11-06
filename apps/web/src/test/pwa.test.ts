/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

describe('PWA Compliance & Service Worker Isolation', () => {
  const publicDir = path.resolve(__dirname, '../../public');
  const manifestPath = path.join(publicDir, 'manifest.webmanifest');
  const swPath = path.join(publicDir, 'sw.js');

  it('provides a valid W3C Web App Manifest with required installability metadata', () => {
    expect(fs.existsSync(manifestPath)).toBe(true);

    const rawManifest = fs.readFileSync(manifestPath, 'utf-8');
    const manifest = JSON.parse(rawManifest);

    expect(manifest.name).toBe('Isoswe Resident Portal');
    expect(manifest.short_name).toBe('Isoswe');
    expect(manifest.start_url).toBe('/resident');
    expect(manifest.display).toBe('standalone');
    expect(manifest.theme_color).toBe('#4f46e5');
    expect(manifest.background_color).toBe('#ffffff');
    expect(Array.isArray(manifest.icons)).toBe(true);
    expect(manifest.icons.length).toBeGreaterThanOrEqual(3);

    // Verify 192x192 icon exists
    const icon192 = manifest.icons.find((i: { sizes: string; purpose?: string }) => i.sizes === '192x192');
    expect(icon192).toBeDefined();
    expect(icon192.type).toBe('image/png');
    const icon192File = path.join(publicDir, icon192.src.replace(/^\//, ''));
    expect(fs.existsSync(icon192File)).toBe(true);
    expect(fs.statSync(icon192File).size).toBeGreaterThan(0);

    // Verify 512x512 icon exists
    const icon512 = manifest.icons.find(
      (i: { sizes: string; purpose?: string }) => i.sizes === '512x512' && (!i.purpose || i.purpose === 'any')
    );
    expect(icon512).toBeDefined();
    expect(icon512.type).toBe('image/png');
    const icon512File = path.join(publicDir, icon512.src.replace(/^\//, ''));
    expect(fs.existsSync(icon512File)).toBe(true);
    expect(fs.statSync(icon512File).size).toBeGreaterThan(0);

    // Verify maskable icon exists
    const iconMaskable = manifest.icons.find(
      (i: { sizes: string; purpose?: string }) => i.purpose === 'maskable'
    );
    expect(iconMaskable).toBeDefined();
    expect(iconMaskable.type).toBe('image/png');
    const iconMaskableFile = path.join(publicDir, iconMaskable.src.replace(/^\//, ''));
    expect(fs.existsSync(iconMaskableFile)).toBe(true);
    expect(fs.statSync(iconMaskableFile).size).toBeGreaterThan(0);
  });

  it('enforces strict service worker cache isolation (never intercepts or caches /api/ or auth)', () => {
    expect(fs.existsSync(swPath)).toBe(true);

    const swContent = fs.readFileSync(swPath, 'utf-8');

    // App shell caching asserts
    expect(swContent).toContain("CACHE_NAME = 'isoswe-shell-v1'");
    expect(swContent).toContain("'/index.html'");
    expect(swContent).toContain("'/manifest.webmanifest'");

    // Strictly ensure no API routes are bundled in app shell
    const appShellMatch = swContent.match(/APP_SHELL\s*=\s*\[([\s\S]*?)\];/);
    expect(appShellMatch).not.toBeNull();
    const appShellContent = appShellMatch![1];
    expect(appShellContent).not.toMatch(/'\/api/);
    expect(appShellContent).not.toMatch(/'\/auth/);

    // STRICT BYPASS: Never intercept or cache API, auth, health, or non-GET requests
    expect(swContent).toContain("request.method !== 'GET'");
    expect(swContent).toContain("url.pathname.startsWith('/api')");
    expect(swContent).toContain("url.pathname.startsWith('/health')");
    expect(swContent).toContain("url.hostname.includes('supabase')");

    // SPA fallback handling
    expect(swContent).toContain("request.mode === 'navigate'");
    expect(swContent).toContain("cache.match('/index.html')");
  });
});
