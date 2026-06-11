package com.example.androidplayground.demos.coroutines

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.random.Random

/**
 * 模拟用户数据模型
 */
data class User(val id: Int, val name: String, val email: String)

/**
 * UI 状态封装：使用密封类处理 加载/成功/失败 三种状态
 */
sealed class UserListUiState {
    object Loading : UserListUiState()                                  // 加载中
    data class Success(val users: List<User>) : UserListUiState()       // 成功
    data class Error(val message: String) : UserListUiState()          // 失败
}

/**
 * 数据仓库层：负责真正的耗时操作
 */
class UserRepository {
    suspend fun fetchUsers(): List<User> = withContext(Dispatchers.IO) {
        delay(2000) // 模拟网络延迟
        
        // 模拟 30% 的请求失败率
        if (Random.nextInt(10) < 3) {
            throw RuntimeException("网络连接失败，请检查设置")
        }

        // 模拟返回 10 条数据
        List(10) { i ->
            User(i, "测试用户 $i", "user$i@example.com")
        }
    }
}

/**
 * 用户列表逻辑层
 */
class UserListViewModel : ViewModel() {
    private val repository = UserRepository()

    // 默认初始状态为“加载中”
    private val _uiState = MutableStateFlow<UserListUiState>(UserListUiState.Loading)
    val uiState: StateFlow<UserListUiState> = _uiState.asStateFlow()

    init {
        loadUsers()
    }

    /**
     * 发起协程任务获取数据
     */
    fun loadUsers() {
        viewModelScope.launch {
            _uiState.value = UserListUiState.Loading
            try {
                val users = repository.fetchUsers()
                // 请求成功，更新状态流
                _uiState.value = UserListUiState.Success(users)
            } catch (e: Exception) {
                // 请求失败，捕获错误信息并更新状态流
                _uiState.value = UserListUiState.Error(e.localizedMessage ?: "未知错误")
            }
        }
    }
}
