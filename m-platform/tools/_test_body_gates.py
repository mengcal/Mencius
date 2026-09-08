"""R10.4 体积闸门测试（终版-工具 随包交付，评审C/评审A"已实测可复验"口径）。
用法: python _test_body_gates.py   （宿主跑，目标 127.0.0.1:2024）
断言: vision 9MB→413（8MB 帽）/ codebuddy 3MB→413 / rag/query 3MB→413（2MB 帽）/ vision chunked 流→413。
"""
import json, re, urllib.request, urllib.error, http.client as _hc

ENV = open(r'D:\m\.env', encoding='utf-8').read()
vt = re.search(r'VISION_PROXY_TOKEN=([a-f0-9]+)', ENV).group(1)
pt = re.search(r'CODEBUDDY_PROXY_TOKEN=([a-f0-9]+)', ENV).group(1)
rt = re.search(r'RAG_PROXY_TOKEN=([a-f0-9]+)', ENV).group(1)
FAILS = []


def post(url, obj, hdrs, want=413):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', **hdrs})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        got = r.status
    except urllib.error.HTTPError as e:
        got = e.code
        try:
            e.read()
        except (ConnectionAbortedError, OSError):
            pass  # 413 断流=闸门生效
    tag = '✓' if got == want else '✗'
    if got != want:
        FAILS.append(url)
    print(f'{tag} {url.split("2024")[1]} -> {got} (期待{want})')


def chunked_post(path, keyhdr, keyval, blocks=6, want=413):
    conn = _hc.HTTPConnection('127.0.0.1', 2024, timeout=60)
    conn.putrequest('POST', path)
    conn.putheader('Content-Type', 'application/json')
    conn.putheader('Transfer-Encoding', 'chunked')
    conn.putheader(keyhdr, keyval)
    conn.endheaders()
    try:
        for _ in range(blocks):  # 6 × 2MB = 12MB 分块流（无 Content-Length）
            conn.send(b'200000\r\n' + b'A' * 0x200000 + b'\r\n')
        conn.send(b'0\r\n\r\n')
        got = conn.getresponse().status
    except (BrokenPipeError, ConnectionResetError):
        got = 'conn-reset(断流=闸门生效)'
    tag = '✓' if got in (want, 'conn-reset(断流=闸门生效)') else '✗'
    if tag == '✗':
        FAILS.append(path + ' chunked')
    print(f'{tag} {path} chunked -> {got}')


big9 = 'A' * 9_000_000    # > vision 8MB 帽
big3 = 'A' * 3_000_000    # > codebuddy/rag 2MB 帽
post('http://127.0.0.1:2024/vision', {'image_b64': big9, 'question': 'x'}, {'X-Proxy-Key': vt}, 413)
post('http://127.0.0.1:2024/codebuddy/chat/completions',
     {'model': 'Qwen/Qwen3.8-Flash-Next', 'messages': [{'role': 'user', 'content': big3}]},
     {'X-Proxy-Key': pt}, 413)
post('http://127.0.0.1:2024/rag/query', {'q_vec': [float(x) for x in range(4000)] * 600, 'k': 3},
     {'X-Proxy-Key': rt}, 413)
chunked_post('/vision', 'X-Proxy-Key', vt)

print('ALL GREEN' if not FAILS else f'FAILURES: {FAILS}')
raise SystemExit(0 if not FAILS else 1)
