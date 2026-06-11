package com.example.androidplayground.adapter

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.androidplayground.R
import com.example.androidplayground.model.DemoItem

class DemoAdapter(
    private val demos: List<DemoItem>,
    private val onItemClick: (DemoItem) -> Unit
) : RecyclerView.Adapter<DemoAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvTitle: TextView = view.findViewById(R.id.tvTitle)
        val tvDescription: TextView = view.findViewById(R.id.tvDescription)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_demo, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val demo = demos[position]
        holder.tvTitle.text = demo.title
        holder.tvDescription.text = demo.description
        holder.itemView.setOnClickListener { onItemClick(demo) }
    }

    override fun getItemCount() = demos.size
}
