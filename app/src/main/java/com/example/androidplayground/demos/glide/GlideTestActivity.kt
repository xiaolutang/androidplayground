package com.example.androidplayground.demos.glide

import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.bumptech.glide.Glide
import com.bumptech.glide.load.DataSource
import com.bumptech.glide.load.engine.GlideException
import com.bumptech.glide.request.RequestListener
import com.bumptech.glide.request.target.Target
import com.example.androidplayground.R

class GlideTestActivity : AppCompatActivity() {

    private val SMALL_IMAGE_URL = "https://picsum.photos/100/100"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_glide_test)

        val ivNormal = findViewById<ImageView>(R.id.ivNormal)
        val tvNormalInfo = findViewById<TextView>(R.id.tvNormalInfo)
        val ivCenterCrop = findViewById<ImageView>(R.id.ivCenterCrop)
        val tvCenterCropInfo = findViewById<TextView>(R.id.tvCenterCropInfo)
        val ivXmlCrop = findViewById<ImageView>(R.id.ivXmlCrop)
        val tvXmlCropInfo = findViewById<TextView>(R.id.tvXmlCropInfo)
        val ivFixed200 = findViewById<ImageView>(R.id.ivFixed200)
        val tvFixed200Info = findViewById<TextView>(R.id.tvFixed200Info)
        val ivFixed500 = findViewById<ImageView>(R.id.ivFixed500)
        val tvFixed500Info = findViewById<TextView>(R.id.tvFixed500Info)
        val btnStart = findViewById<Button>(R.id.btnStartTest)

        btnStart.setOnClickListener {
            loadImages(
                ivNormal, tvNormalInfo, 
                ivCenterCrop, tvCenterCropInfo, 
                ivXmlCrop, tvXmlCropInfo,
                ivFixed200, tvFixed200Info,
                ivFixed500, tvFixed500Info
            )
        }
    }

    private fun loadImages(
        ivNormal: ImageView, tvNormal: TextView,
        ivCrop: ImageView, tvCrop: TextView,
        ivXml: ImageView, tvXml: TextView,
        ivFixed200: ImageView, tvFixed200: TextView,
        ivFixed500: ImageView, tvFixed500: TextView
    ) {
        // 1. 普通模式
        Glide.with(this)
            .load(SMALL_IMAGE_URL)
            .listener(createLogger(tvNormal, "普通模式"))
            .into(ivNormal)

        // 2. XML 拉伸 (验证组)
        Glide.with(this)
            .load(SMALL_IMAGE_URL)
            .listener(createLogger(tvXml, "XML拉伸"))
            .into(ivXml)

        // 3. Glide 变换 (实验组)
        Glide.with(this)
            .load(SMALL_IMAGE_URL)
            .centerCrop()
            .listener(createLogger(tvCrop, "Glide变换"))
            .into(ivCrop)

        // 4. 固定 200dp (新增)
        Glide.with(this)
            .load(SMALL_IMAGE_URL)
            .listener(createLogger(tvFixed200, "200dp视图"))
            .into(ivFixed200)

        // 5. 固定 500dp (新增)
        Glide.with(this)
            .load(SMALL_IMAGE_URL)
            .listener(createLogger(tvFixed500, "500dp视图"))
            .into(ivFixed500)
    }

    private fun createLogger(infoTextView: TextView, modeName: String): RequestListener<Drawable> {
        return object : RequestListener<Drawable> {
            override fun onLoadFailed(
                e: GlideException?, model: Any?, target: Target<Drawable>, isFirstResource: Boolean
            ): Boolean {
                infoTextView.text = "$modeName: 加载失败 ${e?.message}"
                return false
            }

            override fun onResourceReady(
                resource: Drawable,
                model: Any,
                target: Target<Drawable>?,
                dataSource: DataSource,
                isFirstResource: Boolean
            ): Boolean {
                if (resource is BitmapDrawable) {
                    val bitmap = resource.bitmap
                    val width = bitmap.width
                    val height = bitmap.height
                    val byteCount = bitmap.byteCount
                    val kb = byteCount / 1024.0

                    infoTextView.text = """
                        结果: ${width}x${height} 像素
                        内存占用: ${String.format("%.2f", kb)} KB
                    """.trimIndent()
                } else {
                    infoTextView.text = "结果: 非 Bitmap 类型 (${resource::class.java.simpleName})"
                }
                return false
            }
        }
    }
}
