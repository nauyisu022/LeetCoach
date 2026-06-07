from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicDefinition:
    name: str
    label: str
    category: str
    category_label: str
    aliases: tuple[str, ...]


TOPIC_CATEGORIES = [
    ("core-structures", "基础数据结构"),
    ("linear-structures", "线性结构"),
    ("tree-graph", "树与图"),
    ("algorithm-patterns", "算法范式"),
    ("dynamic-programming", "动态规划"),
    ("search-enumeration", "搜索与枚举"),
    ("sorting-selection", "排序与选择"),
    ("range-data-structures", "区间与高级结构"),
    ("string-algorithms", "字符串算法"),
    ("math-bit", "数学与位运算"),
    ("engineering", "工程与交互"),
]


TOPIC_DEFINITIONS = [
    TopicDefinition("Array", "数组", "core-structures", "基础数据结构", ("Array", "数组")),
    TopicDefinition("Matrix", "矩阵", "core-structures", "基础数据结构", ("Matrix",)),
    TopicDefinition("Hash Table", "哈希表", "core-structures", "基础数据结构", ("Hash Table", "哈希表")),
    TopicDefinition("String", "字符串", "core-structures", "基础数据结构", ("String", "字符串")),
    TopicDefinition("Counting", "计数", "core-structures", "基础数据结构", ("Counting",)),
    TopicDefinition("Linked List", "链表", "linear-structures", "线性结构", ("Linked List", "链表")),
    TopicDefinition("Doubly Linked List", "双向链表", "linear-structures", "线性结构", ("双向链表",)),
    TopicDefinition("Stack", "栈", "linear-structures", "线性结构", ("Stack", "栈")),
    TopicDefinition("Queue", "队列", "linear-structures", "线性结构", ("Queue", "队列")),
    TopicDefinition("Heap (Priority Queue)", "堆 / 优先队列", "linear-structures", "线性结构", ("Heap (Priority Queue)", "堆（优先队列）")),
    TopicDefinition("Data Stream", "数据流", "linear-structures", "线性结构", ("数据流",)),
    TopicDefinition("Tree", "树", "tree-graph", "树与图", ("Tree",)),
    TopicDefinition("Binary Tree", "二叉树", "tree-graph", "树与图", ("Binary Tree",)),
    TopicDefinition("Binary Search Tree", "二叉搜索树", "tree-graph", "树与图", ("Binary Search Tree",)),
    TopicDefinition("Graph", "图", "tree-graph", "树与图", ("Graph",)),
    TopicDefinition("Trie", "字典树", "tree-graph", "树与图", ("Trie", "字典树")),
    TopicDefinition("Union Find", "并查集", "tree-graph", "树与图", ("Union Find",)),
    TopicDefinition("Topological Sort", "拓扑排序", "tree-graph", "树与图", ("Topological Sort",)),
    TopicDefinition("Shortest Path", "最短路", "tree-graph", "树与图", ("Shortest Path",)),
    TopicDefinition("Minimum Spanning Tree", "最小生成树", "tree-graph", "树与图", ("Minimum Spanning Tree",)),
    TopicDefinition("Eulerian Circuit", "欧拉回路", "tree-graph", "树与图", ("Eulerian Circuit",)),
    TopicDefinition("Strongly Connected Component", "强连通分量", "tree-graph", "树与图", ("Strongly Connected Component",)),
    TopicDefinition("Biconnected Component", "双连通分量", "tree-graph", "树与图", ("Biconnected Component",)),
    TopicDefinition("Binary Search", "二分查找", "algorithm-patterns", "算法范式", ("Binary Search",)),
    TopicDefinition("Two Pointers", "双指针", "algorithm-patterns", "算法范式", ("Two Pointers", "双指针")),
    TopicDefinition("Sliding Window", "滑动窗口", "algorithm-patterns", "算法范式", ("Sliding Window",)),
    TopicDefinition("Prefix Sum", "前缀和", "algorithm-patterns", "算法范式", ("Prefix Sum",)),
    TopicDefinition("Greedy", "贪心", "algorithm-patterns", "算法范式", ("Greedy",)),
    TopicDefinition("Simulation", "模拟", "algorithm-patterns", "算法范式", ("Simulation",)),
    TopicDefinition("Line Sweep", "扫描线", "algorithm-patterns", "算法范式", ("Line Sweep",)),
    TopicDefinition("Divide and Conquer", "分治", "algorithm-patterns", "算法范式", ("Divide and Conquer",)),
    TopicDefinition("Recursion", "递归", "algorithm-patterns", "算法范式", ("Recursion",)),
    TopicDefinition("Dynamic Programming", "动态规划", "dynamic-programming", "动态规划", ("Dynamic Programming",)),
    TopicDefinition("Memoization", "记忆化搜索", "dynamic-programming", "动态规划", ("Memoization",)),
    TopicDefinition("Depth-First Search", "深度优先搜索", "search-enumeration", "搜索与枚举", ("Depth-First Search",)),
    TopicDefinition("Breadth-First Search", "广度优先搜索", "search-enumeration", "搜索与枚举", ("Breadth-First Search", "广度优先搜索")),
    TopicDefinition("Backtracking", "回溯", "search-enumeration", "搜索与枚举", ("Backtracking", "回溯")),
    TopicDefinition("Enumeration", "枚举", "search-enumeration", "搜索与枚举", ("Enumeration",)),
    TopicDefinition("Sorting", "排序", "sorting-selection", "排序与选择", ("Sorting", "排序")),
    TopicDefinition("Merge Sort", "归并排序", "sorting-selection", "排序与选择", ("Merge Sort",)),
    TopicDefinition("Counting Sort", "计数排序", "sorting-selection", "排序与选择", ("Counting Sort",)),
    TopicDefinition("Bucket Sort", "桶排序", "sorting-selection", "排序与选择", ("Bucket Sort",)),
    TopicDefinition("Radix Sort", "基数排序", "sorting-selection", "排序与选择", ("Radix Sort",)),
    TopicDefinition("Quickselect", "快速选择", "sorting-selection", "排序与选择", ("Quickselect",)),
    TopicDefinition("Segment Tree", "线段树", "range-data-structures", "区间与高级结构", ("Segment Tree",)),
    TopicDefinition("Binary Indexed Tree", "树状数组", "range-data-structures", "区间与高级结构", ("Binary Indexed Tree",)),
    TopicDefinition("Ordered Set", "有序集合", "range-data-structures", "区间与高级结构", ("Ordered Set",)),
    TopicDefinition("Monotonic Stack", "单调栈", "range-data-structures", "区间与高级结构", ("Monotonic Stack",)),
    TopicDefinition("Monotonic Queue", "单调队列", "range-data-structures", "区间与高级结构", ("Monotonic Queue",)),
    TopicDefinition("String Matching", "字符串匹配", "string-algorithms", "字符串算法", ("String Matching",)),
    TopicDefinition("Rolling Hash", "滚动哈希", "string-algorithms", "字符串算法", ("Rolling Hash",)),
    TopicDefinition("Hash Function", "哈希函数", "string-algorithms", "字符串算法", ("Hash Function", "哈希函数")),
    TopicDefinition("Suffix Array", "后缀数组", "string-algorithms", "字符串算法", ("Suffix Array",)),
    TopicDefinition("Math", "数学", "math-bit", "数学与位运算", ("Math",)),
    TopicDefinition("Number Theory", "数论", "math-bit", "数学与位运算", ("Number Theory",)),
    TopicDefinition("Combinatorics", "组合数学", "math-bit", "数学与位运算", ("Combinatorics",)),
    TopicDefinition("Probability and Statistics", "概率统计", "math-bit", "数学与位运算", ("Probability and Statistics",)),
    TopicDefinition("Geometry", "几何", "math-bit", "数学与位运算", ("Geometry",)),
    TopicDefinition("Game Theory", "博弈论", "math-bit", "数学与位运算", ("Game Theory",)),
    TopicDefinition("Bit Manipulation", "位运算", "math-bit", "数学与位运算", ("Bit Manipulation",)),
    TopicDefinition("Bitmask", "状态压缩 / 位掩码", "math-bit", "数学与位运算", ("Bitmask",)),
    TopicDefinition("Brainteaser", "脑筋急转弯", "math-bit", "数学与位运算", ("Brainteaser",)),
    TopicDefinition("Randomized", "随机化", "math-bit", "数学与位运算", ("Randomized",)),
    TopicDefinition("Design", "设计", "engineering", "工程与交互", ("Design", "设计")),
    TopicDefinition("Concurrency", "并发", "engineering", "工程与交互", ("Concurrency",)),
    TopicDefinition("Interactive", "交互题", "engineering", "工程与交互", ("Interactive",)),
]

TOPIC_BY_NAME = {topic.name: topic for topic in TOPIC_DEFINITIONS}
TOPIC_BY_ALIAS = {alias: topic for topic in TOPIC_DEFINITIONS for alias in topic.aliases}
CATEGORY_ORDER = {name: index for index, (name, _) in enumerate(TOPIC_CATEGORIES)}


def topic_aliases(name: str) -> tuple[str, ...]:
    topic = TOPIC_BY_NAME.get(name) or TOPIC_BY_ALIAS.get(name)
    if not topic:
        return (name,)
    return topic.aliases


def normalize_topic_name(raw_name: str) -> str:
    return (TOPIC_BY_ALIAS.get(raw_name) or TOPIC_BY_NAME.get(raw_name) or TopicDefinition(raw_name, raw_name, "other", "其他", (raw_name,))).name


def topic_label(raw_name: str) -> str:
    topic = TOPIC_BY_ALIAS.get(raw_name) or TOPIC_BY_NAME.get(raw_name)
    return topic.label if topic else raw_name


def display_topic_labels(raw_names: list[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_names:
        key = normalize_topic_name(raw_name)
        if key in seen:
            continue
        seen.add(key)
        labels.append(topic_label(raw_name))
    return labels
