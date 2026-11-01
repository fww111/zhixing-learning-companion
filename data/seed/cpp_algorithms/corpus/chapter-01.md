# 第1章 算法与复杂度

## 1.1 什么是算法

算法是解决特定问题的一系列明确、有限的计算步骤。一个正确的算法必须满足：输入明确、每一步无歧义、在有限步骤内终止、对每一种合法输入都能得到正确输出。例如"在一个有序数组中查找某个数"，顺序扫描是一种算法，二分查找是另一种算法——它们解决同一个问题，但效率差距巨大。

在算法学习中，我们关心三个层次的问题：这个算法对不对（正确性）、这个算法有多快（时间效率）、这个算法要占多少空间（空间效率）。算法课的大部分内容，就是在"正确"的前提下，不断寻找更快的思路与更省的数据组织方式。

```cpp
// 一个最简单的算法：求 1..n 的和
#include <iostream>
int main() {
    long long n;
    std::cin >> n;
    long long sum = 0;
    for (long long i = 1; i <= n; ++i) sum += i;  // 逐项累加：O(n)
    std::cout << sum << std::endl;
    return 0;
}
```

同一个问题还有 O(1) 的解法：利用等差数列求和公式 `sum = n*(n+1)/2`。这说明"想到更好的算法"往往比"把代码写快"重要得多。

**易错点**：把"程序"和"算法"混为一谈。算法是解题思路的精确描述，程序只是算法在某种语言下的实现；同一算法可以有不同的实现细节，但步骤逻辑必须一致。

## 1.2 时间复杂度与大O表示法

时间复杂度用大O表示法描述算法运行时间随输入规模 n 增长的趋势，它忽略常数因子和低阶项，只保留增长最快的部分。常见记号有：O(1) 常数、O(log n) 对数、O(n) 线性、O(n log n) 线性对数、O(n²) 平方、O(2^n) 指数。

分析循环结构是最常用的技巧：单层 n 次循环是 O(n)；两层嵌套是 O(n²)；每次将问题规模减半的循环是 O(log n)；递归算法可以用递推式分析，如 T(n)=2T(n/2)+O(n) 解得 O(n log n)。

```cpp
// 三段代码，三种复杂度
for (int i = 0; i < n; ++i) sum += a[i];          // O(n)
for (int i = 0; i < n; ++i)
    for (int j = 0; j < n; ++j) cnt++;            // O(n^2)
for (int i = n; i > 1; i /= 2) cnt++;             // O(log n)
```

估算能否通过时限的经验法则：主流评测机 1 秒大约执行 10^8 ~ 10^9 次简单操作。若 n ≤ 10^5 而你的算法是 O(n²)，则约 10^10 次操作，必然超时，需要 O(n log n) 或更快的算法。

**易错点**：
- 认为大O代表"精确的运行时间"。O(n) 的算法不一定比 O(n²) 快（n 很小的时候），大O只描述增长趋势。
- 忽略隐藏在大O里的常数：同样是 O(n)，`std::sort` 内部的常数和手写冒泡的常数差异巨大。
- 把输入规模看错：两层循环 j 从 i 开始也常常是 O(n²)，不是 O(n)。

## 1.3 空间复杂度与常见复杂度类别

空间复杂度描述算法运行时额外占用的内存随输入规模的增长趋势，同样用大O表示。原地排序（如快速排序平均 O(log n) 栈空间）与需要辅助数组的排序（如归并排序 O(n)）是典型对比。竞赛中通常给出 64MB~256MB 内存限制，一个 `int` 数组开 10^7 约占 40MB，开数组前要估算。

常见复杂度类别与可处理的 n 范围（1秒时限的经验值）：

| 复杂度 | 典型算法 | 可处理的 n 量级 |
| --- | --- | --- |
| O(log n) | 二分查找 | 10^18 |
| O(n) | 前缀和、双指针 | 10^8 |
| O(n log n) | 排序、线段树 | 10^6 |
| O(n²) | 简单DP、 Floyd | 10^4 |
| O(n³) | 区间DP、矩阵乘法 | 500 |
| O(2^n) | 子集枚举、搜索剪枝 | 20~25 |
| O(n!) | 全排列搜索 | 10~11 |

```cpp
// 递归 depth = n，栈空间 O(n)：n 过大可能栈溢出
int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
```

**易错点**：只关注时间复杂度而忽略空间；在函数里按值传递大 vector 造成隐性 O(n) 复制，应传引用 `const vector<int>&`。

## 1.4 C++算法编程基础与STL总览

C++ 算法题的基本骨架是：读入数据、处理、输出。竞赛中优先使用 `std::cin/cout` 配合 `sync_with_stdio(false)` 或使用 `scanf/printf`，避免 `endl` 频繁刷新缓冲区。

STL（标准模板库）是算法竞赛的核心武器库：`vector`（动态数组）、`stack`、`queue`、`deque`、`priority_queue`（堆）、`set/map`（有序红黑树）、`unordered_set/unordered_map`（哈希表）、`sort/lower_bound/upper_bound` 等算法函数。熟练使用 STL 能把精力集中在算法思想上。

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;
    vector<int> a(n);
    for (auto& x : a) cin >> x;

    sort(a.begin(), a.end());                       // 排序 O(n log n)
    bool found = binary_search(a.begin(), a.end(), 5);
    auto it = lower_bound(a.begin(), a.end(), 5);   // 第一个 >= 5 的位置

    map<string, int> counter;                       // 有序映射
    counter["apple"] += 1;

    cout << (found ? "yes" : "no") << "\n";
    return 0;
}
```

**易错点**：
- `vector` 越界访问不报错但行为未定义，常见于循环边界写错。
- `unordered_map` 最坏单次操作 O(n)，被特殊数据卡常时换 `map`。
- 求和/乘积用 `int` 溢出：两个 10^5 相乘已超 `int` 范围，应使用 `long long`。
