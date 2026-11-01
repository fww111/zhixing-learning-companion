# 第5章 搜索算法

## 5.1 深度优先搜索DFS

DFS 沿一条路径走到底再回头，是"穷举所有可能"的系统性方法。它既可用于图的遍历（连通块、拓扑排序），也可用于解空间搜索（排列组合、路径方案）。实现上通常用递归：进入节点时标记，依次访问未访问的邻居，回溯时恢复现场。

```cpp
// 网格 DFS：统计连通块数量
#include <bits/stdc++.h>
using namespace std;

int n, m;
vector<string> grid;
vector<vector<bool>> vis;

void dfs(int x, int y) {
    if (x < 0 || x >= n || y < 0 || y >= m) return;
    if (vis[x][y] || grid[x][y] == '#') return;   // 越界/已访问/障碍
    vis[x][y] = true;
    dfs(x + 1, y); dfs(x - 1, y); dfs(x, y + 1); dfs(x, y - 1);
}

int main() {
    cin >> n >> m;
    grid.resize(n);
    vis.assign(n, vector<bool>(m, false));
    for (auto& row : grid) cin >> row;
    int blocks = 0;
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < m; ++j)
            if (!vis[i][j] && grid[i][j] != '#') { dfs(i, j); ++blocks; }
    cout << blocks << "\n";
    return 0;
}
```

每个节点的访问/标记顺序保证了 O(n+m) 的总复杂度：每个点、每条边只被处理常数次。

**易错点**：进入节点后忘记立刻标记 `vis`，导致同一节点被重复访问指数次；四方向数组 DX/DY 写错一个值。

## 5.2 回溯与剪枝

回溯 = DFS 遍历"决策树"：每一层做一个选择，递归下去，返回时撤销选择恢复现场。剪枝是在搜索前提前放弃注定失败的分支，是搜索算法能否通过时限的关键。常用剪枝：可行性剪枝（当前已不合法直接返回）、最优性剪枝（当前劣于已知最优解）、重复性剪枝（同层跳过相同元素）。

```cpp
// 全排列输出（回溯模板）
#include <bits/stdc++.h>
using namespace std;

int n;
vector<int> path;
vector<bool> used;

void backtrack(int depth) {
    if (depth == n) {                       // 到达叶子：输出一个解
        for (int x : path) cout << x << " ";
        cout << "\n";
        return;
    }
    for (int i = 1; i <= n; ++i) {
        if (used[i]) continue;              // 剪枝：已用过的跳过
        used[i] = true;
        path.push_back(i);                  // 做选择
        backtrack(depth + 1);               // 进入下一层
        path.pop_back();                    // 撤销选择
        used[i] = false;
    }
}

int main() { cin >> n; used.assign(n + 1, false); backtrack(0); return 0; }
```

**易错点**：忘记撤销（`pop_back`/`used=false`）导致状态污染；剪枝条件放错位置（应在进入下一层之前判断）；对无序集合枚举时同层重复元素未跳过，产生重复解。

## 5.3 广度优先搜索BFS

BFS 按层扩展：先访问起点，再依次访问距离为 1、2、3……的所有节点。用队列实现，天然保证"第一次到达某节点时步数最少"，因此无权图的最短路直接用 BFS。复杂度 O(n+m)。

```cpp
// 网格 BFS：从起点到终点的最少步数
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, m;
    cin >> n >> m;
    vector<string> grid(n);
    for (auto& row : grid) cin >> row;
    int sx, sy, tx, ty;
    cin >> sx >> sy >> tx >> ty;   // 0-based

    vector<vector<int>> dist(n, vector<int>(m, -1));
    queue<pair<int, int>> q;
    q.push({sx, sy});
    dist[sx][sy] = 0;
    int dx[] = {1, -1, 0, 0}, dy[] = {0, 0, 1, -1};

    while (!q.empty()) {
        auto [x, y] = q.front(); q.pop();
        for (int k = 0; k < 4; ++k) {
            int nx = x + dx[k], ny = y + dy[k];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
            if (dist[nx][ny] != -1 || grid[nx][ny] == '#') continue;
            dist[nx][ny] = dist[x][y] + 1;      // 入队即定距离
            q.push({nx, ny});
        }
    }
    cout << dist[tx][ty] << "\n";               // -1 表示不可达
    return 0;
}
```

**易错点**：入队时不立即标记 `dist`，同一节点被多次入队导致复杂度退化甚至死循环；把 BFS 用于带边权的图（第一次到达不再保证最短，需 Dijkstra）。

## 5.4 BFS求最短路

在无权图上，BFS 求最短路只需记录 `dist` 数组；若还要求具体路径，为每个节点记录前驱 `prev`，终点回溯即可。多源 BFS（多个起点同时入队）求"每个点到最近的某个源的距离"也是高频套路，初始化时把所有源点距离置 0 一并入队。

```cpp
// 多源 BFS：01 矩阵中每个 0 到最近 1 的距离
vector<vector<int>> multi_source_bfs(const vector<vector<int>>& g) {
    int n = g.size(), m = g[0].size();
    vector<vector<int>> dist(n, vector<int>(m, -1));
    queue<pair<int, int>> q;
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < m; ++j)
            if (g[i][j] == 1) { dist[i][j] = 0; q.push({i, j}); }
    int dx[] = {1, -1, 0, 0}, dy[] = {0, 0, 1, -1};
    while (!q.empty()) {
        auto [x, y] = q.front(); q.pop();
        for (int k = 0; k < 4; ++k) {
            int nx = x + dx[k], ny = y + dy[k];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m || dist[nx][ny] != -1) continue;
            dist[nx][ny] = dist[x][y] + 1;
            q.push({nx, ny});
        }
    }
    return dist;
}
```

**易错点**：多源 BFS 时逐个源跑单源 BFS，复杂度爆炸；路径还原时从终点回溯要用 `prev` 链并反转，直接顺序输出会倒序。
