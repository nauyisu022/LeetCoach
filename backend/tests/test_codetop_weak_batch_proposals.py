from app.ai_test_enhancer import validate_test_code
from app.judge import run_submission
from test_proposals.codetop_weak_batch import PROPOSALS


REFERENCE_SOLUTIONS = {
    "lru-cache": (
        "LRUCache",
        """
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self.data:
            return -1
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, key: int, value: int) -> None:
        if self.capacity <= 0:
            return
        if key in self.data:
            self.data.move_to_end(key)
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
""",
    ),
    "min-stack": (
        "MinStack",
        """
class MinStack:
    def __init__(self):
        self.values = []
        self.minimums = []

    def push(self, val: int) -> None:
        self.values.append(val)
        self.minimums.append(val if not self.minimums else min(val, self.minimums[-1]))

    def pop(self) -> None:
        self.values.pop()
        self.minimums.pop()

    def top(self) -> int:
        return self.values[-1]

    def getMin(self) -> int:
        return self.minimums[-1]
""",
    ),
    "implement-trie-prefix-tree": (
        "Trie",
        """
class Trie:
    def __init__(self):
        self.root = {}

    def insert(self, word: str) -> None:
        node = self.root
        for char in word:
            node = node.setdefault(char, {})
        node['#'] = True

    def search(self, word: str) -> bool:
        node = self.root
        for char in word:
            if char not in node:
                return False
            node = node[char]
        return '#' in node

    def startsWith(self, prefix: str) -> bool:
        node = self.root
        for char in prefix:
            if char not in node:
                return False
            node = node[char]
        return True
""",
    ),
    "implement-stack-using-queues": (
        "MyStack",
        """
from collections import deque

class MyStack:
    def __init__(self):
        self.q = deque()

    def push(self, x: int) -> None:
        self.q.append(x)
        for _ in range(len(self.q) - 1):
            self.q.append(self.q.popleft())

    def pop(self) -> int:
        return self.q.popleft()

    def top(self) -> int:
        return self.q[0]

    def empty(self) -> bool:
        return not self.q
""",
    ),
    "implement-queue-using-stacks": (
        "MyQueue",
        """
class MyQueue:
    def __init__(self):
        self.input = []
        self.output = []

    def push(self, x: int) -> None:
        self.input.append(x)

    def _move(self):
        if not self.output:
            while self.input:
                self.output.append(self.input.pop())

    def pop(self) -> int:
        self._move()
        return self.output.pop()

    def peek(self) -> int:
        self._move()
        return self.output[-1]

    def empty(self) -> bool:
        return not self.input and not self.output
""",
    ),
    "find-median-from-data-stream": (
        "MedianFinder",
        """
from bisect import insort

class MedianFinder:
    def __init__(self):
        self.values = []

    def addNum(self, num: int) -> None:
        insort(self.values, num)

    def findMedian(self) -> float:
        n = len(self.values)
        mid = n // 2
        if n % 2:
            return float(self.values[mid])
        return (self.values[mid - 1] + self.values[mid]) / 2
""",
    ),
    "remove-invalid-parentheses": (
        "Solution().removeInvalidParentheses",
        """
class Solution:
    def removeInvalidParentheses(self, s: str):
        def valid(value):
            balance = 0
            for char in value:
                if char == '(':
                    balance += 1
                elif char == ')':
                    balance -= 1
                    if balance < 0:
                        return False
            return balance == 0

        level = {s}
        while True:
            answer = [value for value in level if valid(value)]
            if answer:
                return answer
            level = {
                value[:i] + value[i + 1:]
                for value in level
                for i, char in enumerate(value)
                if char in '()'
            }
""",
    ),
    "lfu-cache": (
        "LFUCache",
        """
from collections import defaultdict, OrderedDict

class LFUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.size = 0
        self.min_freq = 0
        self.key_to_value_freq = {}
        self.freq_to_keys = defaultdict(OrderedDict)

    def _touch(self, key):
        value, freq = self.key_to_value_freq[key]
        del self.freq_to_keys[freq][key]
        if not self.freq_to_keys[freq] and self.min_freq == freq:
            self.min_freq += 1
        self.freq_to_keys[freq + 1][key] = None
        self.key_to_value_freq[key] = (value, freq + 1)

    def get(self, key: int) -> int:
        if key not in self.key_to_value_freq:
            return -1
        self._touch(key)
        return self.key_to_value_freq[key][0]

    def put(self, key: int, value: int) -> None:
        if self.capacity <= 0:
            return
        if key in self.key_to_value_freq:
            self.key_to_value_freq[key] = (value, self.key_to_value_freq[key][1])
            self._touch(key)
            return
        if self.size == self.capacity:
            old_key, _ = self.freq_to_keys[self.min_freq].popitem(last=False)
            del self.key_to_value_freq[old_key]
            self.size -= 1
        self.key_to_value_freq[key] = (value, 1)
        self.freq_to_keys[1][key] = None
        self.min_freq = 1
        self.size += 1
""",
    ),
    "design-hashmap": (
        "MyHashMap",
        """
class MyHashMap:
    def __init__(self):
        self.data = {}

    def put(self, key: int, value: int) -> None:
        self.data[key] = value

    def get(self, key: int) -> int:
        return self.data.get(key, -1)

    def remove(self, key: int) -> None:
        self.data.pop(key, None)
""",
    ),
}


def test_codetop_weak_batch_proposals_validate():
    assert set(PROPOSALS) == set(REFERENCE_SOLUTIONS)
    for task_id, proposal in PROPOSALS.items():
        result = validate_test_code(proposal["test_code"])
        assert result.ok, (task_id, result.errors)
        assert result.assertion_count >= 2


def test_codetop_weak_batch_proposals_pass_reference_solutions():
    for task_id, proposal in PROPOSALS.items():
        entry_point, code = REFERENCE_SOLUTIONS[task_id]
        result = run_submission(
            prompt="from typing import *",
            code=code,
            test_code=proposal["test_code"],
            entry_point=entry_point,
        )
        assert result.passed, (task_id, result.failed_assertion, result.stderr)
