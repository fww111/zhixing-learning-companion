# 第7章 图论基础

## 7.1 图的存储

图 G=(V, E) 由顶点与边构成，分为无向图与有向图，边可带权。三种常用存储方式：

- 邻接矩阵 `g[u][v]`：O(1) 查边，O(V²) 空间，适合稠密图与 Floyd。
- 邻接表 `vector<vector<int>> adj`（竞赛最常用）：O(V+E) 空间，遍历邻居方便。
- 边集数组：存边列表，Kruskal 等算法直接用。

带权图用 `vector<vector<pair<int,int>>>`，pair 存 `{邻居, 边权}`。n 个点 m 条边的无向图要记得正反各加一条边。

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, m;
    cin >> n >> m;
    vector<vector<pair<int, int>>> adj(n + 1);   // 1-based
    for (int i = 0; i < m; ++i) {
        int u, v, w;
        cin >> u >> v >> w;
        adj[u].push_back({v, w});                // 无向图：反向也要加
        adj[v].push_back({u, w});
    }
    for (int u = 1; u <= n; ++u)
        for (auto [v, w] : adj[u]) cout << u << "->" << v << " w=" << w << "\n";
    return 0;
}
```

**易错点**：无向图忘加反向边；1-based 与 0-based 混用导致越界；重边与自环未按题意处理。

## 7.2 图的遍历与连通性

图的 DFS/BFS 与网格版本一致，区别只是"邻居"来自邻接表。遍历一遍即可判断连通性、统计连通块个数；无向图中记录 `vis` 后，DFS 中访问到已标记邻居即发现环（更严谨可用 DFS 序+父节点法）。BFS/DFS 也用于二分图染色（相邻点异色）等判定。

```cpp
// 连通块计数（递归版 DFS，n 大时改用显式栈/ BFS）
void dfs(int u, const vector<vector<int>>& adj, vector<bool>& vis) {
    vis[u] = true;
    for (int v : adj[u])
        if (!vis[v]) dfs(v, adj, vis);
}

int count_components(int n, const vector<vector<int>>& adj) {
    vector<bool> vis(n + 1, false);
    int cnt = 0;
    for (int u = 1; u <= n; ++u)
        if (!vis[u]) { dfs(u, adj, vis); ++cnt; }
    return cnt;
}
```

**易错点**：递归深度过大爆栈（链状图），改用 BFS 或显式栈；遍历的是邻接表 `adj` 但循环边界写成 `m` 条边。

## 7.3 最短路算法

- **Dijkstra**：非负权图单源最短路，`priority_queue` 小根堆实现 O((n+m)log n)。核心：每次取出当前距离最小的点并松弛其邻居，已确定的点不再入队。
- **Bellman-Ford / SPFA**：可处理负权边，O(nm) / SPFA 队列优化；检测负环。
- **Floyd**：任意两点最短路，三重循环 O(n³)，适合 n ≤ 500 的稠密小图，注意 k 必须在最外层。

```cpp
// Dijkstra（堆优化）
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, m, s;
    cin >> n >> m >> s;
    vector<vector<pair<int, long long>>> adj(n + 1);
    for (int i = 0; i < m; ++i) {
        int u, v;
        long long w;
        cin >> u >> v >> w;
        adj[u].push_back({v, w});
    }
    const long long INF = 1e18;
    vector<long long> dist(n + 1, INF);
    priority_queue<pair<long long, int>, vector<pair<long long, int>>, greater<>> pq;
    dist[s] = 0;
    pq.push({0, s});
    while (!pq.empty()) {
        auto [d, u] = pq.top(); pq.pop();
        if (d > dist[u]) continue;              // 过期条目，跳过
        for (auto [v, w] : adj[u])
            if (dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                pq.push({dist[v], v});
            }
    }
    for (int u = 1; u <= n; ++u) cout << (dist[u] == INF ? -1 : dist[u]) << " \n"[u == n];
    return 0;
}
```

**易错点**：Dijkstra 用于有负权边（结果错误）；堆里过期条目不跳过导致超时；Floyd 的 k 放在内层（状态含义就错了）；松弛用 `int` 溢出。

## 7.4 最小生成树

最小生成树（MST）在无向连通图中选 n-1 条边使总权最小且图连通。两种经典算法：

- **Kruskal**：边按权排序，从小到大用并查集判环加入，O(m log m)，适合稀疏图。
- **Prim**：从任意点开始，每次选"连接树内外的最小边"，堆优化 O((n+m)log n)，适合稠密图。

```cpp
// Kruskal（配合并查集）
#include <bits/stdc++.h>
using namespace std;

struct DSU {
    vector<int> f;
    DSU(int n) : f(n + 1) { iota(f.begin(), f.end(), 0); }
    int find(int x) { return f[x] == x ? x : f[x] = find(f[x]); }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        f[a] = b;
        return true;
    }
};

int main() {
    int n, m;
    cin >> n >> m;
    vector<array<long long, 3>> edges(m);    // {w, u, v}
    for (auto& e : edges) cin >> e[1] >> e[2] >> e[0];
    sort(edges.begin(), edges.end());

    DSU dsu(n);
    long long total = 0;
    int used = 0;
    for (auto& [w, u, v] : edges)
        if (dsu.unite(u, v)) { total += w; if (++used == n - 1) break; }

    cout << (used == n - 1 ? to_string(total) : "not connected") << "\n";
    return 0;
}
```

**易错点**：图不连通时没有判断（应输出无解）；Kruskal 排序时按 u 排而非按 w 排；并查集未路径压缩导致退化。

## 7.5 拓扑排序

拓扑排序把 DAG（有向无环图）的顶点排成线性序列，使每条边 u→v 中 u 都排在 v 前面。Kahn 算法：维护每个点的入度，把入度为 0 的点入队，出队时把它指向的点入度减 1，减到 0 入队；若出队总数 < n，说明存在环。应用：任务依赖调度、DP 顺序（DAG 上最短路/最长路）。

```cpp
// Kahn 拓扑排序 + 环检测
vector<int> toposort(int n, const vector<vector<int>>& adj, vector<int> indeg) {
    queue<int> q;
    for (int u = 1; u <= n; ++u)
        if (indeg[u] == 0) q.push(u);
    vector<int> order;
    while (!q.empty()) {
        int u = q.front(); q.pop();
        order.push_back(u);
        for (int v : adj[u])
            if (--indeg[v] == 0) q.push(v);
    }
    return order;    // size() < n 时有环
}
```

**易错点**：加边时忘记给 v 的入度 +1；用普通 DFS 求拓扑序时结果需要逆序（DFS 完成顺序的逆序才是拓扑序）；图中必须无环，有环时应输出判定信息。
