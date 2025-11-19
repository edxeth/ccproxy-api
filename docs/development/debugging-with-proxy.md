# Debugging with HTTP Proxy

This guide explains how to use HTTP proxies for debugging requests made by the CCProxy API server.

## Overview

The CCProxy API server supports standard HTTP proxy environment variables, allowing you to intercept and debug HTTP/HTTPS traffic using tools like:

- [mitmproxy](https://mitmproxy.org/)
- [Fiddler](https://www.telerik.com/fiddler)
- Corporate proxies

## Setting Up Proxy

### Basic Proxy Configuration

Set the appropriate environment variables before starting the server:

```bash
# For HTTP and HTTPS traffic
export HTTP_PROXY=http://localhost:8888
export HTTPS_PROXY=http://localhost:8888

# Or use ALL_PROXY for both protocols
export ALL_PROXY=http://localhost:8888

# Start the server
./Taskfile dev
```

### Using mitmproxy

1. Install mitmproxy:
   ```bash
   pip install mitmproxy
   ```

2. Start mitmproxy:
   ```bash
   mitmproxy
   # or for web interface
   mitmweb
   ```

3. Export the proxy settings:
   ```bash
   export HTTPS_PROXY=http://localhost:8080
   ```

4. Install mitmproxy's CA certificate (see below)

## SSL/TLS Certificate Configuration

When using HTTPS proxies that perform SSL interception, you'll need to configure the proxy's root CA certificate.

### Option 1: Using Custom CA Bundle (Recommended)

```bash
# For mitmproxy
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem

# Or use SSL_CERT_FILE
export SSL_CERT_FILE=/path/to/your/ca-bundle.pem

# Start the server
./Taskfile dev
```

### Option 2: Disable SSL Verification (Development Only)

**WARNING**: This is insecure and should only be used for local development.

```bash
export SSL_VERIFY=false
./Taskfile dev
```

### Installing Proxy CA Certificates

#### mitmproxy
```bash
# The CA certificate is typically located at:
~/.mitmproxy/mitmproxy-ca-cert.pem

# Set the environment variable
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem
```

#### Charles Proxy
1. In Charles: Help > SSL Proxying > Save Charles Root Certificate
2. Save as PEM format
3. Set: `export REQUESTS_CA_BUNDLE=/path/to/charles-ca-cert.pem`

## Debugging Example

Here's a complete example using mitmproxy:

```bash
# Terminal 1: Start mitmproxy
mitmweb --listen-port 8888

# Terminal 2: Configure and run the server
export HTTPS_PROXY=http://localhost:8888
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem
./Taskfile dev

# Terminal 3: Make a test request
curl -X POST http://localhost:8000/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-opus-20240229", "messages": [{"role": "user", "content": "Hello"}]}'
```

You should now see the request to `api.anthropic.com` in the mitmproxy web interface.

## Capturing Codex SSE Model Metadata

When you need to verify the exact Codex model returned by OpenAI, run CCProxy
through mitmproxy and use the helper script `scripts/mitm_codex_sse_logger.py`
to automatically print the model name contained in each SSE event. This is
especially useful when double-checking that the Codex CLI or `ccproxy` is
actually receiving `gpt-5.1-codex` (high) from the upstream Response API.

```bash
# Terminal 1: run mitmproxy with the SSE logger
pip install --upgrade mitmproxy
mitmdump --listen-port 8888 -s scripts/mitm_codex_sse_logger.py

# Terminal 2: route CCProxy through the proxy
export HTTPS_PROXY=http://localhost:8888
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem

# Start CCProxy normally (Taskfile/devserver/uvx all work)
./Taskfile dev

# Terminal 3: trigger a streaming Codex request
curl -N http://localhost:8000/codex/responses \
  -H "Content-Type: application/json" \
  -d '{
        "model": "gpt-5.1-codex",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": true
      }'
```

`mitmdump` prints log lines similar to:

```
127.0.0.1:53624: clientconnect
<< codex_sse_model event_type=response.created model=gpt-5.1-codex url=https://chatgpt.com/backend-api/codex/v1/responses
```

Each SSE event carries the same `model` field, so you can watch the log to
confirm what the upstream actually returned. Because the CCProxy HTTP client
respects the standard `HTTPS_PROXY`, `ALL_PROXY`, and `REQUESTS_CA_BUNDLE`
variables, the same approach also works when running the Codex CLI itself (set
the environment variables before invoking `codex exec ...`).

### Proxying a Codex CLI Run

You can capture a *real* `codex exec` run by pointing the CLI at CCProxy (via a
profile in `~/.codex/config.toml`) and routing the CCProxy process through
mitmproxy. The CLI stays non-interactive, so it works inside the Codex CLI headless
environment.

```toml
# ~/.codex/config.toml
[profiles.ccproxy]
model_provider = "ccproxy"
[model_providers.ccproxy]
name = "CCProxy"
base_url = "http://127.0.0.1:8000/codex"
wire_api = "responses"
model = "gpt-5.1-codex"
model_reasoning_effort = "high"
model_reasoning_summary = "detailed"
```

With that profile in place, run the following three terminals:

```bash
# Terminal 1: mitmproxy + SSE logger
mitmdump --listen-port 8888 -s scripts/mitm_codex_sse_logger.py

# Terminal 2: start CCProxy with proxy + CA configuration
export HTTPS_PROXY=http://127.0.0.1:8888
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem
./Taskfile dev  # or whichever command you use to run ccproxy

# Terminal 3: trigger a Codex CLI request routed through CCProxy
codex exec --profile ccproxy --model gpt-5.1-codex --sandbox danger-full-access \
  --ask-for-approval=never "Write a short diagnostic reply"
```

The command in Terminal 3 forces the CLI to hit the local CCProxy instance,
which then talks to ChatGPT via mitmproxy. You will see the resulting SSE traffic
and `model` names logged by the addon, confirming which upstream model fulfilled
the CLI request.

## Testing Proxy Configuration

Use the provided debug script to test your proxy setup:

```bash
# Set proxy environment variables
export HTTPS_PROXY=http://localhost:8888
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem

# Run the debug script
python examples/proxy_debug.py
```

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `HTTP_PROXY` | Proxy for HTTP requests | `http://proxy.company.com:8080` |
| `HTTPS_PROXY` | Proxy for HTTPS requests | `http://proxy.company.com:8080` |
| `ALL_PROXY` | Proxy for all protocols | `http://proxy.company.com:8080` |
| `REQUESTS_CA_BUNDLE` | Path to CA certificate bundle | `/path/to/ca-bundle.pem` |
| `SSL_CERT_FILE` | Alternative to REQUESTS_CA_BUNDLE | `/path/to/ca-bundle.pem` |
| `SSL_VERIFY` | Enable/disable SSL verification | `true` or `false` |

## Troubleshooting

### SSL Certificate Errors

If you see SSL certificate verification errors:

1. Ensure the proxy's CA certificate is properly installed
2. Verify the certificate path is correct
3. Check that the certificate file is readable

### Proxy Connection Errors

1. Verify the proxy is running and accessible
2. Check the proxy URL format (should be `http://` even for HTTPS proxying)
3. Ensure no firewall is blocking the connection

### No Traffic in Proxy

1. Verify environment variables are set correctly
2. Restart the server after setting environment variables
3. Check that the proxy is configured to intercept HTTPS traffic

## OpenAI Format Endpoints

When using tools like Aider that expect OpenAI-formatted e correct endpoint:


### Endpoint Differences

- **`/openai/v1/chat/completions`** - Reverse proxy endpoint that returns **Anthropic format**
- **`/cc/openai/v1/chat/completions`** - Claude Code SDK endpoint that returns **OpenAI format**

### Configuring Aider

To use Aider with the Claude Code Proxy, configure it to use the correct endpoint:

```bash
# Correct - Uses OpenAI format transformation
export OPENAI_API_BASE=http://localhost:8000/cc/openai/v1
aider

# Incorrect - Returns raw Anthropic format
# export OPENAI_API_BASE=http://localhost:8000/openai/v1
```

### Testing Endpoint Format

You can verify the endpoint format using the test script:

```bash
# This will show the difference between endpoints
python test_endpoint_difference.py
```

## Security Considerations

- **Never disable SSL verification in production**
- Only use proxy interception for debugging in development environments
- Be cautious with proxy credentials in environment variables
- Clear proxy settings when not debugging to avoid accidental traffic interception
