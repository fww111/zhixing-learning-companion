# 第3章 排序与二分

## 3.1 常见排序算法

排序是算法学习的分水岭。入门需要掌握：冒泡/选择/插入排序（O(n²)，帮助理解思想）、归并排序（O(n log n)，分治代表）、快速排序（平均 O(n log n)，原地分治）、计数排序（O(n+k)，值域小的时候线性）。

冒泡排序每轮把最大元素"冒"到末尾；插入排序像整理手牌，把新元素插入左侧有序段；归并排序"递归排序左右两半再合并"；快速排序"选基准划分两侧再递归"。考试和面试重点考察归并与快排的过程推导、稳定性与复杂度。

```cpp
// 归并排序：稳定，O(n log n)，需要 O(n) 辅助空间
void merge_sort(vector<int>& a, int l, int r) {
    if (r - l <= 1) return;
    int mid = (l + r) / 2;
    merge_sort(a, l, mid);
    merge_sort(a, mid, r);
    vector<int> tmp;
    int i = l, j = mid;
    while (i < mid && j < r)
        tmp.push_back(a[i] <= a[j] ? a[i++] : a[j++]);
    while (i < mid) tmp.push_back(a[i++]);
    while (j < r) tmp.push_back(a[j++]);
    copy(tmp.begin(), tmp.end(), a.begin() + l);
}
```

**易错点**：快排基准选择不当导致退化成 O(n²)（如对有序数组选最左元素为基准）；归并合并时两个 `while` 补尾漏写一个。

## 3.2 STL sort与自定义比较器

`std::sort` 是内省排序（快排+堆排+插入的混合），平均 O(n log n)，不保证稳定；需要稳定排序时用 `std::stable_sort`。自定义比较器有三种写法：普通函数、lambda 表达式、重载 `operator<` 的结构体。多关键字排序是高频考点：先比第一关键字，相同再比第二关键字。

```cpp
#include <bits/stdc++.h>
using namespace std;

struct Student { string name; int score; };

int main() {
    vector<Student> v = {{"alice", 90}, {"bob", 85}, {"carol", 90}};

    // 分数降序；分数相同按名字典序升序（多关键字排序）
    sort(v.begin(), v.end(), [](const Student& x, const Student& y) {
        if (x.score != y.score) return x.score > y.score;
        return x.name < y.name;
    });

    for (auto& s : v) cout << s.name << " " << s.score << "\n";
    return 0;
}
```

**易错点**：比较器必须满足严格弱序，写 `return x.score >= y.score` 在相等时返回 true 会导致运行时越界崩溃；结构体排序忘记用引用接收导致比较对象被复制（效率低）。

## 3.3 二分查找

二分查找在**有序**序列上每次把搜索范围减半，O(log n)。掌握三个 STL 函数后多数场景不需要手写：`binary_search`（判断存在）、`lower_bound`（第一个 >= x 的迭代器）、`upper_bound`（第一个 > x 的迭代器）。手写时必须固定一个模板并坚持使用，推荐"左闭右开"模板。

```cpp
// 左闭右开模板：在 [lo, hi) 中找第一个 >= x 的下标
int lower_bound_idx(const vector<int>& a, int lo, int hi, int x) {
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;   // 防溢出写法
        if (a[mid] >= x) hi = mid;      // 答案在 [lo, mid]
        else lo = mid + 1;              // 答案在 [mid+1, hi)
    }
    return lo;                          // 可能等于 hi，表示不存在
}
```

二分的正确性依赖两点：单调性（条件在某个位置后恒成立）与不变式（每次循环后答案仍在区间内）。写完二分用 n=1、n=2 的小数据验证一遍是性价比最高的调试手段。

**易错点**：
- `mid = (lo + hi) / 2` 在 lo+hi 超过 int 上限时溢出，应写 `lo + (hi - lo) / 2`。
- 死循环：`lo = mid` 且 `mid = (lo + hi) / 2` 向下取整，区间不缩小时死循环（用 `hi = mid` 或改为向上取整）。
- 对无序数组二分。

## 3.4 二分答案

二分答案是二分思想的迁移：如果"答案为 x 时判定函数成立"具有单调性（x 越大越容易/越难满足），就可以在答案值域上二分，把"求最小/最大满足条件的值"转化为 O(log V) 次 O(能判定) 的验证。典型题目：最小化最大值、最大化最小值（如"木板分割""跳石头""切分数组使最大和最小"）。

```cpp
// 把数组切成 m 段，最小化"各段和的最大值"
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, m;
    cin >> n >> m;
    vector<long long> a(n + 1);
    for (int i = 1; i <= n; ++i) cin >> a[i];

    auto check = [&](long long cap) {   // 段最大和不超过 cap 是否可行
        long long cur = 0;
        int seg = 1;
        for (int i = 1; i <= n; ++i) {
            if (a[i] > cap) return false;
            if (cur + a[i] > cap) { ++seg; cur = a[i]; }
            else cur += a[i];
        }
        return seg <= m;
    };

    long long lo = 0, hi = accumulate(a.begin(), a.end(), 0LL);
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2;
        if (check(mid)) hi = mid;       // 可行则尝试更小
        else lo = mid + 1;
    }
    cout << lo << "\n";
    return 0;
}
```

**易错点**：判定函数的单调性没验证就开始二分（不单调的二分答案是错的）；值域下界从 0 开始但元素本身可能大于 0 造成 check 永假——下界应设为 max(a[i])。
