---
doc_id: 04-collectives
title: MPI 集合通信
doc_type: 讲义
course: parallel-computing
language: zh
sections: 4
---

# MPI 集合通信

## 广播、散播与收集

集合通信是**通信子内所有进程**共同参与的操作。三个最常用的：

- `MPI_Bcast(buf, count, type, root, comm)`：root 的数据发给所有人。所有人调用时 `count` 和 `type` 要一致。
- `MPI_Scatter(sbuf, scount, stype, rbuf, rcount, rtype, root, comm)`：root 把数据切成 p 份，各拿一份。注意 root 的 `scount` 是**每份的长度**，不是总长度——这是最常见的参数错误。
- `MPI_Gather(rbuf, rcount, rtype, sbuf, scount, stype, root, comm)`：Scatter 的逆操作，各进程的数据汇聚到 root。

还有两个变体值得记住：`MPI_Allgather` 相当于 Gather 之后再做一次 Bcast，结果人人有份；`MPI_Alltoall` 是每对进程之间都交换一段，通信量是 O(p²)，p 上千时会成为瓶颈。

**Scatter/Gather 不等于「各发各的」。** 它们是优化过的实现，在内部用树形或流水线而不是 p 次点对点。手工用循环写 p 次 `MPI_Send`，性能通常差 2 到 5 倍，而且容易在 p 很大时死锁。

## 归约与 Allreduce

`MPI_Reduce(sbuf, rbuf, count, type, op, root, comm)` 把所有人的数据按 `op`（MPI_SUM、MPI_MAX、MPI_MIN、MPI_PROD 等）合并到 root。

`MPI_Allreduce` 做同样的事，但结果发给所有人。它比「Reduce 之后再 Bcast」快，因为实现把两步融合成了一棵树的两次遍历，省掉一次启动延迟。

一个容易忽略的点：**浮点归约的结果和顺序有关**。并行归约的加法顺序与串行不同，所以 `MPI_SUM` 的结果和串行求和**不会逐位相同**，差个 1e-15 是正常的。做严格回归测试时要留容差，不要用 `==` 比。

如果结果必须可复现（比如要写进论文的数值），有两个办法：固定归约的树形结构（有些实现提供确定的归约顺序），或者先 Gather 到 0 号进程再串行求和——后者放弃了并行归约的性能，但结果唯一。

用户自定义归约用 `MPI_Op_create` 注册函数。要求该操作**满足结合律**，因为实现可以按任意顺序组合。减法、除法不满足，用它做归约会得到随进程数变化的结果。

## 树形通信为什么比线性快

线性广播：root 依次发给 p−1 个进程，耗时 (p−1)·t。树形广播：每轮翻倍，耗时 ⌈log₂p⌉·t。

p = 1024 时，线性要 1023 步，树形只要 10 步。差两个数量级。

这个分析基于「延迟主导」模型（消息很小，时间花在启动上）。如果消息很大、带宽主导，线性反而可能更快，因为它能让多条链路并行传输不同片段。所以实际实现会在小消息用树、大消息用线性或分带（如 MPICH 的 Rabenseifner 算法对大消息先 Reduce-scatter 再 Allgather）。

**这解释了一个常见困惑**：为什么 `MPI_Allreduce` 在 4 字节时延迟几乎不随 p 变，而 4 MB 时却近似线性增长。前者是延迟受限、走树；后者是带宽受限、走分带。

写性能模型时把这两段分开拟合，比强行用一个公式拟合整条曲线准确得多。

## 集合通信的常见误用

**1. 在条件分支里调用。** 只有部分进程进入 `if (rank % 2 == 0) MPI_Bcast(...)`。集合通信要求通信子内全部进程参与，缺一个就挂死。判断条件必须是所有进程都能算出的、结果一致的量。

**2. 把集合通信当同步屏障用。** `MPI_Barrier` 确实是屏障，但集合通信本身不保证「所有进程都到了才开始」——它只保证语义正确。想同步就显式调 `MPI_Barrier`，别指望 `MPI_Allreduce` 顺带完成。

**3. 在小数据上反复调用。** 每次集合通信有固定启动开销（几微秒）。在循环里对单个 double 做 10 万次 `MPI_Allreduce`，时间全花在启动上。正确做法是先本地累加，最后归约一次。

**4. 忽略 Allreduce 的通信量。** `MPI_Allreduce` 每个进程要传输约 2·(p−1)/p·n 字节。n = 1 MB、p = 1024 时，单进程约 2 MB，看着不多；但全进程合计是约 2 GB 的网卡吞吐。设计算法时先算这个合计量，再决定要不要换成「本地归约 + 稀疏汇总」。

**5. 用 Gather 收集大数组。** root 的内存要装下 p 份数据，p = 1024、每份 100 MB 时 root 直接 OOM。这时应该让各进程自己写文件，或者用 `MPI_File` 并行 I/O。
