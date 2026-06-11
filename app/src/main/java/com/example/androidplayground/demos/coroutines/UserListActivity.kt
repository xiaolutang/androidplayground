package com.example.androidplayground.demos.coroutines

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.androidplayground.R
import kotlinx.coroutines.launch

class UserListActivity : AppCompatActivity() {

    private val viewModel: UserListViewModel by viewModels()
    private lateinit var adapter: UserAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_user_list)

        val rvUsers = findViewById<RecyclerView>(R.id.rvUsers)
        val progressBar = findViewById<ProgressBar>(R.id.progressBar)
        val errorView = findViewById<View>(R.id.errorView)
        val tvError = findViewById<TextView>(R.id.tvError)
        val btnRetry = findViewById<Button>(R.id.btnRetry)

        adapter = UserAdapter()
        rvUsers.layoutManager = LinearLayoutManager(this)
        rvUsers.adapter = adapter

        btnRetry.setOnClickListener { viewModel.loadUsers() }

        // 订阅 UI 状态
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    progressBar.isVisible = state is UserListUiState.Loading
                    rvUsers.isVisible = state is UserListUiState.Success
                    errorView.isVisible = state is UserListUiState.Error

                    when (state) {
                        is UserListUiState.Success -> adapter.submitList(state.users)
                        is UserListUiState.Error -> tvError.text = state.message
                        else -> Unit
                    }
                }
            }
        }
    }

    // 内部 Adapter 类
    class UserAdapter : RecyclerView.Adapter<UserAdapter.ViewHolder>() {
        private var users = listOf<User>()

        fun submitList(newList: List<User>) {
            users = newList
            notifyDataSetChanged()
        }

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val name: TextView = view.findViewById(android.R.id.text1)
            val email: TextView = view.findViewById(android.R.id.text2)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(android.R.layout.simple_list_item_2, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val user = users[position]
            holder.name.text = user.name
            holder.email.text = user.email
        }

        override fun getItemCount() = users.size
    }
}
