import json, httpx
def parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"): return json.loads(line[5:].strip())
    return json.loads(resp.text)
def tools(port):
    r = httpx.post(f"http://127.0.0.1:{port}/mcp", headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},
        timeout=20, json={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
    return parse(r)["result"]["tools"]
for port,label in [(8100,"profile"),(8101,"graph"),(8102,"assessment")]:
    try:
        t = tools(port)
        print(f"{port} {label}: {len(t)} tools ->", [x["name"] for x in t])
    except Exception as e:
        print(f"{port} {label}: ERROR {e}")