# 🚀 基础八股文核心指南 (资深/高级版)

本篇舍弃浅层定义，直击源码底层设计细节、系统选型权衡与生产环境实战坑点。

---

## 📦 专题一：集合框架 (ArrayList, HashMap & Android 极致优化)

### Q1: HashMap 的底层数据结构是如何演进的？
*   **JDK 1.7**：**数组 + 链表**。
*   **JDK 1.8+**：**数组 + 链表 + 红黑树**。
    *   **红黑树触发条件**：当单条链表长度 > 8 且 数组总长度 > 64 时，链表会转为红黑树。
    *   **设计初衷**：解决哈希碰撞极端情况下，查询效率从 O(n) 退化到 O(logn) 的性能问题。

### Q2: HashMap 是怎么决定数组位置的？（底层算法深挖）
这是一道体现底层功底的细节题，分为两步：

1.  **扰动函数 (hash 方法源码级分析)**：
    *   **源码**：`static final int hash(Object key) { int h; return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16); }`
    *   **核心动作**：将 `hashCode` 无符号右移 16 位，再与原 `hashCode` 进行 **异或 (XOR)** 运算。
    *   **深度原因 (Why)**：
        *   数组下标计算公式是 `(n-1) & hash`。如果数组长度 `n` 较小（如 16），那么只有哈希值的 **低 4 位** 参与了运算。
        *   如果没有扰动，只要低 4 位相同的 Key 都会发生碰撞，即使它们的高 16 位差异巨大。
        *   **异或的妙处**：通过右移 16 位并异或，强制让 **高位信息也参与到低位运算中**。这样即使数组很小，也能充分利用 Key 全部的哈希特征，极大降低了碰撞概率。

2.  **取模运算 (下标计算)**：
    *   源码：`(n - 1) & hash`。
    *   **为什么用 & 而不是 %**：因为 `n` 是 2 的幂次，位运算比数学取模快 10 倍以上。


### Q3: HashMap 的负载因子为什么是 0.75？
*   **数学依据**：基于 **泊松分布 (Poisson Distribution)**。在默认负载因子 0.75 下，哈希碰撞导致链表长度达到 8 的概率小于千万分之一。
*   **权衡**：0.75 是空间利用率与查询效率（时间开销）的最佳折中点。

### Q4: 既然有了 HashMap，Android 为什么要搞 `ArrayMap` 和 `SparseArray`？
*   **HashMap 的缺陷**：内存贪婪。每一个 Entry 都是一个 Node 对象。在大量小数据映射时，产生大量对象碎片，导致频繁 GC。
*   **SparseArray (Int -> Object)**：底层使用双数组 + 二分查找。完全干掉了 Node 对象，内存收益极大。
*   **ArrayMap (Object -> Object)**：同样是双数组 + 二分查找。内部维护了全局缓存池，极大减少内存抖动。

### Q5: ArrayList vs HashMap (物理内存布局差异)
*   **物理结构**：ArrayList 物理连续（数组），CPU 缓存友好；HashMap 物理分散（Node对象），由于指针跳转频繁，Cache Miss 概率高。
*   **扩容机制**：ArrayList 1.5 倍扩容（System.arraycopy 块搬移）；HashMap 2 倍扩容（需要极耗 CPU 的 Rehash）。
*   **Fail-Fast**：两者都通过 `modCount` 记录修改，在迭代中检测到不一致则抛出 `ConcurrentModificationException`。

---

## 💎 专题二：LiveData (深度原理解析)

### Q1: `postValue` 为什么会导致数据丢失？
*   **原理**：`postValue` 采用的是 **“数据合并（Conflation）”** 机制。内部只维护一个 `mPendingData`，主线程处理前，多次 post 只会保留最后一次的值。

### Q2: 什么是 LiveData 的“数据倒灌”？（★★★★★）
*   **根源**：LiveData 内部 `mVersion` 与观察者的 `mLastVersion` 不一致。新观察者初始版本为 -1，订阅时会立即触发一次过时数据的推送。
*   **解决方案**：SingleLiveEvent、反射修改版本号、或使用 `SharedFlow(replay=0)`。

---

## 🏗 专题三：ViewModel (深度存活机制)

### Q1: `SavedStateHandle` 是做什么的？
*   **场景**：处理系统内存不足导致的 **“进程被杀（Process Death）”**。利用 `onSaveInstanceState` 机制将数据持久化到 Bundle，实现进程重启后的数据恢复。

---

## 📬 专题四：Handler (消息机制的灵魂)

### Q1: `Looper.loop()` 是死循环，为什么不会卡死主线程？
*   **底层机制**：**Linux epoll**。线程被内核挂起了（`epoll_wait`），直到有 IO 事件或写入才被唤醒，不占用 CPU 忙等。

### Q2: 什么是同步屏障 (Sync Barrier)？
*   **场景**：UI 刷新（Vsync 信号）具有最高优先级。
*   **实现**：发送 `target == null` 的特殊消息，强制队列忽略同步消息，优先处理异步消息。

### Q3: `IdleHandler` 的妙用？
*   **场景**：用于 App 的**延迟加载**。在主线程空闲时初始化非核心组件，提升启动体验。

---

## 📊 专题五：原生 Android vs Flutter 绘制原理对比

### Q1: 为什么 Flutter 能在不同平台上保持高度的一致性？
*   **核心原因**：Flutter **绕过了系统原生 UI 组件 (OEM Widgets)**。
*   **详解**：原生 Android 依赖系统内置的 View 体系，受厂商和版本影响大。Flutter 则是自带渲染引擎（Skia/Impeller），直接在 GPU 提供的画布上进行像素级绘制。它把系统只当做一个提供“画布”和“输入事件”的窗口。

### Q2: 详细对比两者的渲染流水线？
1.  **原生 Android**：
    *   UI 线程构建 View 树 -> Measure/Layout -> 生成 DisplayList -> **RenderThread** 转化为 GPU 指令 -> **SurfaceFlinger** 合成。
    *   **瓶颈**：复杂的 View 层级会导致递归 Measure/Layout 耗时严重。
2.  **Flutter**：
    *   Widget 树 -> Element 树 -> **RenderObject 树** -> 生成 Layer -> **GPU 线程** 直接栅格化。
    *   **优势**：Widget 是轻量对象，Element 实现增量更新，路径更短，效率更高。

### Q3: 什么是“着色器卡顿” (Shader Jitter)？
*   **现象**：Flutter App 在第一次执行某个复杂动画时会出现掉帧。
*   **原因**：Skia 引擎需要即时编译 GLSL 着色器程序，这个过程占用 CPU 导致延迟。
*   **解决**：使用 **Impeller** 引擎（预编译着色器）彻底解决。

### Q4: 混合开发 (PlatformView) 的性能挑战？
*   由于需要将两个独立的渲染 Surface 进行“纹理合成”，这涉及到线程同步和显存开销，通常会导致 FPS 下降和内存增长。
