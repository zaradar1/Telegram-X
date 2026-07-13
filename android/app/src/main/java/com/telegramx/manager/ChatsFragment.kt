package com.telegramx.manager

import android.app.AlertDialog
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlin.concurrent.thread

data class ChatItem(val id: Long, val name: String, val subtitle: String)

class ChatsFragment : Fragment(R.layout.fragment_chats) {

    private lateinit var adapter: ChatsAdapter

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val recycler = view.findViewById<RecyclerView>(R.id.chatsRecycler)
        val progress = view.findViewById<ProgressBar>(R.id.chatsProgress)
        val emptyText = view.findViewById<TextView>(R.id.chatsEmpty)

        recycler.layoutManager = LinearLayoutManager(requireContext())
        adapter = ChatsAdapter(emptyList()) { chat -> promptDownload(chat) }
        recycler.adapter = adapter

        val phone = (activity as? MainActivity)?.activePhone
        if (phone == null) {
            emptyText.visibility = View.VISIBLE
            emptyText.text = getString(R.string.error_not_logged_in)
            return
        }

        progress.visibility = View.VISIBLE
        thread {
            val chats = PyBridge.listChats(phone).map { c ->
                val kind = when {
                    c.getBool("is_channel") -> getString(R.string.chat_kind_channel)
                    c.getBool("is_group") -> getString(R.string.chat_kind_group)
                    else -> getString(R.string.chat_kind_user)
                }
                ChatItem(c.getLong("id"), c.getStr("name") ?: "", kind)
            }
            activity?.runOnUiThread {
                progress.visibility = View.GONE
                if (chats.isEmpty()) {
                    emptyText.visibility = View.VISIBLE
                    emptyText.text = getString(R.string.chats_empty)
                } else {
                    emptyText.visibility = View.GONE
                }
                adapter.update(chats)
            }
        }
    }

    private fun promptDownload(chat: ChatItem) {
        val phone = (activity as? MainActivity)?.activePhone ?: return
        val input = EditText(requireContext()).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            hint = getString(R.string.hint_download_limit)
            setText("50")
        }
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.download_dialog_title, chat.name))
            .setMessage(R.string.download_dialog_message)
            .setView(input)
            .setPositiveButton(R.string.action_start) { _, _ ->
                val limit = input.text.toString().toIntOrNull() ?: 50
                thread {
                    val result = PyBridge.startBulkDownload(phone, chat.id, limit)
                    activity?.runOnUiThread {
                        if (result.getBool("ok")) {
                            Toast.makeText(requireContext(), R.string.download_started, Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(requireContext(), result.getStr("error") ?: getString(R.string.error_unknown), Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
            .setNegativeButton(R.string.action_cancel, null)
            .show()
    }
}

class ChatsAdapter(
    private var items: List<ChatItem>,
    private val onDownload: (ChatItem) -> Unit,
) : RecyclerView.Adapter<ChatsAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val name: TextView = view.findViewById(R.id.chatName)
        val subtitle: TextView = view.findViewById(R.id.chatSubtitle)
        val downloadButton: View = view.findViewById(R.id.downloadButton)
    }

    fun update(newItems: List<ChatItem>) {
        items = newItems
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: android.view.ViewGroup, viewType: Int): ViewHolder {
        val view = android.view.LayoutInflater.from(parent.context)
            .inflate(R.layout.item_chat, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.name.text = item.name
        holder.subtitle.text = item.subtitle
        holder.downloadButton.setOnClickListener { onDownload(item) }
    }

    override fun getItemCount() = items.size
}
