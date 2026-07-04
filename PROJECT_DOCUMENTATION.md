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
   (`get_user_credentials`) using the phone number as a lookup key.

2FA note: full two-step-password handling in the UI is a roadmap item (§6);
the current flow centers on OTP sign-in.

### 🎥 Media operations (background workers)
Workers run on daemon threads and periodically write progress to `dl_progress`;
the **Active Jobs** tab polls the DB to render status.

- **Quick Download** — one-off download to a selected upload target.
- **Bulk Downloader** — scans a source channel for messages containing Terabox
  links, extracts direct links with `extract_terabox_sync` (backed by a large
  bank of provider fallbacks `_api1_sync … _api30_sync`, normalized by `_norm`),
  and downloads to `DOWNLOAD_DIR`.
- **Channel Scraper** — iterates a source channel, downloads media locally, and
  re-uploads to a target channel.
- **Media Forwarder** — uses Telegram's native `forward_messages()` to move
  media between chats without local download.

Idempotency: `is_msg_processed` / `mark_msg_processed` and `dl_done_check` /
`dl_done_add` prevent re-processing the same message across restarts.

### 🛡️ Administration & security
- **User management** — external users start in `pending_users`; the admin can
  approve / reject / ban / unban from the UI
  (`approve_user`, `reject_user`, `ban_user`, `unban_user`, `get_pending_users`).
- **Premium licensing** — plans `PRO_1M`, `PRO_3M`, `PRO_1Y`, `PRO_LIFETIME`.
  Admins generate codes (`generate_premium_code`), grant directly
  (`activate_premium`), or users redeem codes (`redeem_premium_code`).
- **Admin system** — platform stats (`get_admin_stats`) and broadcast messaging.
- **Bot console** — sends operational commands (e.g. `/stats`, `/backup`) to the
  linked userbot from the web UI.
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
- **Compliance** — automating Telegram accounts (userbots) and downloading from
  third-party file hosts is subject to Telegram's Terms of Service, the file
  host's terms, and applicable copyright law. Operate only on content and
  accounts you are authorized to use.

---

## 8. Roadmap

- Full 2FA (two-step password) support in the Streamlit auth flow.
- Webhook-based bot response parsing to replace polling in the Bot Console.
- Additional cloud storage upload targets (Google Drive is partially wired via
  the backup manager; extend to user-facing upload destinations / S3).

---

## 9. Local Setup

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py   # opens http://localhost:8501
```

Get API credentials from [my.telegram.org](https://my.telegram.org/) (API ID +
API Hash). See `USAGE_GUIDE.md` and `QUICK_REFERENCE.md` for step-by-step UI
walkthroughs.
