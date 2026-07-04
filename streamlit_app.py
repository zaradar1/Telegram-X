import streamlit as st
import asyncio
import os
import time
import requests
import tempfile
import threading
from io import BytesIO
from telethon import TelegramClient, errors
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
        DOWNLOAD_DIR, BOT_TOKEN
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
    cl = get_client()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(cl.connect())
    s = cl.session.save()
    loop.run_until_complete(cl.disconnect())
    return s

def get_client():
    if st.session_state.session_string:
        return TelegramClient(StringSession(st.session_state.session_string), st.session_state.api_id, st.session_state.api_hash)
    else:
        # Create a new memory session if none exists
        return TelegramClient(StringSession(), st.session_state.api_id, st.session_state.api_hash)


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
        return True, client.session.save(), None
    except errors.SessionPasswordNeededError:
        return False, None, "2FA Password needed. (Not supported in this basic UI yet)"
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
                
                job['total'] += 1
                try:
                    # Actually forward media by re-uploading or forwarding
                    if msg.media:
                        await client.send_message(target_id, message=msg)
                    job['completed'] += 1
                except Exception as e:
                    job['failed'] += 1
            
            job['status'] = 'finished'
        except Exception as e:
            job['status'] = f'error: {str(e)}'
        finally:
            await client.disconnect()

    loop.run_until_complete(run_forward())

def downloader_worker(job, source_id, limit, api_id, api_hash, session_str):
    job['status'] = 'running'
    
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
                            filepath = os.path.join(save_dir, result.get("filename", f"video_{uuid.uuid4().hex[:6]}.mp4"))
                            
                            headers = {"User-Agent": HEADERS.get("user-agent", ""), "Referer": "https://www.terabox.com/"}
                            r = requests.get(download_url, headers=headers, stream=True, timeout=120)
                            if r.status_code == 403:
                                headers.pop("Referer", None)
                                r = requests.get(download_url, headers=headers, stream=True, timeout=120)
                            
                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk: f.write(chunk)
                                    
                            job['completed'] += 1
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
                pseudo_id = hash(phone_input) % (10**8)
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
                
                pseudo_id = hash(phone_input) % (10**8)
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
                success, session_str, err = asyncio.run(verify_auth_code(st.session_state.phone, code_input, st.session_state.phone_code_hash))
                if success:
                    st.success("Successfully logged in!")
                    # Save the new session string
                    st.session_state.session_string = session_str
                    pseudo_id = hash(st.session_state.phone) % (10**8)
                    save_user_credentials(pseudo_id, st.session_state.api_id, st.session_state.api_hash, session_str)
    
                    st.session_state.step = "job"
                    st.rerun()
                else:
                    st.error(f"Verification Failed: {err}")

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
        
        if st.button("Process Link"):
            if not link_input:
                st.error("Please provide a Terabox link.")
            else:
                with st.spinner("Extracting direct link..."):
                    result = extract_terabox_sync(link_input)
                if not result or not result.get("download"):
                    st.error("Failed to extract.")
                else:
                    job_id = str(uuid.uuid4())
                    st.session_state.background_jobs[job_id] = {
                        'type': 'quick_dl',
                        'status': 'starting',
                        'total': 1, 'completed': 0, 'failed': 0
                    }
                    st.info(f"Queued: {result.get('title')}")
                    st.success("Please use Job Manager for bulk, or background logic here.")

    elif mode == "Bulk Downloader":
        st.title("Bulk Downloader")
        st.write("Scan a channel for Terabox links and download them to the server storage.")
        
        src_name = st.selectbox("Source Channel", list(channel_options.keys()), key="bd_src")
        limit = st.number_input("Messages to scan", min_value=1, max_value=5000, value=50, key="bd_lim")
        
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
            t = threading.Thread(target=downloader_worker, args=(st.session_state.background_jobs[job_id], src_id, limit, st.session_state.api_id, st.session_state.api_hash, s_str))
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
                
                async def run_bot_command(cmd_text, b_username):
                    cl = get_client()
                    await cl.connect()
                    await cl.send_message(b_username, cmd_text)
                    await asyncio.sleep(2.0)
                    msgs = await cl.get_messages(b_username, limit=5)
                    await cl.disconnect()
                    return msgs
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                res_msgs = loop.run_until_complete(run_bot_command(final_cmd, bot_username))
                for m in reversed(res_msgs):
                    if not m.out and m.text:
                        st.info(m.text)
        except Exception as e:
            st.error(f"Could not connect to bot console: {e}")
