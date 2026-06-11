package com.example.androidplayground.demos.coroutines

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * 协程 Demo 的逻辑层
 * 所有的业务逻辑、线程切换、任务启动都在这里处理
 */
class CoroutinesDemoViewModel : ViewModel() {

    // 使用 StateFlow 来存储日志列表，UI 层会观察这个数据流
    private val _uiLog = MutableStateFlow<List<String>>(listOf("系统已就绪..."))
    val uiLog: StateFlow<List<String>> = _uiLog.asStateFlow()

    /**
     * 向控制台添加一条带线程信息的日志
     */
    private fun addLog(message: String) {
        val threadName = Thread.currentThread().name
        val newLog = "[$threadName] $message"
        
        // 更新状态流，UI 会自动收到通知
        _uiLog.update { currentLogs ->
            (listOf(newLog) + currentLogs).take(50) // 只保留最近50条
        }
    }

    // 6. 进阶挑战：搜索防抖逻辑
    private val _searchQuery = MutableStateFlow("")
    
    init {
        // 在初始化时设置监听
        viewModelScope.launch {
            _searchQuery
                .debounce(500)             // 1. 防抖：用户停止输入 500ms 后才触发
                .filter { it.isNotBlank() } // 2. 过滤：空字符串不搜索
                .distinctUntilChanged()    // 3. 去重：如果内容没变，不重复搜索
                .collect { query ->
                    performFakeSearch(query)
                }
        }
    }

    fun onSearchQueryChanged(newQuery: String) {
        _searchQuery.value = newQuery
    }

    private suspend fun performFakeSearch(query: String) {
        addLog("🔍 正在搜索: $query ...")
        delay(1000) // 模拟网络耗时
        addLog("✅ 搜索结果: 找到了关于 '$query' 的 10 条数据")
    }

    // 1. 基础启动示例
    fun runSimpleLaunch() {
        // viewModelScope 启动的协程会在 ViewModel 销毁时自动取消
        viewModelScope.launch {
            addLog("基础协程已启动")
            delay(1000) // 挂起 1 秒，不阻塞主线程
            addLog("基础协程执行完毕")
        }
    }

    // 2. 线程切换示例 (withContext)
    fun runDispatcherSwitch() {
        viewModelScope.launch {
            addLog("开始任务 (主线程)")
            
            // 使用 withContext 切换到 IO 线程执行耗时任务
            val result = withContext(Dispatchers.IO) {
                addLog("正在 IO 线程请求数据...")
                delay(2000) // 模拟网络耗时
                "【服务器数据】"
            }
            
            // 任务结束会自动回到主线程
            addLog("获取到结果: $result (已回到主线程)")
        }
    }

    // 3. 异步并发示例 (async/await)
    fun runAsyncAwait() {
        viewModelScope.launch {
            addLog("并发任务开始...")
            val startTime = System.currentTimeMillis()
            
            // 同时启动两个任务，不互相等待
            val task1 = async(Dispatchers.IO) {
                delay(1500)
                "用户信息"
            }
            val task2 = async(Dispatchers.IO) {
                delay(1000)
                "文章列表"
            }
            
            // 使用 await() 等待它们的结果
            val combinedResult = "${task1.await()} + ${task2.await()}"
            val duration = System.currentTimeMillis() - startTime
            addLog("任务完成: $combinedResult，耗时: ${duration}ms")
        }
    }

    // 4. 异常处理示例
    fun runErrorHandling() {
        // 定义一个专门处理异常的句柄
        val handler = CoroutineExceptionHandler { _, exception ->
            addLog("捕捉到异常: ${exception.localizedMessage}")
        }
        
        viewModelScope.launch(handler) {
            addLog("准备执行可能出错的任务...")
            delay(500)
            throw RuntimeException("网络连接异常！")
        }
    }

    // 5. Flow 操作符示例
    fun runFlowOperators() {
        viewModelScope.launch {
            addLog("Flow 数据流管道开始...")
            (1..5).asFlow()
                .onEach { delay(500) }     // 每个元素间隔 0.5 秒
                .map { it * 10 }           // 转换：乘以 10
                .filter { it > 25 }        // 过滤：只保留大于 25 的
                .collect { value ->        // 收集结果
                    addLog("收到 Flow 结果: $value")
                }
            addLog("Flow 管道结束")
        }
    }
}
