# 第2章 基础数据结构

## 2.1 数组、前缀和与差分

数组是最基本的数据结构，支持下标随机访问 O(1)。在数组之上衍生出两个高频技巧：前缀和与差分，它们互为逆运算。

前缀和：设 `pre[i] = a[1] + ... + a[i]`，则区间 [l, r] 的和为 `pre[r] - pre[l-1]`，把每次区间求和从 O(n) 降到 O(1)，构建前缀和需要 O(n)。差分：设 `d[i] = a[i] - a[i-1]`，对区间 [l, r] 整体加 c 只需 `d[l] += c; d[r+1] -= c`，最后做一次前缀和还原，把每次区间修改从 O(n) 降到 O(1)。

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, q;
    cin >> n >> q;
    vector<long long> a(n + 1), pre(n + 1, 0);
    for (int i = 1; i <= n; ++i) cin >> a[i];
    for (int i = 1; i <= n; ++i) pre[i] = pre[i - 1] + a[i];

    while (q--) {                 // q 次区间求和，每次 O(1)
        int l, r;
        cin >> l >> r;
        cout << pre[r] - pre[l - 1] << "\n";
    }
    return 0;
}
```

**易错点**：
- 下标从 1 开始可以避免 `pre[l-1]` 中 l=0 的边界问题；从 0 开始则要小心 `-1` 下标。
- 前缀和数组要用 `long long`：10^5 个 10^9 的数累加必然超 `int`。
- 差分做"区间加"后忘记做前缀和还原。

## 2.2 栈与队列

栈（stack）是后进先出 LIFO 的线性结构，核心操作 `push/pop/top` 均为 O(1)；队列（queue）是先进先出 FIFO 结构，核心操作 `push/pop/front/back` 均为 O(1)。栈适合表达"最近匹配"和"回退"类问题（括号匹配、表达式求值、DFS 模拟），队列适合表达"按到达顺序处理"（BFS、任务排队）。

```cpp
#include <bits/stdc++.h>
using namespace std;

bool matched(const string& s) {      // 括号匹配：栈的经典应用
    stack<char> st;
    for (char c : s) {
        if (c == '(' || c == '[' || c == '{') st.push(c);
        else {
            if (st.empty()) return false;
            char t = st.top(); st.pop();
            if ((c == ')' && t != '(') || (c == ']' && t != '[') || (c == '}' && t != '{'))
                return false;
        }
    }
    return st.empty();
}

int main() {
    string s;
    cin >> s;
    cout << (matched(s) ? "matched" : "unmatched") << "\n";
    return 0;
}
```

**易错点**：`pop()` 不返回元素，取值必须先 `top()`/`front()` 再 `pop()`；匹配类问题结束时忘记检查栈是否为空（只剩左括号也算不匹配）。

## 2.3 单调栈

单调栈是栈的强化用法：栈内元素保持单调（递增或递减），新元素入栈前把破坏单调性的元素弹出。每个元素最多入栈、出栈各一次，因此总复杂度 O(n)。典型应用：对每个元素，找出左边/右边第一个比它大（或小）的元素位置，例如"柱状图中最大矩形""每日温度"。

```cpp
// 对每个 a[i]，求右边第一个比它大的元素的下标（不存在为 -1）
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<int> a(n + 1), ans(n + 1, -1);
    for (int i = 1; i <= n; ++i) cin >> a[i];

    stack<int> st;                        // 存下标，栈内值单调递减
    for (int i = 1; i <= n; ++i) {
        while (!st.empty() && a[i] > a[st.top()]) {
            ans[st.top()] = i;            // a[i] 是栈顶元素的答案
            st.pop();
        }
        st.push(i);
    }
    for (int i = 1; i <= n; ++i) cout << ans[i] << " \n"[i == n];
    return 0;
}
```

**易错点**：栈里存值而不是存下标，导致无法记录答案位置；单调方向想反（找"右边第一个更大"时栈内保持递减，新元素大于栈顶时弹栈）。

## 2.4 链表与双指针

链表通过指针把节点串起来，插入删除 O(1)，随机访问 O(n)。竞赛中更多使用数组模拟链表（`nxt[]`、`pre[]` 数组）或直接用 `std::list`。双指针是一类思想：维护两个同向或相向移动的下标，把暴力 O(n²) 的扫描优化到 O(n)，例如判断回文、合并有序数组、滑动窗口。

```cpp
// 同向双指针：找出和 >= target 的最短连续子数组长度
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    long long target;
    cin >> n >> target;
    vector<long long> a(n + 1);
    for (int i = 1; i <= n; ++i) cin >> a[i];

    int ans = INT_MAX;
    long long sum = 0;
    for (int l = 1, r = 1; r <= n; ++r) {   // 右指针扩窗
        sum += a[r];
        while (sum - a[l] >= target && l <= r) { sum -= a[l]; ++l; }  // 收缩
        if (sum >= target) ans = min(ans, r - l + 1);
    }
    cout << (ans == INT_MAX ? -1 : ans) << "\n";
    return 0;
}
```

**易错点**：双指针的单调性前提（右移 r 时答案单调变化）不成立时不能用；滑动窗口更新最值的时机放错（应在每个 r 处理完后更新）。

## 2.5 哈希表

哈希表以"键→值"的形式存储，平均插入、查找、删除都是 O(1)。C++ 中 `unordered_map/unordered_set` 基于哈希实现，`map/set` 基于红黑树实现且保持有序（单次 O(log n)）。哈希表最典型的应用是计数统计和"用 O(1) 判断某个东西是否出现过"，例如两数之和。

```cpp
// 两数之和：返回和为 target 的两个下标
#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    long long target;
    cin >> n >> target;
    unordered_map<long long, int> pos;   // 值 -> 下标
    int i1 = -1, i2 = -1;
    for (int i = 1; i <= n; ++i) {
        long long x;
        cin >> x;
        auto it = pos.find(target - x);
        if (it != pos.end()) { i1 = it->second; i2 = i; break; }
        pos[x] = i;
    }
    cout << i1 << " " << i2 << "\n";
    return 0;
}
```

**易错点**：
- 需要有序遍历或求"键的上一个/下一个"时必须用 `map`，`unordered_map` 无序。
- `unordered_map` 对自定义类型需要提供哈希函数，初学时容易忽略。
- 统计出现次数时先查询后插入的顺序写反导致漏计。
