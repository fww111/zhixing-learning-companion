import json, httpx
def parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"): return json.loads(line[5:].strip())
    return json.loads(resp.text)
endpoints = {
  8100: "https://habitat-roommate-rush-privilege.trycloudflare.com",
  8101: "https://elementary-county-vendors-acquire.trycloudflare.com",
  8102: "https://bundle-connectors-revelation-trembl.trycloudflare.com",
}
for port, base in endpoints.items():
    try:
        r = httpx.post(f"{base}/mcp", headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},
            timeout=45, json={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
        tools = parse(r)["result"]["tools"]
        print(f"{port}: HTTP{r.status_code} {len(tools)} tools ->", [t["name"] for t in tools])
    except Exception as e:
        print(f"{port}: ERROR {type(e).__name__}: {str(e)[:200]}")