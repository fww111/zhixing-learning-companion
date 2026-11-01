# 第6章 动态规划

## 6.1 动态规划入门与记忆化搜索

动态规划（DP）适用于"最优子结构 + 重叠子问题"的问题：大问题的最优解可以由子问题的最优解合成，且子问题被反复计算。两种等价写法：**记忆化搜索**（递归 + 缓存）与**递推填表**。设计 DP 的固定四步：定义状态（`dp[i]` 表示什么）、列出转移方程、确定初始值、确定计算顺序与答案位置。

```cpp
// 爬楼梯：dp[i] = dp[i-1] + dp[i-2]
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<long long> dp(n + 1);
    dp[0] = 1;
    if (n >= 1) dp[1] = 1;
    for (int i = 2; i <= n; ++i) dp[i] = dp[i - 1] + dp[i - 2];
    cout << dp[n] << "\n";
    return 0;
}

// 记忆化搜索版本（语义与递推完全一致）
map<int, long long> memo;
long long climb(int n) {
    if (n <= 1) return 1;
    if (memo.count(n)) return memo[n];
    return memo[n] = climb(n - 1) + climb(n - 2);
}
```

把朴素递归的 `fib_slow`（O(2^n)）加一行缓存就变成 O(n)——这就是记忆化的力量。

**易错点**：状态定义含糊（`dp[i]` 到底是"以 i 结尾"还是"前 i 个"），转移方程随之全错；初始化遗漏边界（`dp[0]`）；求最大值时 `dp` 数组没有初始化为极小值。

## 6.2 线性DP：最长上升子序列与最长公共子序列

最长上升子序列（LIS）：`dp[i]` = 以 `a[i]` 结尾的 LIS 长度，转移 `dp[i] = max(dp[j]) + 1`（j < i 且 a[j] < a[i])，O(n²)；配合"维护每个长度的最小结尾值 + 二分"可优化到 O(n log n)。最长公共子序列（LCS）：`dp[i][j]` = a 前 i 个与 b 前 j 个的 LCS 长度，字符相等时 `dp[i][j] = dp[i-1][j-1] + 1`，否则取两侧较大者。

```cpp
// LCS：O(n*m)
#include <bits/stdc++.h>
using namespace std;

int main() {
    string a, b;
    cin >> a >> b;
    int n = a.size(), m = b.size();
    vector<vector<int>> dp(n + 1, vector<int>(m + 1, 0));
    for (int i = 1; i <= n; ++i)
        for (int j = 1; j <= m; ++j) {
            if (a[i - 1] == b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
            else dp[i][j] = max(dp[i - 1][j], dp[i][j - 1]);
        }
    cout << dp[n][m] << "\n";
    return 0;
}
```

**易错点**：下标错位——`dp[i]` 对应 `a[i-1]` 是最常见的 bug 来源；LIS 的 O(n log n) 版本里 `lower_bound` 与 `upper_bound` 的选择（严格上升用 `lower_bound`，非下降用 `upper_bound`）。

## 6.3 背包问题

01 背包：n 个物品各有重量 w 和价值 v，容量 W 的背包每个物品至多选一次，求最大价值。二维定义 `dp[i][j]` = 前 i 个物品、容量 j 的最大价值，转移 `dp[i][j] = max(dp[i-1][j], dp[i-1][j-w]+v)`；一维优化时**容量必须倒序枚举**，防止同一物品被选两次。完全背包（每个物品可选无限次）则**正序枚举**。

```cpp
// 01背包一维写法
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, W;
    cin >> n >> W;
    vector<long long> dp(W + 1, 0);
    for (int i = 0; i < n; ++i) {
        long long w, v;
        cin >> w >> v;
        for (int j = W; j >= w; --j)          // 倒序：保证每件物品只选一次
            dp[j] = max(dp[j], dp[j - w] + v);
    }
    cout << dp[W] << "\n";
    return 0;
}
```

三类背包口诀：01 背包倒序、完全背包正序、多重背包按数量二进制拆分后转 01 背包。

**易错点**：一维 01 背包写成正向枚举（等价于完全背包）；`j >= w` 的循环条件漏写导致下标为负；输出答案误以为一定是 `dp[W]`（有的题目要求恰好装满，需初始化 `-inf`）。

## 6.4 区间DP入门

区间 DP 的状态是区间 `[i, j]`：`dp[i][j]` 表示把该区间处理完的最优值，转移时枚举区间内的分割点 k：`dp[i][j] = min/max(dp[i][k] + dp[k+1][j] + cost(i,j))`。计算顺序按**区间长度从小到大**。经典题：石子合并、矩阵链乘法、戳气球。

```cpp
// 石子合并：每次合并相邻两堆，代价为两堆之和，求最小总代价
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<long long> s(n + 1, 0);              // 前缀和便于求区间和
    for (int i = 1; i <= n; ++i) { long long x; cin >> x; s[i] = s[i - 1] + x; }

    const long long INF = 1e18;
    vector<vector<long long>> dp(n + 1, vector<long long>(n + 1, 0));
    for (int len = 2; len <= n; ++len) {         // 枚举区间长度
        for (int i = 1; i + len - 1 <= n; ++i) {
            int j = i + len - 1;
            dp[i][j] = INF;
            long long cost = s[j] - s[i - 1];
            for (int k = i; k < j; ++k)          // 枚举分割点
                dp[i][j] = min(dp[i][j], dp[i][k] + dp[k + 1][j] + cost);
        }
    }
    cout << dp[1][n] << "\n";
    return 0;
}
```

**易错点**：枚举顺序写成按左右端点而漏掉短区间（必须先算所有长度为 len-1 的区间）；区间和每次现算是 O(n)，应使用前缀和。
