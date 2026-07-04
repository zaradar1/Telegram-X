import streamlit as st
import asyncio
import os
import time
import requests
import tempfile
import threading
import hashlib
from io import BytesIO
from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession
import uuid
import pandas as pd

# Import extraction logic and DB from existing codebase
try:
        from main import (
        init_db, save_user_credentials, get_user_credentials, get_db, cipher_suite,
        extract_terabox_sync, HEADERS, _send_timeout_for_size, _fetch_thumb,
        get_db, approve_user, reject_user, ban_user, unban_user, get_pending_users,
        get_admin_stats, get_all_user_ids, generate_premium_code, get_all_premium_codes, activate_premium,
        DOWNLOAD_DIR, BOT_TOKEN,
        cloud_targets_available, upload_to_cloud_targets,
        is_msg_processed, mark_msg_processed,
    )
except Exception as e:
    import traceback
    st.error(f"Failed to import from main.py. Ensure main.py is in the same directory. Detailed error: {e}")
    st.code(traceback.format_exc())
    st.stop()

init_db()

st.set_page_config(page_title="Terabox Archiver Pro", page_icon="📦", layout="wide")

# Initialize global job tracker (persists across Streamlit reruns in the same process)
if "background_jobs" not in st.session_state:
    st.session_state.background_jobs = {}

if "step" not in st.session_state:
    st.session_state.step = "config"
if "api_id" not in st.session_state:
    st.session_state.api_id = ""
if "api_hash" not in st.session_state:
    st.session_state.api_hash = ""
if "phone" not in st.session_state:
    st.session_state.phone = ""
if "phone_code_hash" not in st.session_state:
    st.session_state.phone_code_hash = None
if "channels" not in st.session_state:
    st.session_state.channels = []


# Multi-Client Session Handling
if "session_string" not in st.session_state:
    st.session_state.session_string = ""
if "phone" not in st.session_state:
    st.session_state.phone = ""

def get_session_string():
    async def _get():
        cl = get_client()
        await cl.connect()
        s = cl.session.save()
        await cl.disconnect()
        return s
    return asyncio.run(_get())

def get_client():
    if st.session_state.session_string:
        return TelegramClient(StringSession(st.session_state.session_string), st.session_state.api_id, st.session_state.api_hash)
    else:
        # Create a new memory session if none exists
        return TelegramClient(StringSession(), st.session_state.api_id, st.session_state.api_hash)

def phone_to_uid(phone: str) -> int:
    """Stable numeric DB key derived from a phone number.

    Python's built-in hash() is salted per-process (PYTHONHASHSEED), so the
    same phone number would map to a different key after every restart and
    "Load Saved Session" would stop finding rows saved before the restart.
    SHA-256 is deterministic across runs and its 60-bit prefix fits SQLite's
    signed 64-bit INTEGER columns.
    """
    digest = hashlib.sha256(phone.strip().encode("utf-8")).hexdigest()
    return int(digest[:15], 16)


async def check_login_status():
    client = get_client()
    await client.connect()
    is_auth = await client.is_user_authorized()
    await client.disconnect()
    return is_auth

async def send_auth_code(phone):
    client = get_client()
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        return sent.phone_code_hash, client.session.save(), None
    except Exception as e:
        return None, None, str(e)
    finally:
        await client.disconnect()

async def verify_auth_code(phone, code, phone_code_hash):
    client = get_client()
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True, client.session.save(), None, False
    except errors.SessionPasswordNeededError:
        # Account has two-step verification enabled; caller must collect the
        # password and call verify_2fa_password() to finish signing in.
        return False, client.session.save(), None, True
    except Exception as e:
        return False, None, str(e), False
    finally:
        await client.disconnect()

async def verify_2fa_password(session_string, api_id, api_hash, password):
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(password=password)
        return True, client.session.save(), None
    except errors.PasswordHashInvalidError:
        return False, None, "Invalid 2FA password."
    except Exception as e:
        return False, None, str(e)
    finally:
        await client.disconnect()

