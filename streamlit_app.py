#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM ACCOUNT LOGIN & MANAGER
Modern Streamlit UI for Telegram account login and information retrieval
"""

import streamlit as st
import asyncio
import json
import os
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

try:
    from telethon import TelegramClient, errors
    from telethon.tl.types import User
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    st.error("❌ pip install telethon")
    st.stop()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ══════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="📱 Telegram Account Manager",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ══════════════════════════════════════════════════════════════════════
# CUSTOM STYLING
# ══════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
    .auth-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .success-box {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #28a745;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #dc3545;
    }
    .info-box {
        background-color: #d1ecf1;
        padding: 1rem;
        border-radius: 8px;
        border-left: 5px solid #17a2b8;
    }
    .user-card {
        background: white;
        border: 2px solid #e1e4e8;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════
if "logged_in_users" not in st.session_state:
    st.session_state.logged_in_users = {}

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "temp_client" not in st.session_state:
    st.session_state.temp_client = None

if "login_step" not in st.session_state:
    st.session_state.login_step = 0  # 0: initial, 1: code sent, 2: code entered, 3: 2fa needed

if "temp_phone" not in st.session_state:
    st.session_state.temp_phone = None

if "temp_api_id" not in st.session_state:
    st.session_state.temp_api_id = None

if "temp_api_hash" not in st.session_state:
    st.session_state.temp_api_hash = None

# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

SESSION_DIR = Path.home() / ".telegram_sessions"
SESSION_DIR.mkdir(exist_ok=True)

# Create a persistent event loop for Telethon clients
@st.cache_resource
def get_event_loop():
    """Get or create a persistent event loop for async operations"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

def run_async(coro):
    """Run async code safely using the persistent event loop"""
    loop = get_event_loop()
    return loop.run_until_complete(coro)

async def send_login_code(api_id: int, api_hash: str, phone: str) -> Tuple[bool, str, Optional[TelegramClient]]:
    """
    Step 1: Send login code to user's Telegram
    
    Returns:
        Tuple of (success, message, client)
    """
    try:
        session_name = f"session_{phone.replace('+', '')}"
        client = TelegramClient(
            str(SESSION_DIR / session_name),
            api_id,
            api_hash
        )
        
        await client.connect()
        
        # Check if already logged in
        if await client.is_user_authorized():
            return True, f"✅ Already logged in as {phone}", client
        
        # Request code to be sent
        result = await client.send_code_request(phone)
        return False, f"📱 OTP sent! Code expires in {result.timeout}s. Please enter it.", client
            
    except errors.PhoneNumberInvalidError:
        return False, "❌ Invalid phone number format. Use +1234567890", None
    except errors.PhoneNumberBannedError:
        return False, "🚫 This phone number is banned from Telegram.", None
    except errors.FloodWaitError as e:
        return False, f"⏱️ Too many attempts. Wait {e.seconds} seconds.", None
    except Exception as e:
        return False, f"❌ Error sending code: {str(e)}", None


async def verify_login_code(client: TelegramClient, phone: str, otp: str, password: Optional[str] = None) -> Tuple[bool, str, Optional[TelegramClient]]:
    """
    Step 2: Verify the OTP code and login
    
    Returns:
        Tuple of (success, message, client)
    """
    try:
        # Verify code
        await client.sign_in(phone, otp)
        
        me = await client.get_me()
        return True, f"✅ Logged in successfully as {me.first_name}!", client
            
    except SessionPasswordNeededError:
        return False, "🔐 Two-factor authentication required. Please enter your password.", client
    except errors.PhoneCodeInvalidError:
        return False, "❌ Invalid OTP code. Please try again.", None
    except errors.PhoneCodeExpiredError:
        return False, "⏰ OTP code expired. Request a new one.", None
    except Exception as e:
        return False, f"❌ Verification failed: {str(e)}", None


async def verify_2fa_password(client: TelegramClient, password: str) -> Tuple[bool, str, Optional[TelegramClient]]:
    """
    Step 3: Verify 2FA password if needed
    
    Returns:
        Tuple of (success, message, client)
    """
    try:
        await client.sign_in(password=password)
        
        me = await client.get_me()
        return True, f"✅ Logged in successfully as {me.first_name}!", client
            
    except errors.PasswordHashInvalidError:
        return False, "❌ Invalid 2FA password. Please try again.", None
    except Exception as e:
        return False, f"❌ 2FA verification failed: {str(e)}", None


async def get_user_info(client: TelegramClient) -> Optional[Dict[str, Any]]:
    """Get current user information"""
    try:
        me = await client.get_me()
        
        # Get user statistics
        dialogs = await client.get_dialogs(limit=None)
        
        user_info = {
            "user_id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "None",
            "phone": me.phone or "Hidden",
            "is_bot": me.bot,
            "is_premium": me.premium,
            "total_dialogs": len(dialogs),
            "bio": me.about or "Not set",
        }
        
        return user_info
    except Exception as e:
        log.error(f"Error getting user info: {e}")
        return None


