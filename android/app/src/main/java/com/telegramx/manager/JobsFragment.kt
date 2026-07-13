package com.telegramx.manager

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlin.concurrent.thread

data class JobItem(
    val jobId: String,
    val chatId: Long,
    val status: String,
    val total: Int,
    val completed: Int,
    val failed: Int,
)

class JobsFragment : Fragment(R.layout.fragment_jobs) {

    private lateinit var adapter: JobsAdapter
    private val handler = Handler(Looper.getMainLooper())
    private var polling = false

    private val pollRunnable = object : Runnable {
        override fun run() {
            refresh()
            if (polling) handler.postDelayed(this, 2000)
        }
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val recycler = view.findViewById<RecyclerView>(R.id.jobsRecycler)
        recycler.layoutManager = LinearLayoutManager(requireContext())
        adapter = JobsAdapter(
            emptyList(),
            onPause = { PyBridge.pauseJob(it) },
            onResume = { PyBridge.resumeJob(it) },
            onStop = { PyBridge.stopJob(it) },
        )
        recycler.adapter = adapter
    }

    override fun onStart() {
        super.onStart()
        polling = true
        handler.post(pollRunnable)
    }

    override fun onStop() {
        super.onStop()
        polling = false
        handler.removeCallbacks(pollRunnable)
    }

    private fun refresh() {
        val emptyText = view?.findViewById<TextView>(R.id.jobsEmpty)
        val progress = view?.findViewById<ProgressBar>(R.id.jobsProgress)
        thread {
            val jobs = PyBridge.listJobs().map { j ->
                JobItem(
                    j.getStr("job_id") ?: "",
                    j.getLong("chat_id"),
                    j.getStr("status") ?: "",
                    j.getInt("total"),
                    j.getInt("completed"),
                    j.getInt("failed"),
                )
            }
            activity?.runOnUiThread {
                progress?.visibility = View.GONE
                emptyText?.visibility = if (jobs.isEmpty()) View.VISIBLE else View.GONE
                adapter.update(jobs)
            }
        }
    }
}

class JobsAdapter(
    private var items: List<JobItem>,
    private val onPause: (String) -> Unit,
    private val onResume: (String) -> Unit,
    private val onStop: (String) -> Unit,
) : RecyclerView.Adapter<JobsAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.jobTitle)
        val progressText: TextView = view.findViewById(R.id.jobProgressText)
        val pauseButton: Button = view.findViewById(R.id.jobPauseButton)
        val stopButton: Button = view.findViewById(R.id.jobStopButton)
    }

    fun update(newItems: List<JobItem>) {
        items = newItems
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: android.view.ViewGroup, viewType: Int): ViewHolder {
        val view = android.view.LayoutInflater.from(parent.context)
            .inflate(R.layout.item_job, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.title.text = holder.itemView.context.getString(R.string.job_title, item.chatId)
        holder.progressText.text = holder.itemView.context.getString(
            R.string.job_progress, item.status, item.completed, item.total, item.failed
        )
        holder.pauseButton.text = if (item.status == "paused")
            holder.itemView.context.getString(R.string.action_resume)
        else
            holder.itemView.context.getString(R.string.action_pause)
        holder.pauseButton.isEnabled = item.status == "running" || item.status == "paused"
        holder.pauseButton.setOnClickListener {
            if (item.status == "paused") onResume(item.jobId) else onPause(item.jobId)
        }
        holder.stopButton.isEnabled = item.status == "running" || item.status == "paused"
        holder.stopButton.setOnClickListener { onStop(item.jobId) }
    }

    override fun getItemCount() = items.size
}