async def fetch_channels():
    client = get_client()
    await client.connect()
    channels = []
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                channels.append({"id": dialog.id, "name": dialog.name})
    except Exception as e:
        pass
    finally:
        await client.disconnect()
    return channels

# --- BACKGROUND TASKS ---
def scraper_worker(job, source_id, target_id, limit, api_id, api_hash, session_str):
    job['status'] = 'running'
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    
    async def run_scrape():
        await client.connect()
        try:
            async for msg in client.iter_messages(source_id, limit=limit):
                if job['status'] == 'stopped':
                    break
                while job['status'] == 'paused':
                    await asyncio.sleep(1)

                if is_msg_processed(str(source_id), msg.id, "scrape"):
                    continue

                text = msg.message or ""
                if "terabox.com" in text or "terabox" in text:
                    job['total'] += 1
                    result = extract_terabox_sync(text)
                    if result and result.get('download'):
                        try:
                            download_url = result['download']
                            temp_dir = tempfile.gettempdir()
                            filepath = os.path.join(temp_dir, result.get("filename", "video.mp4"))

                            headers = {"User-Agent": HEADERS.get("user-agent", ""), "Referer": "https://www.terabox.com/"}
                            r = requests.get(download_url, headers=headers, stream=True, timeout=120)
                            if r.status_code == 403:
                                headers.pop("Referer", None)
                                r = requests.get(download_url, headers=headers, stream=True, timeout=120)

                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk: f.write(chunk)

                            await client.send_file(target_id, filepath, caption=result.get("title", "Scraped Video"))
                            job['completed'] += 1
                            mark_msg_processed(str(source_id), msg.id, "scrape")
                            if os.path.exists(filepath):
                                os.remove(filepath)
                        except Exception as e:
                            job['failed'] += 1
            
            job['status'] = 'finished'
        except Exception as e:
            job['status'] = f'error: {str(e)}'
        finally:
            await client.disconnect()

    loop.run_until_complete(run_scrape())

def forwarder_worker(job, source_id, target_id, limit, api_id, api_hash, session_str):
    job['status'] = 'running'
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    
    async def run_forward():
        await client.connect()
        try:
            async for msg in client.iter_messages(source_id, limit=limit):
                if job['status'] == 'stopped':
                    break
                while job['status'] == 'paused':
                    await asyncio.sleep(1)

                if is_msg_processed(str(source_id), msg.id, "forward"):
                    continue

                job['total'] += 1
                try:
                    # Actually forward media by re-uploading or forwarding
                    if msg.media:
                        await client.send_message(target_id, message=msg)
                    job['completed'] += 1
                    mark_msg_processed(str(source_id), msg.id, "forward")
                except Exception as e:
                    job['failed'] += 1
            
            job['status'] = 'finished'
        except Exception as e:
            job['status'] = f'error: {str(e)}'
        finally:
            await client.disconnect()

    loop.run_until_complete(run_forward())

def downloader_worker(job, source_id, limit, api_id, api_hash, session_str, cloud_targets=None):
    job['status'] = 'running'
    job.setdefault('cloud_links', [])
    cloud_targets = cloud_targets or []

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(session_str), api_id, api_hash)

    async def run_download():
        await client.connect()
        try:
            async for msg in client.iter_messages(source_id, limit=limit):
                if job['status'] == 'stopped':
                    break
                while job['status'] == 'paused':
                    await asyncio.sleep(1)

                if is_msg_processed(str(source_id), msg.id, "download"):
                    continue

                text = msg.message or ""
                if "terabox.com" in text or "terabox" in text:
                    job['total'] += 1
                    result = extract_terabox_sync(text)
                    if result and result.get('download'):
                        try:
                            download_url = result['download']
                            # Save to DOWNLOAD_DIR as a real local file
                            save_dir = DOWNLOAD_DIR
                            os.makedirs(save_dir, exist_ok=True)
                            filename = result.get("filename", f"video_{uuid.uuid4().hex[:6]}.mp4")
                            filepath = os.path.join(save_dir, filename)

                            headers = {"User-Agent": HEADERS.get("user-agent", ""), "Referer": "https://www.terabox.com/"}
                            r = requests.get(download_url, headers=headers, stream=True, timeout=120)
                            if r.status_code == 403:
                                headers.pop("Referer", None)
                                r = requests.get(download_url, headers=headers, stream=True, timeout=120)

                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk: f.write(chunk)

                            job['completed'] += 1
                            mark_msg_processed(str(source_id), msg.id, "download")

                            if cloud_targets:
                                links = upload_to_cloud_targets(filepath, filename, cloud_targets)
                                job['cloud_links'].append({"filename": filename, "links": links})
                        except Exception as e:
                            job['failed'] += 1

            job['status'] = 'finished'
        except Exception as e:
            job['status'] = f'error: {str(e)}'
        finally:
            await client.disconnect()

    loop.run_until_complete(run_download())