async def get_all_chats(client: TelegramClient) -> list:
    """Get all user chats and groups"""
    try:
        dialogs = await client.get_dialogs(limit=None)
        chats = []
        
        for dialog in dialogs:
            entity = dialog.entity
            chat_info = {
                "name": entity.title if hasattr(entity, 'title') else entity.first_name,
                "type": "Group" if hasattr(entity, 'title') else "Private",
                "members": entity.participants_count if hasattr(entity, 'participants_count') else 0,
                "id": entity.id,
                "unread_count": dialog.unread_count,
            }
            chats.append(chat_info)
        
        return sorted(chats, key=lambda x: x['unread_count'], reverse=True)
    except Exception as e:
        log.error(f"Error getting chats: {e}")
        return []


async def close_client(client: TelegramClient):
    """Safely close Telegram client"""
    try:
        if client:
            await client.disconnect()
    except Exception as e:
        log.error(f"Error closing client: {e}")


# ══════════════════════════════════════════════════════════════════════
# MAIN UI
# ══════════════════════════════════════════════════════════════════════

st.markdown("# 📱 Telegram Account Manager")
st.markdown("---")

# Create tabs
tab1, tab2, tab3 = st.tabs(["🔐 Login", "👤 My Accounts", "📊 Account Info"])

# ══════════════════════════════════════════════════════════════════════
# TAB 1: LOGIN
# ══════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Login to Your Telegram Account")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if st.session_state.login_step == 0:
            st.markdown("#### Step 1️⃣: API Credentials")
            st.info("📋 Get your API credentials from [my.telegram.org](https://my.telegram.org/)", icon="ℹ️")
            
            api_id = st.number_input(
                "API ID",
                min_value=1,
                help="Your Telegram API ID",
                key="api_id_input"
            )
            
            api_hash = st.text_input(
                "API Hash",
                type="password",
                help="Your Telegram API Hash",
                key="api_hash_input"
            )
            
            st.markdown("#### Step 2️⃣: Phone Number")
            
            phone = st.text_input(
                "Phone Number",
                placeholder="+1234567890",
                help="Include country code",
                key="phone_input"
            )
            
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("🔐 Send OTP", use_container_width=True, type="primary"):
                    if not api_id or not api_hash or not phone:
                        st.error("❌ Please fill in all fields")
                    else:
                        with st.spinner("Sending OTP..."):
                            try:
                                success, msg, client = run_async(
                                    send_login_code(int(api_id), api_hash, phone)
                                )
                                
                                if not success:  # Code was sent
                                    st.session_state.login_step = 1
                                    st.session_state.temp_client = client
                                    st.session_state.temp_phone = phone
                                    st.session_state.temp_api_id = api_id
                                    st.session_state.temp_api_hash = api_hash
                                    st.success(msg)
                                    st.rerun()
                                else:  # Already logged in
                                    st.session_state.logged_in_users[phone] = client
                                    st.session_state.current_user = phone
                                    st.session_state.login_step = 0
                                    st.success(msg)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
        
        elif st.session_state.login_step == 1:
            st.markdown("#### Step 3️⃣: Verify OTP")
            st.info(f"📱 An OTP code has been sent to {st.session_state.temp_phone}", icon="ℹ️")
            
            otp = st.text_input(
                "Verification Code (OTP)",
                max_chars=5,
                placeholder="00000",
                help="Code sent to your Telegram",
                key="otp_input"
            )
            
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("✅ Verify Code", use_container_width=True, type="primary"):
                    if not otp:
                        st.error("❌ Please enter the OTP")
                    else:
                        with st.spinner("Verifying..."):
                            try:
                                success, msg, client = run_async(
                                    verify_login_code(
                                        st.session_state.temp_client,
                                        st.session_state.temp_phone,
                                        otp
                                    )
                                )
                                
                                if success:
                                    st.session_state.logged_in_users[st.session_state.temp_phone] = client
                                    st.session_state.current_user = st.session_state.temp_phone
                                    st.session_state.login_step = 0
                                    st.session_state.temp_client = None
                                    st.session_state.temp_phone = None
                                    st.success(msg)
                                    st.rerun()
                                elif "Two-factor" in msg:
                                    st.session_state.login_step = 2
                                    st.warning(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
            
            with col_btn2:
                if st.button("🔄 Reset", use_container_width=True):
                    st.session_state.login_step = 0
                    st.session_state.temp_client = None
                    st.session_state.temp_phone = None
                    st.rerun()
        
        elif st.session_state.login_step == 2:
            st.markdown("#### Step 4️⃣: Enter 2FA Password")
            st.warning("🔐 Two-factor authentication is enabled on this account", icon="⚠️")
            
            password = st.text_input(
                "2FA Password",
                type="password",
                placeholder="Enter your 2FA password",
                key="password_input"
            )
            
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("✅ Verify 2FA", use_container_width=True, type="primary"):
                    if not password:
                        st.error("❌ Please enter your 2FA password")
                    else:
                        with st.spinner("Verifying 2FA..."):
                            try:
                                success, msg, client = run_async(
                                    verify_2fa_password(st.session_state.temp_client, password)
                                )
                                
                                if success:
                                    st.session_state.logged_in_users[st.session_state.temp_phone] = client
                                    st.session_state.current_user = st.session_state.temp_phone
                                    st.session_state.login_step = 0
                                    st.session_state.temp_client = None
                                    st.session_state.temp_phone = None
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
            
            with col_btn2:
                if st.button("🔄 Reset", use_container_width=True):
                    st.session_state.login_step = 0
                    st.session_state.temp_client = None
                    st.session_state.temp_phone = None
                    st.rerun()
    
    with col2:
        st.markdown("#### 📋 Quick Tips")
        st.markdown("""
        **Requirements:**
        - Valid Telegram account
        - API credentials
        - Phone number with country code
        
        **Format:**
        - Phone: +CountryCodeNumber
        - Example: +1234567890
        
        **Security:**
        - Sessions stored locally
        - No data to external servers
        - 2FA supported
        
        **Troubleshooting:**
        - OTP expires in ~5 min
        - Max 5 attempts before wait
        - Always use country code
        """)


# ══════════════════════════════════════════════════════════════════════
# TAB 2: LOGGED IN ACCOUNTS
# ══════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Logged In Accounts")
    
    if not st.session_state.logged_in_users:
        st.info("📭 No logged in accounts yet. Login from the 🔐 Login tab.", icon="ℹ️")
    else:
        for phone, client in st.session_state.logged_in_users.items():
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.markdown(f"**📱 {phone}**")
                
                with col2:
                    if st.button("📋 View Info", key=f"view_{phone}", use_container_width=True):
                        st.session_state.current_user = phone
                
                with col3:
                    if st.button("🚪 Logout", key=f"logout_{phone}", use_container_width=True):
                        run_async(close_client(client))
                        del st.session_state.logged_in_users[phone]
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════
# TAB 3: ACCOUNT INFORMATION
# ══════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Account Information")
    
    if not st.session_state.logged_in_users:
        st.warning("⚠️ Please login first from the 🔐 Login tab", icon="⚠️")
    else:
        # Select account
        selected_phone = st.selectbox(
            "Select Account",
            list(st.session_state.logged_in_users.keys()),
            key="account_select"
        )
        
        client = st.session_state.logged_in_users[selected_phone]
        
        # Get user info
        with st.spinner("Loading user information..."):
            try:
                user_info = run_async(get_user_info(client))
                
                if user_info:
                    # User Profile Card
                    st.markdown("### 👤 User Profile")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("User ID", user_info['user_id'])
                    with col2:
                        st.metric("Total Chats", user_info['total_dialogs'])
                    with col3:
                        st.metric("Account Type", "🤖 Bot" if user_info['is_bot'] else "👤 User")
                    
                    st.markdown("---")
                    
                    # User Details
                    st.markdown("### 📋 Details")
                    
                    details_col1, details_col2 = st.columns(2)
                    
                    with details_col1:
                        st.write(f"**First Name:** {user_info['first_name']}")
                        st.write(f"**Last Name:** {user_info['last_name']}")
                        st.write(f"**Username:** @{user_info['username']}")
                    
                    with details_col2:
                        st.write(f"**Phone:** {user_info['phone']}")
                        st.write(f"**Premium:** {'✅ Yes' if user_info['is_premium'] else '❌ No'}")
                        st.write(f"**Bio:** {user_info['bio']}")
                    
                    st.markdown("---")
                    
                    # Chats & Groups
                    st.markdown("### 💬 Chats & Groups")
                    
                    with st.spinner("Loading chats..."):
                        chats = run_async(get_all_chats(client))
                        
                        if chats:
                            # Show stats
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                groups = len([c for c in chats if c['type'] == 'Group'])
                                st.metric("Groups", groups)
                            
                            with col2:
                                private_chats = len([c for c in chats if c['type'] == 'Private'])
                                st.metric("Private Chats", private_chats)
                            
                            with col3:
                                total_unread = sum(c['unread_count'] for c in chats)
                                st.metric("Unread Messages", total_unread)
                            
                            st.markdown("---")
                            
                            # Chats table
                            st.markdown("#### All Chats")
                            
                            import pandas as pd
                            df = pd.DataFrame(chats)
                            df = df[['name', 'type', 'members', 'unread_count']]
                            df.columns = ['Chat Name', 'Type', 'Members', 'Unread']
                            
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.info("No chats found")
                else:
                    st.error("Failed to load user information")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.85rem;">
    <p>🔒 <strong>Privacy Notice:</strong> Your sessions are stored locally and never shared.</p>
    <p>Built with ❤️ using Streamlit & Telethon</p>
</div>
""", unsafe_allow_html=True)
