# 📚 Terabox Archiver Pro — Project Documentation

> Technical documentation for the Streamlit + Telethon administrative panel and
> Telegram automation toolkit contained in this repository. Details below are
> cross-checked against `main.py` and `streamlit_app.py`.

---

## 1. Project Overview

**Project Name:** Terabox Archiver Pro (repo: `Telegram-X`)
**Type:** Web application (Streamlit UI) + Telegram automation backend (Telethon / MTProto)
**Primary Purpose:** An administrative panel for managing Telegram media
operations — extracting and downloading Terabox links found in channels,
mirroring/forwarding media between channels, and handling user authorization and
premium licensing — all driven from a web UI on top of native Telegram userbot
sessions.

Key entry points:

| File | Role |
|------|------|
| `streamlit_app.py` | Streamlit UI: auth flow, worker launch pages, Job Manager, admin tabs |
| `main.py` | Core library: DB layer, Fernet crypto, Terabox extraction, download/forward workers, bot helpers |
| `requirements.txt` | Python dependencies |
| `README.md`, `USAGE_GUIDE.md`, `QUICK_REFERENCE.md`, `QUICKSTART.py` | End-user guides |

---

## 2. Architecture & Tech Stack

### Frontend & UI
- **Streamlit** serves the interactive UI. It is stateless: each interaction
  triggers a full script rerun.
- **`st.session_state`** preserves auth progress across reruns — notably
  `step`, `api_id`, `api_hash`, `phone`, `phone_code_hash`, `session_string`,
  and the in-process `background_jobs` dict.

### Backend & automation
- **Telethon (asyncio)** provides native MTProto connections for requesting OTPs
  (`send_code_request`), signing in (`sign_in`), scraping messages, downloading
  media, and forwarding.
- **`threading` daemon workers** run the long-lived Bulk Downloader, Channel
  Scraper, and Media Forwarder off the main thread. `main.py` also starts
  background helpers at import time: extraction workers
  (`_start_extraction_workers`), a proxy manager (`_start_proxy_manager`), and a
  Google Drive backup manager (`_start_gdrive_backup_manager`).
- **Async bridge:** `_run_async` / `_make_async` marshal blocking extraction
  work onto a shared event loop and thread pool.

### Persistence
- **SQLite** at `terabox_v5.db` (`DB_FILE`), opened via a custom
  `ClosingConnection` factory with `check_same_thread=False` and WAL journaling.
- **Cryptography (`Fernet`)** encrypts sensitive columns. The key is created or
  loaded by `get_or_create_fernet_key`; `encrypt_credential` / `decrypt_credential`
  wrap the API hash and Telethon `StringSession` before they are written to the DB.
- **DB error handling** — schema migrations use guarded `ALTER TABLE` calls
  wrapped in bare `try/except: pass` so re-running `init_db()` on an
  already-migrated DB is a no-op. `get_db()` opens a fresh connection per call
  (via `with get_db() as conn:`), and `ClosingConnection` closes it on context
  exit rather than pooling. Job-state writes (`dl_job_create`, `dl_job_update`)
  serialize through a module-level `_db_lock` to avoid concurrent-write
  contention across worker threads, but do not themselves catch
  `sqlite3.Error` — a failed write propagates to the caller rather than being
  silently retried.

### Downloads
- `DOWNLOAD_DIR` defaults to the system temp dir (`tempfile.gettempdir()`), with
  additional working dirs (`FORWARD_CACHE`, `DL_BASE`, `STATE_DIR`, `RECORD_DIR`)
  created on startup.

---

## 3. Data Model (SQLite schema)

Created idempotently by `init_db()` (uses `CREATE TABLE IF NOT EXISTS` plus
guarded `ALTER TABLE` for migrations):