# --- UI LAYOUT ---

st.sidebar.title("📦 Navigation")

if st.session_state.step in ["config", "login", "verify"]:
    st.sidebar.info("Please authenticate first.")
else:
    mode = st.sidebar.radio("Menu", ["Quick Download", "Bulk Downloader", "Channel Scraper", "Media Forwarder", "Job Manager", "User Management", "Admin System", "Premium & Codes", "Bot Console"])
    if st.sidebar.button("Logout"):
        st.session_state.session_string = ""
        st.session_state.step = "config"
        st.rerun()

# --- AUTHENTICATION FLOW ---

if st.session_state.step == "config":
    st.title("Login & Load Session")
    st.markdown("Enter your Telegram Phone Number to load your saved credentials, or enter new ones below.")
    
    phone_input = st.text_input("Your Telegram Phone Number (e.g. +1234567890)")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load Saved Session"):
            if not phone_input:
                st.error("Please enter your phone number.")
            else:
                # We use phone number as a pseudo user_id (hashed or raw) for multi-client
                pseudo_id = phone_to_uid(phone_input)
                api_id, api_hash, s_str = get_user_credentials(pseudo_id)
                if api_id and s_str:
                    st.session_state.api_id = int(api_id)
                    st.session_state.api_hash = api_hash
                    st.session_state.session_string = s_str
                    st.session_state.phone = phone_input
                    
                    is_auth = asyncio.run(check_login_status())
                    if is_auth:
                        st.success("Session loaded successfully!")
                        st.session_state.step = "job"
                        st.rerun()
                    else:
                        st.warning("Session expired. Please verify OTP.")
                        st.session_state.step = "login"
                        st.rerun()
                else:
                    st.error("No saved credentials found for this phone number.")

    st.markdown("---")
    st.subheader("Or Enter New Credentials")
    api_id_input = st.text_input("Telegram API ID")
    api_hash_input = st.text_input("Telegram API HASH")
    
    if st.button("Save & Continue"):
        if not phone_input or not api_id_input or not api_hash_input:
            st.error("Please provide Phone, API ID and API HASH.")
        else:
            try:
                st.session_state.api_id = int(api_id_input)
                st.session_state.api_hash = api_hash_input
                st.session_state.phone = phone_input
                
                pseudo_id = phone_to_uid(phone_input)
                save_user_credentials(pseudo_id, api_id_input, api_hash_input, "")
                
                is_auth = asyncio.run(check_login_status())
                st.session_state.step = "job" if is_auth else "login"
                st.rerun()
            except ValueError:
                st.error("API ID must be a number.")

elif st.session_state.step == "login":
    st.title("Telegram Login")
    phone_input = st.text_input("Phone Number (e.g. +1234567890)")
    if st.button("Send Login Code"):
        if not phone_input:
            st.error("Please enter a phone number.")
        else:
            with st.spinner("Requesting code from Telegram..."):
                pch, session_str, err = asyncio.run(send_auth_code(phone_input))
                if err:
                    st.error(f"Error: {err}")
                else:
                    st.session_state.phone = phone_input
                    st.session_state.phone_code_hash = pch
                    st.session_state.session_string = session_str
                    st.session_state.step = "verify"
                    st.rerun()

