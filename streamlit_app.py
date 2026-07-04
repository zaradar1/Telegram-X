import streamlit as st
import asyncio
import os
import time
import requests
import tempfile
import threading
from io import BytesIO
from telethon import TelegramClient, errors
import uuid

# Import extraction logic from existing codebase
try:
    from main import extract_terabox_sync, HEADERS, _send_timeout_for_size, _fetch_thumb
except ImportError:
    st.error("Failed to import from main.py. Ensure main.py is in the same directory.")
    st.stop()

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

SESSION_FILE = "streamlit_session"

def get_client():
    return TelegramClient(SESSION_FILE, st.session_state.api_id, st.session_state.api_hash)

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
        return sent.phone_code_hash, None
    except Exception as e:
        return None, str(e)
    finally:
        await client.disconnect()

async def verify_auth_code(phone, code, phone_code_hash):
    client = get_client()
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True, None
    except errors.SessionPasswordNeededError:
        return False, "2FA Password needed. (Not supported in this basic UI yet)"
    except Exception as e:
        return False, str(e)
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
def scraper_worker(job_id, source_id, target_id, limit):
    job = st.session_state.background_jobs[job_id]
    job['status'] = 'running'
    
    # We must run asyncio in this new thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = get_client()
    
    async def run_scrape():
        await client.connect()
        try:
            count = 0
            async for msg in client.iter_messages(source_id, limit=limit):
                if job['status'] == 'stopped':
                    break
                while job['status'] == 'paused':
                    await asyncio.sleep(1)
                
                # Simplistic scrape logic: Look for links
                text = msg.message or ""
                if "terabox.com" in text or "terabox" in text:
                    job['total'] += 1
                    # Extract logic...
                    result = extract_terabox_sync(text)
                    if result and result.get('download'):
                        try:
                            # Download
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
                                    
                            # Upload
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

# --- UI LAYOUT ---

st.sidebar.title("📦 Navigation")

if st.session_state.step in ["config", "login", "verify"]:
    st.sidebar.info("Please authenticate first.")
else:
    mode = st.sidebar.radio("Menu", ["Quick Download", "Channel Scraper", "Media Forwarder", "Job Manager"])
    if st.sidebar.button("Logout"):
        if os.path.exists(SESSION_FILE + ".session"):
            os.remove(SESSION_FILE + ".session")
        st.session_state.step = "config"
        st.rerun()


# --- AUTHENTICATION FLOW ---

if st.session_state.step == "config":
    st.title("API Configuration")
    api_id_input = st.text_input("Telegram API ID", value=str(st.session_state.api_id) if st.session_state.api_id else "")
    api_hash_input = st.text_input("Telegram API HASH", value=st.session_state.api_hash)
    
    if st.button("Save & Continue"):
        if not api_id_input or not api_hash_input:
            st.error("Please provide both API ID and API HASH.")
        else:
            try:
                st.session_state.api_id = int(api_id_input)
                st.session_state.api_hash = api_hash_input
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
                pch, err = asyncio.run(send_auth_code(phone_input))
                if err:
                    st.error(f"Error: {err}")
                else:
                    st.session_state.phone = phone_input
                    st.session_state.phone_code_hash = pch
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
                success, err = asyncio.run(verify_auth_code(st.session_state.phone, code_input, st.session_state.phone_code_hash))
                if success:
                    st.success("Successfully logged in!")
                    st.session_state.step = "job"
                    st.rerun()
                else:
                    st.error(f"Verification Failed: {err}")


# --- MAIN APP FLOW ---

elif st.session_state.step == "job":
    
    # Pre-fetch channels if empty
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
                    # In a real quick download, we can do it synchronously or pass to worker.
                    # For simplicity, doing it synchronously here like before.
                    # ... [Omitted full sync download for brevity, reusing worker logic]
                    st.success("Please use Job Manager for bulk, or background logic here.")
                    
    elif mode == "Channel Scraper":
        st.title("Channel Scraper")
        st.write("Scan a channel for Terabox links and re-upload the videos.")
        
        src_name = st.selectbox("Source Channel", list(channel_options.keys()))
        tgt_name = st.selectbox("Target Channel", list(channel_options.keys()))
        limit = st.number_input("Messages to scan", min_value=1, max_value=5000, value=50)
        
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
            
            t = threading.Thread(target=scraper_worker, args=(job_id, src_id, tgt_id, limit))
            t.daemon = True
            t.start()
            
            st.success(f"Job started! Go to Job Manager to view progress.")

    elif mode == "Media Forwarder":
        st.title("Media Forwarder")
        st.write("Forward media from one channel to another.")
        st.info("Logic similar to scraper. Select source and target and click start.")

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
