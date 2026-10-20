package com.example.androidplayground

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.androidplayground.adapter.DemoAdapter
import com.example.androidplayground.demos.coroutines.CoroutinesDemoActivity
import com.example.androidplayground.demos.coroutines.UserListActivity
import com.example.androidplayground.demos.glide.GlideTestActivity
import com.example.androidplayground.demos.infrared.InfraredTransmitActivity
import com.example.androidplayground.model.DemoItem
import io.flutter.embedding.android.FlutterActivity

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<com.google.android.material.appbar.MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        val rvDemos = findViewById<RecyclerView>(R.id.rvDemos)
        rvDemos.layoutManager = LinearLayoutManager(this)

        val demoList = listOf(
            DemoItem(
                title = "Kotlin 协程基础",
                description = "学习调度器、异步并发与异常处理",
                targetActivity = CoroutinesDemoActivity::class.java
            ),
            DemoItem(
                title = "网络请求模拟 (Flow)",
                description = "实战：加载/成功/失败状态管理",
                targetActivity = UserListActivity::class.java
            ),
            DemoItem(
                title = "Flutter 混合开发",
                description = "在原生 Android 中加载 Flutter 模块",
                targetActivity = FlutterActivity::class.java
            ),
            DemoItem(
                title = "Glide 内存坑验证",
                description = "观察 wrap_content + centerCrop 导致的小图被放大的现象",
                targetActivity = GlideTestActivity::class.java
            ),
            DemoItem(
                title = "红外发射测试",
                description = "检测手机红外能力，并发送 TCL 65V8H Pro 电源码",
                targetActivity = InfraredTransmitActivity::class.java
            )
        )

        rvDemos.adapter = DemoAdapter(demoList) { demo ->
            startActivity(Intent(this, demo.targetActivity))
        }
    }
}
