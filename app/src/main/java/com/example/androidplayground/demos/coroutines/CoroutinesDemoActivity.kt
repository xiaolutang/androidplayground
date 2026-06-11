package com.example.androidplayground.demos.coroutines

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.addTextChangedListener
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.example.androidplayground.R
import kotlinx.coroutines.launch

class CoroutinesDemoActivity : AppCompatActivity() {

    // 最佳实践：使用 Activity KTX 委托创建 ViewModel
    private val viewModel: CoroutinesDemoViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_coroutines_demo)

        val tvLog: TextView = findViewById(R.id.tvLog)

        // 1. 订阅数据流 (StateFlow)
        // repeatOnLifecycle 是最安全的 UI 订阅方式，类似 Flutter 的 StreamBuilder
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiLog.collect { logs ->
                    tvLog.text = logs.joinToString("\n") { "> $it" }
                }
            }
        }

        // 2. 发送动作 (Event) 给 ViewModel
        findViewById<Button>(R.id.btnSimpleLaunch).setOnClickListener {
            viewModel.runSimpleLaunch()
        }

        findViewById<Button>(R.id.btnDispatcherSwitch).setOnClickListener {
            viewModel.runDispatcherSwitch()
        }

        findViewById<Button>(R.id.btnAsyncAwait).setOnClickListener {
            viewModel.runAsyncAwait()
        }

        findViewById<Button>(R.id.btnExceptionHandling).setOnClickListener {
            viewModel.runErrorHandling()
        }

        findViewById<Button>(R.id.btnFlowOperators).setOnClickListener {
            viewModel.runFlowOperators()
        }

        // 3. 进阶挑战：绑定搜索框
        findViewById<android.widget.EditText>(R.id.etSearch).addTextChangedListener {
            viewModel.onSearchQueryChanged(it?.toString() ?: "")
        }
    }
}