| Table | Purpose |
|-------|---------|
| `users` | Registered users: approval/ban flags, link counters |
| `user_credentials` | Per-user `api_id`, encrypted `api_hash`, encrypted session string |
| `pending_users` | Users awaiting admin approval |
| `history` | Per-user Terabox extraction history (url, filename, size, links) |
| `rate_log` | Timestamps backing per-user rate limiting |
| `broadcasts` | Admin broadcast message log |
| `dl_progress` | Background job state: totals, downloaded/failed counts, `state` (`running`/`pause`/`stopped`) |
| `dl_done_msgs` | Per-job set of already-processed message IDs (idempotency) |
| `premium_users` | Active premium grants (plan, activation/expiry, payment code) |
| `premium_codes` | Generated redeemable license codes and redemption status |
| `processed_messages` | De-duplication across scrape/forward tasks keyed by `(source, msg_id, task_type)` |

### Example rows

```
users            (123456789, "alice", "Alice", 2026-01-10, 0, 1, 42)
user_credentials (user_id=123456789, api_id="12345678",
                   api_hash_encrypted="gAAAAA...", session_string_encrypted="gAAAAA...")
dl_progress      (job_id="a1b2c3", chat_id=123456789, src="@source_channel",
                   total_wanted=200, downloaded=150, failed=3, state="running")
premium_codes    (code="PRO1Y-9F3K-...", plan_id="PRO_1Y", used_by=NULL, is_active=1)
```

`api_hash_encrypted` and `session_string_encrypted` are always Fernet
ciphertext (`gAAAAA...` prefix) — the plaintext values only ever exist
in-process, never written to disk.

On startup `init_db()` also resets any `running`/`pause` jobs left over from a
crash to `stopped`, then triggers a forced Drive backup.

---

## 4. Core Features & Data Flow

### 🔐 Authentication flow (multi-client)
1. **Config step** — user enters phone, API ID, and API hash (`step = "config"`).
2. **Login step** — Telethon `send_code_request()` returns a `phone_code_hash`,
   stored in `st.session_state` along with the in-memory session.
3. **Verify step** — user submits the OTP; Telethon `sign_in()` runs. On success
   the `StringSession` is encrypted via the Fernet cipher and persisted through
   `save_user_credentials`.
4. **Subsequent logins** — "Load Saved Session" restores the decrypted session
   (`get_user_credentials`) using `phone_to_uid()` (a stable SHA-256-derived
   key) as the lookup key.
5. **2FA (two-step verification)** — if `sign_in()` raises
   `SessionPasswordNeededError`, the flow moves to a dedicated `twofa` step
   that collects the account's Telegram password and finishes sign-in via
   `verify_2fa_password()`. The bot's own `/login` conversational wizard
   (`main.py:_login_task`) has the equivalent password step.

### 🎥 Media operations (background workers)
Workers run on daemon threads and periodically write progress to `dl_progress`;
the **Active Jobs** tab polls the DB to render status.

- **Quick Download** — extracts one link, downloads it synchronously, sends it
  to the selected channel via `send_file`, and (if configured) uploads it to
  the selected cloud target(s) in the same request.
- **Bulk Downloader** — scans a source channel for messages containing Terabox
  links, extracts direct links with `extract_terabox_sync` (backed by a large
  bank of provider fallbacks `_api1_sync … _api30_sync`, normalized by `_norm`),
  downloads to `DOWNLOAD_DIR`, and optionally uploads each file to the cloud
  targets selected in the UI (see "Cloud upload targets" below).
- **Channel Scraper** — iterates a source channel, downloads media locally, and
  re-uploads to a target channel.
- **Media Forwarder** — uses Telegram's native `forward_messages()` to move
  media between chats without local download.

Idempotency: all three Streamlit-triggered workers (`downloader_worker`,
`scraper_worker`, `forwarder_worker` in `streamlit_app.py`) call
`is_msg_processed` / `mark_msg_processed` per message, keyed by
`(str(source_id), msg_id, task_type)`, so restarting a job after a crash
skips messages it already handled. The bot-triggered task runners in
`main.py` (`_dl_one_message`, `_forwarder_task`) use the same helpers on
their own `(src, msg_id, task_type)` keys; `dl_done_check` / `dl_done_add`
additionally track completion at the `dl_progress` job level.

