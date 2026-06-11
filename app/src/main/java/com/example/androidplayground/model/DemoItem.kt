package com.example.androidplayground.model

import android.app.Activity

data class DemoItem(
    val title: String,
    val description: String,
    val targetActivity: Class<out Activity>
)
