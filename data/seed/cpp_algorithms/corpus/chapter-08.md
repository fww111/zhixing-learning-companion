# 第8章 贪心与高级数据结构

## 8.1 贪心算法与交换论证

贪心在每一步都选当前最优的局部解，期望合成全局最优解。贪心正确性的标准证明方法之一是**交换论证**：假设存在最优解与贪心解不同，把最优解中的选择逐步交换成贪心的选择而不使结果变差，从而证明贪心解也是最优解。贪心没有固定模板，选对"贪心策略"是核心：常见排序依据有截止时间、区间右端点、性价比等。

```cpp
// 找零问题（面值体系下贪心正确）：优先用大面值
#include <bits/stdc++.h>
using namespace std;

int main() {
    long long amount;
    cin >> amount;
    int coins[] = {50, 20, 10, 5, 1};
    int cnt = 0;
    for (int c : coins) {
        cnt += amount / c;
        amount %= c;
    }
    cout << cnt << "\n";
    return 0;
}
```

**易错点**：不证明直接贪。经典反例：面值 {1, 3, 4} 凑 6，贪心得 4+1+1（3枚），最优是 3+3（2枚）——面值体系不满足贪心性质时必须改用 DP。

## 8.2 经典贪心问题：区间调度

区间调度问题：给定 n 个区间，选出最多的互不重叠的区间。正确策略是**按右端点排序，每次选结束最早的**——给后面留出最多的空间。交换论证：设最优解第一个区间与贪心不同，把最优解第一个区间换成贪心那个（结束更早），后续区间全部仍然可用，最优性保持。

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<pair<long long, long long>> seg(n);   // {右端点, 左端点}
    for (auto& s : seg) cin >> s.second >> s.first;
    sort(seg.begin(), seg.end());                // 按右端点排序

    long long last_end = -1e18;
    int cnt = 0;
    for (auto [r, l] : seg) {
        if (l >= last_end) { ++cnt; last_end = r; }   // 选区间：左端点不早于上次结束
    }
    cout << cnt << "\n";
    return 0;
}
```

相关变体：用最少的点刺破所有区间（按右端点排序放点）、无重叠区间要删除的最少个数（n - 最多保留数）。

**易错点**：按左端点或按长度排序都是错的（可构造反例）；端点相接算不算重叠要读清题意（`l >= last_end` 还是 `l > last_end`）。

## 8.3 并查集

并查集（DSU）维护"元素分属哪些集合"，支持两个近乎 O(1) 的操作：`find`（找代表元）与 `unite`（合并两个集合）。两个关键优化：**路径压缩**（find 时把沿途节点直接挂到根）与**按秩/大小合并**（小树挂大树），两者结合的复杂度近似 O(α(n))。典型应用：连通性判定、Kruskal 判环、离线处理动态连通。

```cpp
#include <bits/stdc++.h>
using namespace std;

struct DSU {
    vector<int> f, sz;
    DSU(int n) : f(n + 1), sz(n + 1, 1) { iota(f.begin(), f.end(), 0); }
    int find(int x) { return f[x] == x ? x : f[x] = find(f[x]); }  // 路径压缩
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (sz[a] < sz[b]) swap(a, b);       // 按大小合并
        f[b] = a; sz[a] += sz[b];
        return true;
    }
    bool same(int a, int b) { return find(a) == find(b); }
};

int main() {
    int n, q;
    cin >> n >> q;
    DSU dsu(n);
    while (q--) {
        int op, a, b;
        cin >> op >> a >> b;
        if (op == 1) dsu.unite(a, b);
        else cout << (dsu.same(a, b) ? "Y" : "N") << "\n";
    }
    return 0;
}
```

**易错点**：`find` 写成循环却没压缩，或递归不压缩导致链状结构退化成 O(n)；判断同一集合时错误地直接比较 `f[a] == f[b]`（必须先各自 find 到根）。

## 8.4 树状数组与线段树

树状数组（Fenwick）在 O(log n) 内完成**单点修改 + 前缀和查询**，核心是下标 `lowbit(i) = i & (-i)` 的跳转。线段树更通用：单点/区间修改 + 区间求和/最值，O(log n)，需要 `pushup/pushdown`（懒标记）实现。它们是"修改与查询交替出现"场景的标准答案，也是各类进阶结构（主席树、树链剖分）的基础。

```cpp
// 树状数组：单点加 + 前缀和
#include <bits/stdc++.h>
using namespace std;

struct BIT {
    int n;
    vector<long long> t;
    BIT(int n) : n(n), t(n + 1, 0) {}
    void add(int i, long long v) {
        for (; i <= n; i += i & (-i)) t[i] += v;
    }
    long long query(int i) {              // 前缀 [1, i] 的和
        long long s = 0;
        for (; i > 0; i -= i & (-i)) s += t[i];
        return s;
    }
};

int main() {
    int n, q;
    cin >> n >> q;
    BIT bit(n);
    for (int i = 1; i <= n; ++i) {
        long long x;
        cin >> x;
        bit.add(i, x);
    }
    while (q--) {
        int op, a;
        long long b;
        cin >> op >> a >> b;
        if (op == 1) bit.add(a, b);
        else cout << bit.query((int)b) - bit.query(a - 1) << "\n";  // 区间 [a, b]
    }
    return 0;
}
```

**易错点**：`lowbit` 写成 `i & ~i` 或忘记负数补码技巧；线段树开的空间不足（需要 4n）；区间更新不下传懒标记导致查询结果错；差分 + 树状数组可做"区间修改、单点查询"，不要为它上整套线段树。
