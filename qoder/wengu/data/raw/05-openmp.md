---
doc_id: 05-openmp
title: OpenMP 与共享内存编程
doc_type: 讲义
course: parallel-computing
language: zh
sections: 4
---

# OpenMP 与共享内存编程

## fork-join 执行模型

OpenMP 是**编译制导**的共享内存并行方案。写 `#pragma omp parallel` 就开一个线程组，离开这行作用域时线程组结束——这就是 fork-join。

```c
#pragma omp parallel num_threads(4)
{
    int tid = omp_get_thread_num();
    printf("hello from %d\n", tid);
}
```

三个必须建立的概念：

**团队（team）**：`parallel` 区域内的一组线程，有主线程（team 0）和若干工作线程。组内线程数由 `num_threads` 子句或环境变量 `OMP_NUM_THREADS` 决定。

**并行区不等于分工。** 上面的代码里 4 个线程都执行 `printf`，只是各打各的。要分工，得再加 `#pragma omp for`（循环分配）或 `#pragma omp sections`（任务分配）。

**串行区与并行区共享变量。** 默认情况下并行区外的变量在区内是 shared 的——这既是 OpenMP 的便利，也是所有 bug 的来源（见下一节）。

编译时别忘了开开关：GCC 用 `-fopenmp`，Intel 用 `-qopenmp`，Clang 用 `-fopenmp`。忘了加开关，pragma 会被当成注释静默忽略——**程序能跑、结果对、就是一个线程**，这是最容易被忽略的一类「并行没生效」。

## 数据作用域：private 与 shared

并行区内的变量默认分两类：**在区外声明的自动变量是 shared**，**循环变量和 `private` 子句列出的变量是 private**。

```c
int sum = 0;                       /* shared，危险 */
#pragma omp parallel for private(tmp)
for (int i = 0; i < n; i++) {
    double tmp = a[i] * b[i];      /* 每人一份，安全 */
    sum += tmp;                    /* 全打同一个 sum，竞争 */
}
```

这段代码慢且结果错。正确的写法用归约子句：

```c
#pragma omp parallel for reduction(+:sum) private(tmp)
```

`reduction(+:sum)` 让每个线程先用自己的私有副本累加，结束时再合并。这是 OpenMP 里最该背下来的子句。

几个容易踩的作用域陷阱：

- **循环变量 i 在 `parallel for` 里自动 private**，但你若手写 `#pragma omp parallel` 再用 `#pragma omp for` 分段，`i` 的行为就不一样了。
- **`private` 变量不继承初值。** 写成 `private(tmp)` 后，`tmp` 在区内是未初始化的随机值。要继承初值用 `firstprivate`。
- **`lastprivate`** 把最后一次迭代的值带回串行区，常用于「循环里算出的最后一个结果」。
- **指针是 shared 的，指针指向的内存也是 shared 的。** 声明 `private(p)` 只保护了指针本身，它指向的数组仍然共享——这是「以为是私有其实是共享」的经典误解。

## 竞争条件与同步手段

数据竞争的定义：两个线程访问同一内存位置、至少一个写、且没有同步。结果是未定义的，可能这次对、下次错、换台机器又对。

三种同步手段，代价依次升高：

**原子操作** `#pragma omp atomic`：只保护一条语句，通常编译成一条带 lock 前缀的指令。适合计数器、累加单个变量。不支持复杂表达式。

**临界区** `#pragma omp critical`：保护一段代码，同一时刻只有一个线程能进。代价是串行化，**临界区里绝不能放循环**——那是把并行改回串行。

**屏障** `#pragma omp barrier`：等所有线程到齐。`parallel for` 结束时隐含一次屏障，所以循环之间天然对齐。

判断该用哪个：能用 reduction 就别用 atomic，能用 atomic 就别用 critical，critical 里只放几行操作。

还有一类隐蔽的竞争：**伪共享**。两个线程写不同变量但同一条缓存行，程序正确但慢。`#pragma omp critical` 救不了它，只能靠 padding 或分块。

检测工具：`-fsanitize=thread`（ThreadSanitizer）。它能在运行时抓出大部分数据竞争，代价是慢 5 到 20 倍。调试阶段值得开，压测阶段关掉。

## 调度策略与负载均衡

`#pragma omp parallel for` 默认按 `schedule(static)` 把迭代切成 p 块，每线程一块。这在每次迭代代价相同时最优，代价不同时就会有人早收工有人干到天黑。

四种调度：

| 子句 | 分配方式 | 适用场景 |
|---|---|---|
| `static` | 开始时切好，不再变 | 每次迭代耗时均匀 |
| `static, chunk` | 切成 chunk 大小的块，轮转分配 | 耗时均匀但想改善缓存局部性 |
| `dynamic, chunk` | 谁空了谁领一块 | 迭代耗时差异大、不可预测 |
| `guided, chunk` | 块大小从大到小递减 | 差异大且想减少调度开销 |

`dynamic` 的 `chunk` 太小（比如 1）会让调度开销吃掉收益；太大则退化成静态。经验起点是 `dynamic, 8` 或 `dynamic, 16`，再调。

一个典型的错误场景：三角形循环，内层迭代次数随外层变化。用 `static` 时，拿到前几行的线程工作量最大，最后一行最小，负载严重不均。这时 `schedule(dynamic)` 能把时间拉平，实测常有 1.5 到 2 倍差距。

还有 `collapse(2)` 子句，把两层循环合并成一层再分配，能显著改善小循环体的并行度。前提是两层循环之间没有依赖。

最后提醒：**调度策略不影响正确性，只影响性能**。如果改调度后结果变了，说明存在数据竞争，先修竞争再谈调度。
