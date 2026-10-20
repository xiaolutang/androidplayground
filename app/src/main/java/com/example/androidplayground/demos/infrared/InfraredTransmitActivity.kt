package com.example.androidplayground.demos.infrared

import android.content.Context
import android.hardware.ConsumerIrManager
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.androidplayground.R

/**
 * Uses Android's public Consumer IR API. No system-app privilege is required;
 * the screen reports unsupported or unavailable hardware instead of failing silently.
 */
class InfraredTransmitActivity : AppCompatActivity() {

    private lateinit var statusView: TextView
    private var irManager: ConsumerIrManager? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = "红外发射测试"

        irManager = getSystemService(Context.CONSUMER_IR_SERVICE) as? ConsumerIrManager
        setContentView(createContent())
        refreshStatus()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun createContent(): LinearLayout {
        val padding = (24 * resources.displayMetrics.density).toInt()
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)

            addView(TextView(context).apply {
                text = "使用手机原生红外发射器发送 TCL 65V8H Pro 的实录电源帧。"
                textSize = 18f
            })

            statusView = TextView(context).apply {
                textSize = 15f
                setPadding(0, padding, 0, padding)
            }
            addView(statusView)

            addView(Button(context).apply {
                text = "发送电源码（38kHz）"
                setOnClickListener { transmitPowerCode() }
            }, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ))

            addView(TextView(context).apply {
                text = "请将手机顶部的红外孔正对电视接收窗。发送完成仅表示手机已完成发射；请观察电视是否响应。"
                textSize = 14f
                gravity = Gravity.START
                setPadding(0, padding, 0, 0)
            })
        }
    }

    private fun refreshStatus() {
        val manager = irManager
        if (manager == null || !manager.hasIrEmitter()) {
            statusView.text = "未检测到可供第三方应用使用的红外发射器。"
            return
        }

        val frequencies = manager.carrierFrequencies
            ?.joinToString { "${it.minFrequency}-${it.maxFrequency}Hz" }
            ?: "无法读取"
        statusView.text = "已检测到红外发射器。\n支持载波频率：$frequencies"
    }

    private fun transmitPowerCode() {
        val manager = irManager
        if (manager == null || !manager.hasIrEmitter()) {
            statusView.text = "发送失败：手机未向此应用开放红外发射器。"
            return
        }

        try {
            manager.transmit(CARRIER_FREQUENCY_HZ, TCL_POWER_PATTERN)
            statusView.text = "已发送 TCL 电源帧（38kHz）。请观察电视是否响应。"
        } catch (error: SecurityException) {
            statusView.text = "发送被系统拒绝：${error.message ?: "缺少红外权限"}"
        } catch (error: RuntimeException) {
            statusView.text = "发送失败：${error.message ?: error.javaClass.simpleName}"
        }
    }

    private companion object {
        const val CARRIER_FREQUENCY_HZ = 38_000

        // One complete power frame captured from the user's original TCL 65V8H Pro remote.
        val TCL_POWER_PATTERN = intArrayOf(
            4018, 3949, 527, 1962, 526, 1958, 528, 1959, 528, 1959,
            527, 961, 527, 962, 532, 1954, 529, 962, 530, 1957,
            528, 962, 530, 1956, 527, 965, 529, 960, 528, 961,
            530, 959, 532, 958, 529, 1957, 530, 1958, 531, 958,
            530, 1957, 532, 959, 527, 1957, 530, 961, 528, 1954,
            526, 8491
        )
    }
}
