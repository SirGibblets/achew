import { describe, expect, it } from 'vitest';

import { agentClientConfigs, isLocalUrl, maskToken } from './agentAccess';

const TOKEN = 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG';

function snippet(url: string, id: string): string {
  const config = agentClientConfigs(url, TOKEN).find((c) => c.id === id);
  if (!config) throw new Error(`no ${id} config`);
  return config.snippet;
}

describe('agentClientConfigs', () => {
  it('builds a Claude Code command with the bearer header', () => {
    expect(snippet('http://localhost:8000/mcp', 'claude-code')).toBe(
      `claude mcp add --transport http achew http://localhost:8000/mcp --header "Authorization: Bearer ${TOKEN}"`,
    );
  });

  it('gives JSON clients the URL and header', () => {
    const config = JSON.parse(snippet('https://achew.example.com/mcp', 'json'));
    expect(config.mcpServers.achew).toEqual({
      url: 'https://achew.example.com/mcp',
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
  });

  it('bridges Claude Desktop through mcp-remote, with the token in an env var', () => {
    const local = JSON.parse(snippet('http://127.0.0.1:8000/mcp', 'claude-desktop')).mcpServers.achew;
    expect(local.args).toEqual([
      '-y',
      'mcp-remote',
      'http://127.0.0.1:8000/mcp',
      '--header',
      'Authorization:${ACHEW_AUTH}',
    ]);
    expect(local.env).toEqual({ ACHEW_AUTH: `Bearer ${TOKEN}` });

    // Plain HTTP to another machine needs mcp-remote's opt-in; HTTPS doesn't
    const lan = JSON.parse(snippet('http://192.168.1.20:3000/mcp', 'claude-desktop')).mcpServers.achew;
    expect(lan.args.at(-1)).toBe('--allow-http');
    const https = JSON.parse(snippet('https://achew.example.com/mcp', 'claude-desktop')).mcpServers.achew;
    expect(https.args).not.toContain('--allow-http');
  });
});

describe('isLocalUrl', () => {
  it('recognises loopback hosts', () => {
    expect(isLocalUrl('http://localhost:5173/mcp')).toBe(true);
    expect(isLocalUrl('http://127.0.0.1/mcp')).toBe(true);
    expect(isLocalUrl('http://nas.lan:8000/mcp')).toBe(false);
    expect(isLocalUrl('not a url')).toBe(false);
  });
});

describe('maskToken', () => {
  it('keeps only the first few characters', () => {
    const masked = maskToken(TOKEN);
    expect(masked.startsWith('abcd')).toBe(true);
    expect(masked).not.toContain('efgh');
    expect(masked.length).toBe(24);
  });
});
