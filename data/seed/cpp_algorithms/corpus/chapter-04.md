# 第4章 递归与分治

## 4.1 递归的设计与调用栈

递归是函数直接或间接调用自身。设计递归只需要回答三个问题：函数的功能定义（语义）、递归出口（base case）、如何把规模 n 的问题转化为规模更小的子问题（递推关系）。只要"每次调用规模严格变小且出口正确"，递归必然终止。

递归的运行依赖调用栈：每层调用保存局部变量与返回地址，深度为 O(n) 的递归占用 O(n) 栈空间。C++ 默认栈约 1~8MB，竞赛中深度上百万的递归会栈溢出，需要改写成显式栈或增大栈限制。

```cpp
// 阶乘：功能定义 fact(n)=n!，出口 fact(0)=1，转化 fact(n)=n*fact(n-1)
long long fact(int n) {
    if (n == 0) return 1;      // 出口
    return n * fact(n - 1);    // 缩小规模
}

// 经典陷阱：斐波那契朴素递归是 O(2^n)，因为大量子问题重复计算
long long fib_slow(int n) { return n < 2 ? n : fib_slow(n - 1) + fib_slow(n - 2); }
```

**易错点**：忘记写出口或出口不可达；递归参数不是"严格变小"（如 `f(n) = f(n) + 1`）导致无限递归；朴素递归重复计算指数爆炸（第6章的"记忆化"专门解决它）。

## 4.2 分治策略

分治（Divide and Conquer）三步走：**分解**——把问题分成若干规模更小的同类子问题；**解决**——递归求解子问题；**合并**——把子问题的解合成原问题的解。适用分治的标志是：分解容易、合并可行，且子问题相互独立。

主定理给出标准复杂度结论：T(n) = a·T(n/b) + f(n)。常用情形：T(n)=2T(n/2)+O(n) → O(n log n)（归并排序）；T(n)=2T(n/2)+O(1) → O(n)（树的遍历）；T(n)=T(n/2)+O(1) → O(log n)（二分）。

```cpp
// 分治求最大值：分解成两半，分别求 max，合并取较大者
int max_of(const vector<int>& a, int l, int r) {   // 区间 [l, r)
    if (r - l == 1) return a[l];
    int mid = (l + r) / 2;
    int left = max_of(a, l, mid);
    int right = max_of(a, mid, r);
    return max(left, right);
}
```

**易错点**：子问题重叠时用分治是浪费（如朴素斐波那契），应当记忆化或改用动态规划；合并步骤被忽略——只"分"不"合"得不到原问题的解。

## 4.3 归并排序与逆序对

逆序对定义为：i < j 但 a[i] > a[j] 的数对个数。暴力枚举是 O(n²)；用归并排序求逆序对是分治的经典组合应用，O(n log n)。关键洞察：合并两个有序段时，若右半的元素 a[j] 被取出，它比左半剩余的所有元素都小，此时左半剩余元素数即新增逆序对数。

```cpp
#include <bits/stdc++.h>
using namespace std;

long long merge_count(vector<int>& a, int l, int r) {
    if (r - l <= 1) return 0;
    int mid = (l + r) / 2;
    long long cnt = merge_count(a, l, mid) + merge_count(a, mid, r);
    vector<int> tmp;
    int i = l, j = mid;
    while (i < mid && j < r) {
        if (a[i] <= a[j]) tmp.push_back(a[i++]);
        else { cnt += mid - i; tmp.push_back(a[j++]); }   // 关键一行
    }
    while (i < mid) tmp.push_back(a[i++]);
    while (j < r) tmp.push_back(a[j++]);
    copy(tmp.begin(), tmp.end(), a.begin() + l);
    return cnt;
}

int main() {
    int n;
    cin >> n;
    vector<int> a(n);
    for (auto& x : a) cin >> x;
    cout << merge_count(a, 0, n) << "\n";
    return 0;
}
```

**易错点**：逆序对数量可达 n(n-1)/2 ≈ 5×10^9（n=10^5），必须用 `long long`；相等元素不算逆序对，比较时用 `<=` 保证稳定不重计。