elif st.session_state.step == "verify":
    st.title("Verify OTP")
    st.info(f"Code sent to {st.session_state.phone}")
    code_input = st.text_input("Enter OTP Code")
    if st.button("Verify"):
        if not code_input:
            st.error("Please enter the code.")
        else:
            with st.spinner("Verifying code..."):
                success, session_str, err, needs_2fa = asyncio.run(verify_auth_code(st.session_state.phone, code_input, st.session_state.phone_code_hash))
                if needs_2fa:
                    st.session_state.session_string = session_str
                    st.session_state.step = "twofa"
                    st.rerun()
                elif success:
                    st.success("Successfully logged in!")
                    # Save the new session string
                    st.session_state.session_string = session_str
                    pseudo_id = phone_to_uid(st.session_state.phone)
                    save_user_credentials(pseudo_id, st.session_state.api_id, st.session_state.api_hash, session_str)

                    st.session_state.step = "job"
                    st.rerun()
                else:
                    st.error(f"Verification Failed: {err}")

elif st.session_state.step == "twofa":
    st.title("Two-Step Verification")
    st.info("This account has 2FA enabled. Enter your Telegram 2FA password to finish signing in.")
    password_input = st.text_input("2FA Password", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Verify 2FA"):
            if not password_input:
                st.error("Please enter your 2FA password.")
            else:
                with st.spinner("Verifying 2FA password..."):
                    success, session_str, err = asyncio.run(verify_2fa_password(
                        st.session_state.session_string, st.session_state.api_id,
                        st.session_state.api_hash, password_input,
                    ))
                    if success:
                        st.success("Successfully logged in!")
                        st.session_state.session_string = session_str
                        pseudo_id = phone_to_uid(st.session_state.phone)
                        save_user_credentials(pseudo_id, st.session_state.api_id, st.session_state.api_hash, session_str)
                        st.session_state.step = "job"
                        st.rerun()
                    else:
                        st.error(f"2FA Verification Failed: {err}")
    with col2:
        if st.button("Reset", key="twofa_reset"):
            st.session_state.step = "config"
            st.session_state.session_string = ""
            st.rerun()

# --- MAIN APP FLOW ---

elif st.session_state.step == "job":
    
    if not st.session_state.channels:
        with st.spinner("Loading channels..."):
            st.session_state.channels = asyncio.run(fetch_channels())
            
    channel_options = {"Saved Messages ('me')": 'me'}
    for c in st.session_state.channels:
        channel_options[c['name']] = c['id']
        
    if mode == "Quick Download":
        st.title("Quick Download")
        link_input = st.text_input("Terabox URL")
        target_name = st.selectbox("Upload to", list(channel_options.keys()))

        available_cloud = cloud_targets_available()
        selected_cloud = (
            st.multiselect("Also upload to", available_cloud, key="qd_cloud")
            if available_cloud else []
        )

        if st.button("Process Link"):
            if not link_input:
                st.error("Please provide a Terabox link.")
            else:
                with st.spinner("Extracting direct link..."):
                    result = extract_terabox_sync(link_input)
                if not result or not result.get("download"):
                    st.error("Failed to extract.")
                else:
                    target_id = channel_options[target_name]
                    filename = result.get("filename", f"video_{uuid.uuid4().hex[:6]}.mp4")
                    filepath = os.path.join(DOWNLOAD_DIR, filename)

                    with st.spinner(f"Downloading {result.get('title', filename)}..."):
                        try:
                            headers = {"User-Agent": HEADERS.get("user-agent", ""), "Referer": "https://www.terabox.com/"}
                            r = requests.get(result['download'], headers=headers, stream=True, timeout=120)
                            if r.status_code == 403:
                                headers.pop("Referer", None)
                                r = requests.get(result['download'], headers=headers, stream=True, timeout=120)
                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024 * 1024):
                                    if chunk:
                                        f.write(chunk)
                        except Exception as e:
                            st.error(f"Download failed: {e}")
                            filepath = None

                    if filepath and os.path.exists(filepath):
                        async def _send_quick(fp, tid, caption):
                            cl = get_client()
                            await cl.connect()
                            try:
                                await cl.send_file(tid, fp, caption=caption)
                            finally:
                                await cl.disconnect()

                        with st.spinner(f"Uploading to {target_name}..."):
                            try:
                                asyncio.run(_send_quick(filepath, target_id, result.get("title", "Downloaded video")))
                                st.success(f"Sent to {target_name}.")
                            except Exception as e:
                                st.error(f"Upload to Telegram failed: {e}")

                        if selected_cloud:
                            with st.spinner("Uploading to cloud target(s)..."):
                                links = upload_to_cloud_targets(filepath, filename, selected_cloud)
                                for tgt, url in links.items():
                                    st.write(f"**{tgt}:** {url or '_upload failed_'}")

                        try:
                            os.remove(filepath)
                        except Exception:
                            pass

    elif mode == "Bulk Downloader":
        st.title("Bulk Downloader")
        st.write("Scan a channel for Terabox links and download them to the server storage.")

        src_name = st.selectbox("Source Channel", list(channel_options.keys()), key="bd_src")
        limit = st.number_input("Messages to scan", min_value=1, max_value=5000, value=50, key="bd_lim")

        available_cloud = cloud_targets_available()
        selected_cloud = []
        if available_cloud:
            selected_cloud = st.multiselect(
                "Also upload each file to", available_cloud, key="bd_cloud",
                help="Configured via S3_BUCKET / GDRIVE_SERVICE_ACCOUNT_JSON env vars.",
            )
        else:
            st.caption("Cloud upload targets (S3 / Google Drive) are not configured — set S3_BUCKET or GDRIVE_SERVICE_ACCOUNT_JSON to enable.")

        if st.button("Start Bulk Download"):
            job_id = str(uuid.uuid4())
            st.session_state.background_jobs[job_id] = {
                'type': 'bulk_download',
                'src': src_name,
                'status': 'starting',
                'total': 0, 'completed': 0, 'failed': 0
            }

            src_id = channel_options[src_name]

            s_str = get_session_string()
            t = threading.Thread(target=downloader_worker, args=(st.session_state.background_jobs[job_id], src_id, limit, st.session_state.api_id, st.session_state.api_hash, s_str, selected_cloud))
            t.daemon = True
            t.start()

            st.success(f"Job started! Go to Job Manager to view progress.")
                    
    elif mode == "Channel Scraper":
        st.title("Channel Scraper")
        st.write("Scan a channel for Terabox links and re-upload the videos.")
        
        src_name = st.selectbox("Source Channel", list(channel_options.keys()), key="cs_src")
        tgt_name = st.selectbox("Target Channel", list(channel_options.keys()), key="cs_tgt")
        limit = st.number_input("Messages to scan", min_value=1, max_value=5000, value=50, key="cs_lim")
        
        if st.button("Start Scraper Job"):
            job_id = str(uuid.uuid4())
            st.session_state.background_jobs[job_id] = {
                'type': 'scraper',
                'src': src_name,
                'tgt': tgt_name,
                'status': 'starting',
                'total': 0, 'completed': 0, 'failed': 0
            }
            
            src_id = channel_options[src_name]
            tgt_id = channel_options[tgt_name]
            
            s_str = get_session_string()
            t = threading.Thread(target=scraper_worker, args=(st.session_state.background_jobs[job_id], src_id, tgt_id, limit, st.session_state.api_id, st.session_state.api_hash, s_str))
            t.daemon = True
            t.start()
            
            st.success(f"Job started! Go to Job Manager to view progress.")

    elif mode == "Media Forwarder":
        st.title("Media Forwarder")
        st.write("Forward media from one channel to another.")
        
        src_name = st.selectbox("Source Channel", list(channel_options.keys()), key="mf_src")
        tgt_name = st.selectbox("Target Channel", list(channel_options.keys()), key="mf_tgt")
        limit = st.number_input("Messages to scan", min_value=1, max_value=5000, value=50, key="mf_lim")
        
        if st.button("Start Forwarder Job"):
            job_id = str(uuid.uuid4())
            st.session_state.background_jobs[job_id] = {
                'type': 'forwarder',
                'src': src_name,
                'tgt': tgt_name,
                'status': 'starting',
                'total': 0, 'completed': 0, 'failed': 0
            }
            
            src_id = channel_options[src_name]
            tgt_id = channel_options[tgt_name]
            
            s_str = get_session_string()
            t = threading.Thread(target=forwarder_worker, args=(st.session_state.background_jobs[job_id], src_id, tgt_id, limit, st.session_state.api_id, st.session_state.api_hash, s_str))
            t.daemon = True
            t.start()
            
            st.success(f"Job started! Go to Job Manager to view progress.")

    elif mode == "Job Manager":
        st.title("Active Jobs")
        
        if st.button("Refresh Status"):
            st.rerun()
            
        if not st.session_state.background_jobs:
            st.info("No active jobs.")
        else:
            for jid, job in st.session_state.background_jobs.items():
                st.markdown(f"### Job: {job['type'].upper()} ({jid[:8]})")
                st.write(f"**Status:** {job['status']}")
                st.write(f"**Progress:** {job['completed']} / {job['total']} (Failed: {job['failed']})")
                
                col1, col2, col3 = st.columns(3)
                if job['status'] == 'running':
                    if col1.button("Pause", key=f"p_{jid}"):
                        job['status'] = 'paused'
                        st.rerun()
                elif job['status'] == 'paused':
                    if col1.button("Resume", key=f"r_{jid}"):
                        job['status'] = 'running'
                        st.rerun()
                        
                if job['status'] not in ['stopped', 'finished', 'error']:
                    if col2.button("Stop", key=f"s_{jid}"):
                        job['status'] = 'stopped'
                        st.rerun()

                if job.get('cloud_links'):
                    with st.expander(f"Cloud uploads ({len(job['cloud_links'])})"):
                        for entry in job['cloud_links']:
                            for target, url in entry['links'].items():
                                st.write(f"**{entry['filename']}** → {target}: {url or '_upload failed_'}")
                st.markdown("---")

    elif mode == "User Management":
        st.title("User Management")
        
        # Pending Users
        st.subheader("Pending Users")
        pending = get_pending_users()
        if pending:
            for row in pending:
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                c1.write(f"**ID:** {row['user_id']}")
                c2.write(f"**Name:** {row['first_name']} (@{row['username']})")
                if c3.button("Approve", key=f"app_{row['user_id']}"):
                    approve_user(row['user_id'])
                    st.success(f"Approved {row['user_id']}")
                    st.rerun()
                if c4.button("Reject", key=f"rej_{row['user_id']}"):
                    reject_user(row['user_id'])
                    st.success(f"Rejected {row['user_id']}")
                    st.rerun()
        else:
            st.info("No pending users.")
            
        st.markdown("---")
        
        # All Approved Users
        st.subheader("Approved Users")
        with get_db() as conn:
            all_users = conn.execute("SELECT user_id, username, first_name, is_banned, is_approved FROM users").fetchall()
            
        if all_users:
            df_users = pd.DataFrame([dict(row) for row in all_users])
            st.dataframe(df_users)
            
            st.write("### Quick Actions")
            for row in all_users[:50]:  # Limit to 50 for UI performance
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"{row['first_name']} (ID: {row['user_id']})")
                if row['is_banned']:
                    if c2.button("Unban", key=f"unban_{row['user_id']}"):
                        unban_user(row['user_id'])
                        st.rerun()
                else:
                    if c3.button("Ban", key=f"ban_{row['user_id']}"):
                        ban_user(row['user_id'])
                        st.rerun()
        else:
            st.info("No approved users.")

    elif mode == "Admin System":
        st.title("Admin System")
        
        st.subheader("Platform Stats")
        total, approved, banned, links, today, pending = get_admin_stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Users", total)
        c2.metric("Approved Users", approved)
        c3.metric("Pending Approvals", pending)
        
        c4, c5, c6 = st.columns(3)
        c4.metric("Banned Users", banned)
        c5.metric("Total Links Processed", links)
        c6.metric("Links Today", today)
        
        st.markdown("---")
        st.subheader("Broadcast Message")
        b_msg = st.text_area("Enter message to send to all approved users:")
        if st.button("Send Broadcast"):
            if b_msg.strip():
                users = get_all_user_ids()
                success = 0
                import requests
                for u in users:
                    try:
                        r = requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={"chat_id": u, "text": b_msg, "parse_mode": "HTML"}
                        )
                        if r.status_code == 200: success += 1
                    except: pass
                st.success(f"Broadcast sent to {success}/{len(users)} users.")
            else:
                st.error("Message cannot be empty.")

    elif mode == "Premium & Codes":
        st.title("Premium Management")
        
        st.subheader("Generate Premium Code")
        plan = st.selectbox("Select Plan", ["PRO_1M", "PRO_3M", "PRO_1Y", "PRO_LIFETIME"])
        if st.button("Generate Code"):
            code = generate_premium_code(999999999, plan) # using dummy admin id for generation audit
            st.success(f"Generated Code: `{code}`")
            st.rerun()
            
        st.markdown("---")
        st.subheader("Direct Add Premium")
        with get_db() as conn:
            all_users = conn.execute("SELECT user_id, username, first_name FROM users WHERE is_approved=1").fetchall()
        user_opts = {f"{r['first_name']} (ID: {r['user_id']})": r['user_id'] for r in all_users}
        if user_opts:
            sel_u = st.selectbox("Select User", list(user_opts.keys()))
            sel_p = st.selectbox("Select Plan to give", ["PRO_1M", "PRO_3M", "PRO_1Y", "PRO_LIFETIME"])
            if st.button("Add Premium to User"):
                activate_premium(user_opts[sel_u], sel_p)
                st.success("Premium activated for user.")
        else:
            st.info("No approved users to give premium.")
            
        st.markdown("---")
        st.subheader("Generated Codes")
        codes = get_all_premium_codes(None)
        if codes:
            df_codes = pd.DataFrame([dict(r) for r in codes])
            st.dataframe(df_codes)
        else:
            st.info("No premium codes found.")

    elif mode == "Bot Console":
        st.subheader("Bot Console (Execute Commands)")
        st.markdown("Use this tab to run any bot command directly from the Streamlit UI! It sends the command via your Userbot.")
        try:
            bot_info = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe").json()
            bot_username = bot_info['result']['username']
            
            cmd_opts = ["/status", "/channels", "/stats", "/admin_stats", "/backup", "/help", "/proxy_status", "/api_health", "/users", "/premiumcodes", "/pending", "/pause", "/resume", "/stop"]
            selected_cmd = st.selectbox("Select Command to Run", cmd_opts)
            custom_cmd = st.text_input("Or type custom command (e.g. /approve 12345)")
            
            if st.button("Run Command 🚀"):
                final_cmd = custom_cmd if custom_cmd else selected_cmd
                st.write(f"Executing `{final_cmd}` on bot `@{bot_username}`...")

                async def run_bot_command(cmd_text, b_username, timeout=10.0):
                    """Send a command and capture the bot's reply as it arrives.

                    Uses Telethon's push-based update stream instead of a fixed
                    sleep + last-N-messages guess: the handler fires the moment
                    Telegram delivers the bot's response, so slow replies still
                    get captured and fast replies don't wait out a fixed delay.
                    """
                    cl = get_client()
                    await cl.connect()
                    replies: list[str] = []
                    got_reply = asyncio.Event()

                    @cl.on(events.NewMessage(incoming=True, from_users=b_username))
                    async def _on_reply(event):
                        if event.text:
                            replies.append(event.text)
                        got_reply.set()

                    try:
                        await cl.send_message(b_username, cmd_text)
                        try:
                            await asyncio.wait_for(got_reply.wait(), timeout=timeout)
                        except asyncio.TimeoutError:
                            pass
                    finally:
                        cl.remove_event_handler(_on_reply)
                        await cl.disconnect()
                    return replies

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                replies = loop.run_until_complete(run_bot_command(final_cmd, bot_username))
                if replies:
                    for text in replies:
                        st.info(text)
                else:
                    st.warning("No reply received from the bot within 10s.")
        except Exception as e:
            st.error(f"Could not connect to bot console: {e}")