### ☁️ Cloud upload targets (optional)
`main.py` exposes `upload_to_s3` / `upload_to_gdrive` (dispatched via
`upload_to_cloud_targets`), each inert until its env vars are set:
`S3_BUCKET` (+ optional `AWS_REGION`, `S3_PREFIX`) for S3, or
`GDRIVE_SERVICE_ACCOUNT_JSON` (+ optional `GDRIVE_FOLDER_ID`) for Drive via a
service account. `cloud_targets_available()` reports which are configured;
the Quick Download and Bulk Downloader tabs show a multiselect only when at
least one is. This is distinct from `_backup_to_gdrive`, which is a
Colab-only internal DB/session backup and not user-facing.

### 🛡️ Administration & security
- **User management** — external users start in `pending_users`; the admin can
  approve / reject / ban / unban from the UI
  (`approve_user`, `reject_user`, `ban_user`, `unban_user`, `get_pending_users`).
- **Premium licensing** — plans `PRO_1M`, `PRO_3M`, `PRO_1Y`, `PRO_LIFETIME`.
  Admins generate codes (`generate_premium_code`), grant directly
  (`activate_premium`), or users redeem codes (`redeem_premium_code`).
- **Admin system** — platform stats (`get_admin_stats`) and broadcast messaging.
- **Bot console** — sends a command via the userbot and captures the reply
  through a Telethon `events.NewMessage` handler (push-based, bounded by a
  10s timeout) rather than a fixed sleep-then-fetch-last-5 poll.
- **Rate limiting** — `check_rate_limit` throttles per-user activity via `rate_log`.

### 🔀 Resilience helpers
- `ProxyManager` and `AccountRotator` distribute extraction/download load.
- `_make_resilient_session` builds retrying HTTP sessions; `_is_network_error`
  and `_flood_wait` handle transient failures and Telegram FLOOD_WAIT.

---

## 5. UI Map (Streamlit tabs)

| Tab / view | Backing logic |
|------------|---------------|
| Login & Load Session | session decrypt + credential entry |
| Telegram Login / Verify OTP | `send_code_request` → `sign_in` |
| Quick Download | single-link download |
| Bulk Downloader | channel scan + `extract_terabox_sync` |
| Channel Scraper | download-and-reupload worker |
| Media Forwarder | native `forward_messages` |
| Active Jobs | polls `dl_progress` |
| User Management | pending/approved user actions |
| Admin System | stats + broadcast |
| Premium Management | code generation / direct grant |
| Bot Console | dispatch commands to the userbot |

---

## 6. Deployment Pipeline

**Target:** Streamlit Cloud or a VPS.
1. **GitHub sync** — the Streamlit Cloud app is linked to this repository.
2. **Automatic reboot** — pushes to the deployed branch trigger a pull, a
   `requirements.txt` install, and a server rerun.
3. **DB initialization** — on boot, `init_db()` ensures `terabox_v5.db` exists
   with the current schema, applying guarded `ALTER TABLE` migrations.
4. **Backups** — `trigger_gdrive_backup` / `_backup_to_gdrive` optionally push
   the SQLite file to Google Drive.

> Note: `main.py` and `streamlit_app.py` are the runtime source in this repo. If
> a build step produces obfuscated deployment artifacts, it lives outside the
> tracked source and is not part of these files.

---

## 7. Security Notes

- **Session persistence** — the Fernet key must be kept out of the repo (e.g. via
  `.env`); it is required to decrypt any stored session string or API hash.
- **SQLite concurrency** — `check_same_thread=False` plus WAL is used because
  Streamlit and the worker threads share the DB; writes should stay short.
- **Credential handling** — API hashes and session strings are encrypted at rest;
  keep `terabox_v5.db` and the encryption key access-controlled.
