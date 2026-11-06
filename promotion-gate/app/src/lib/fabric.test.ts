import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./msal', () => ({ getToken: vi.fn(async () => 'token') }));

import { onelakeWrite } from './fabric';

afterEach(() => vi.unstubAllGlobals());

describe('onelakeWrite', () => {
  it('manda cuerpo en create, append y flush para que el navegador envíe Content-Length', async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(null, { status: 201 });
    }));
    await onelakeWrite('ws', 'lh', 'Files/x.json', '{"a":1}');
    expect(calls.map((c) => c.url.split('?')[1])).toEqual(['resource=file', 'action=append&position=0', 'action=flush&position=7']);
    for (const c of calls) expect(c.init.body).not.toBeUndefined();
    expect(calls.every((c) => (c.init.headers as Record<string, string>)['x-ms-version'])).toBe(true);
  });
});
