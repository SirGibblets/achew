/**
 * Connection instructions for Settings → Agent Access: how to point each kind of MCP client
 * at Achew's server (backend/app/mcp_server) with its bearer token.
 */

export interface AgentClientConfig {
  id: string;
  name: string;
  /** What to do with the snippet */
  instructions: string;
  /** A command or config file excerpt, with the real token in it */
  snippet: string;
}

// A masked token shows its first VISIBLE_TOKEN_CHARS characters, padded with dots to MASKED_LENGTH
const VISIBLE_TOKEN_CHARS = 4;
const MASKED_LENGTH = 24;

export function maskToken(token: string): string {
  const dots = Math.max(0, Math.min(token.length, MASKED_LENGTH) - VISIBLE_TOKEN_CHARS);
  return token.slice(0, VISIBLE_TOKEN_CHARS) + '•'.repeat(dots);
}

export function isLocalUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '[::1]' || host.endsWith('.localhost');
  } catch {
    return false;
  }
}

export function agentClientConfigs(url: string, token: string): AgentClientConfig[] {
  const bearer = `Bearer ${token}`;

  // mcp-remote refuses plain HTTP to anything but localhost unless told otherwise
  const remoteArgs = ['-y', 'mcp-remote', url, '--header', 'Authorization:${ACHEW_AUTH}'];
  if (url.startsWith('http://') && !isLocalUrl(url)) {
    remoteArgs.push('--allow-http');
  }

  return [
    {
      id: 'claude-code',
      name: 'Claude Code',
      instructions: 'Run this in a terminal, then start Claude Code and check /mcp.',
      snippet: `claude mcp add --transport http achew ${url} --header "Authorization: ${bearer}"`,
    },
    {
      id: 'claude-desktop',
      name: 'Claude Desktop',
      instructions:
        'Add this to claude_desktop_config.json (Settings → Developer → Edit Config) and restart Claude Desktop. ' +
        'It needs Node.js, which runs the mcp-remote bridge.',
      snippet: JSON.stringify(
        { mcpServers: { achew: { command: 'npx', args: remoteArgs, env: { ACHEW_AUTH: bearer } } } },
        null,
        2,
      ),
    },
    {
      id: 'json',
      name: 'Other clients',
      instructions:
        'For clients that connect to remote (HTTP) MCP servers from a JSON config, such as Cursor ' +
        '(~/.cursor/mcp.json). VS Code uses "servers" in place of "mcpServers", plus "type": "http".',
      snippet: JSON.stringify({ mcpServers: { achew: { url, headers: { Authorization: bearer } } } }, null, 2),
    },
  ];
}