- **Encryption primitive** — `cipher_suite` is a `cryptography.fernet.Fernet`
  instance (AES-128-CBC + HMAC-SHA256 with a random IV and message timestamp),
  which is an accepted standard for symmetric field-level encryption at rest.
  Its guarantees only hold if the key from `get_or_create_fernet_key` is
  generated with a secure RNG and never committed to source control.
- **Phone-derived lookup key** — `streamlit_app.py` derives the DB lookup key
  for "Load Saved Session" via `phone_to_uid()`, a SHA-256 digest of the
  (stripped) phone number truncated to a 60-bit int. This replaced an earlier
  `hash(phone_input) % (10**8)` scheme: Python's built-in `hash()` is salted
  per-process by default (`PYTHONHASHSEED` is randomized unless explicitly
  fixed), so the same phone number mapped to a different key after every app
  restart, and the truncated space made cross-phone-number collisions
  non-negligible. SHA-256 is deterministic across runs and its 60-bit prefix
  keeps collision probability negligible for any realistic user count.
  **Migration note:** rows saved under the old `hash()`-based key are keyed
  differently than `phone_to_uid()` now computes, so "Load Saved Session"
  won't find pre-existing rows after this change — affected users see "No
  saved credentials found" once and need to re-verify OTP, which re-saves
  under the new stable key.
- **User data handling** — `history`, `user_credentials`, and `premium_users`
  key on this same numeric ID, so any weakness in how it's derived also affects
  history/premium lookups, not just login. Rate limiting (`check_rate_limit`)
  and the approve/ban gate (`is_approved`, `is_banned`) are the main abuse
  controls; both operate on this ID as well.
- **Compliance** — automating Telegram accounts (userbots) and downloading from
  third-party file hosts is subject to Telegram's Terms of Service, the file
  host's terms, and applicable copyright law. Operate only on content and
  accounts you are authorized to use.

---

## 8. Roadmap

- ~~Full 2FA (two-step password) support in the Streamlit auth flow.~~ Done —
  see the `twofa` step in §4 (and the equivalent `/login` wizard password step
  in `main.py`).
- ~~Webhook-based bot response parsing to replace polling in the Bot
  Console.~~ Done for the Bot Console's own command/reply capture (now
  event-driven via Telethon, no fixed sleep). The bot's *inbound* command
  dispatch (`run_bot()`) still uses `bot.polling(...)` — switching that to a
  genuine Telegram Bot API webhook needs a publicly reachable HTTPS endpoint,
  which is a hosting decision, not a code-only change.
- ~~Additional cloud storage upload targets (Google Drive, S3).~~ Done — see
  "Cloud upload targets" in §4. Requires `S3_BUCKET` or
  `GDRIVE_SERVICE_ACCOUNT_JSON` to be configured; inert otherwise.
- Real Telegram Bot API webhook receiver for `run_bot()`'s inbound dispatch
  (needs a public HTTPS URL — infra decision, not implemented here).

---

## 9. Local Setup

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py   # opens http://localhost:8501
```

Get API credentials from [my.telegram.org](https://my.telegram.org/) (API ID +
API Hash). See `USAGE_GUIDE.md` and `QUICK_REFERENCE.md` for step-by-step UI
walkthroughs.

Optional env vars for cloud upload targets (leave unset to disable):

| Var | Target | Required with |
|-----|--------|----------------|
| `S3_BUCKET` | S3 | `AWS_REGION`, `S3_PREFIX` (both optional), plus standard AWS credential env vars / instance role |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Google Drive | Path to a service-account JSON key; `GDRIVE_FOLDER_ID` (optional) to target a specific folder |

---

## 10. Troubleshooting

For end-user issues (invalid OTP, expired code, phone format errors, stuck
sessions), see the **"Error Messages & Solutions"** table in
`QUICK_REFERENCE.md` and the **"Troubleshooting Input Issues"** /
**"Getting Help"** sections in `USAGE_GUIDE.md` — both are kept close to the UI
copy so error text there matches what the app actually shows. This file stays
focused on architecture; it intentionally doesn't duplicate that content.
