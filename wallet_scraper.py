# wallet_scraper.py - Avalanche Active Wallet Scraper (Moralis + Free RPC)
import requests
import time
import json
import os
from datetime import datetime
from web3 import Web3
import boto3
import logging
from logging.handlers import RotatingFileHandler

# ============================================
# LOGGING SETUP
# ============================================
def setup_logging():
    """Setup logging for scraper"""
    logger = logging.getLogger('scraper')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler('scraper.log', mode='w')
    file_handler.setLevel(logging.DEBUG)  # Capture all levels including errors
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# ============================================
# CONFIGURATION
# ============================================
AVAX_RPC = "https://api.avax.network/ext/bc/C/rpc"
DAILY_TARGET = 4000
RAW_WALLET_TARGET = 20000
USD_THRESHOLD = 1
SCRAPED_WALLETS_FILE = "scraped_wallets.json"
SCRAPER_STATUS_FILE = "scraper_status.json"
SCRAPER_PID_FILE = "scraper.pid"

# AWS clients
ses_client = boto3.client('ses')

# Get configuration from environment or hardcode
# Option 1: Hardcode directly (replace the string below with your actual API key)
MORALIS_API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IjQyMDAxYTg4LTQ4ZDUtNDcxNC04ZTJjLThjMzg4NTRjY2VlZCIsIm9yZ0lkIjoiNDgxNDM0IiwidXNlcklkIjoiNDk1MzAxIiwidHlwZUlkIjoiZDUwMmJhZGQtMWU5OS00YzEwLTg5YjQtMWJkMDJiOWFjNzViIiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3NjMxNTkxNDksImV4cCI6NDkxODkxOTE0OX0.O80UwB0x7Is0sAAYnjLkL-TT6R16KRT_xKzfU_vKkrk' # TODO: Replace with your Moralis API key

# Option 2: Or use environment variable (uncomment line below and comment line above)
# MORALIS_API_KEY = os.getenv('MORALIS_API_KEY', 'YOUR_MORALIS_API_KEY_HERE')

EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

# Public sources
SNOWTRACE_TX_URL = "https://api.snowtrace.io/api?module=account&action=txlist&address={}&startblock=1&endblock=99999999&page=1&offset=200&sort=desc"

# ============================================
# RPC SETUP
# ============================================
w3 = Web3(Web3.HTTPProvider(AVAX_RPC))

# ============================================
# MORALIS API KEY
# ============================================
def get_moralis_api_key():
    """Get Moralis API key (hardcoded or from environment)"""
    if MORALIS_API_KEY == 'YOUR_MORALIS_API_KEY_HERE':
        logger.warning("⚠️ Using default Moralis API key placeholder - please set MORALIS_API_KEY environment variable or update the code")
    return MORALIS_API_KEY

# ============================================
# LOAD/SAVE SCRAPED WALLETS
# ============================================
def load_scraped_wallets():
    """Load scraped wallets from JSON file"""
    try:
        if os.path.exists(SCRAPED_WALLETS_FILE):
            try:
                with open(SCRAPED_WALLETS_FILE, "r") as f:
                    data = json.load(f)
                    wallets = data.get("wallets", [])
                    master_set = set(data.get("master_set", []))
                    return wallets, master_set
            except json.JSONDecodeError as e:
                error_msg = f"Failed to parse JSON file {SCRAPED_WALLETS_FILE}: {str(e)}"
                logger.error("❌ %s", error_msg, exc_info=True)
                send_error_email("JSON Parse Error", error_msg, str(e))
                return [], set()
            except Exception as e:
                error_msg = f"Error loading scraped wallets from {SCRAPED_WALLETS_FILE}: {str(e)}"
                logger.error("❌ %s", error_msg, exc_info=True)
                send_error_email("File Read Error", error_msg, str(e))
                return [], set()
        return [], set()
    except Exception as e:
        error_msg = f"Unexpected error in load_scraped_wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Unexpected Error", error_msg, str(e))
        return [], set()

def save_scraped_wallets(wallets, master_set):
    """Save scraped wallets to JSON file"""
    try:
        data = {
            "wallets": wallets,
            "master_set": list(master_set),
            "last_updated": datetime.now().isoformat()
        }
        with open(SCRAPED_WALLETS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("✅ Saved %d wallets to %s", len(wallets), SCRAPED_WALLETS_FILE)
    except PermissionError as e:
        error_msg = f"Permission denied when saving to {SCRAPED_WALLETS_FILE}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("File Permission Error", error_msg, str(e))
    except OSError as e:
        error_msg = f"OS error when saving to {SCRAPED_WALLETS_FILE}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("File System Error", error_msg, str(e))
    except Exception as e:
        error_msg = f"Unexpected error saving scraped wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Save Error", error_msg, str(e))

def update_scraper_status(status, wallets_collected=0, message=""):
    """Update scraper status file"""
    try:
        status_data = {
            "status": status,  # running, completed, stopped
            "wallets_collected": wallets_collected,
            "target": DAILY_TARGET,
            "last_update": datetime.now().isoformat(),
            "message": message
        }
        with open(SCRAPER_STATUS_FILE, "w") as f:
            json.dump(status_data, f, indent=2)
    except Exception as e:
        error_msg = f"Failed to update scraper status file: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Status Update Error", error_msg, str(e))

# ============================================
# Step 1 — Collect raw Avalanche wallets
# ============================================
def fetch_raw_wallets(limit=20000):
    """Fetch raw wallet addresses from Snowtrace"""
    wallets = set()
    logger.info("📡 Collecting active wallets (raw)...")
    
    # Using known active contracts
    active_contracts = [
        "0xE54Ca86531e17Ef3616d22Ca28b0D458b6C89106",  # Pangolin Router
        "0x9e90F9B1C0904b8C474b05c226c1E18b1dA53fC7",  # Trader Joe Router
    ]
    
    errors_encountered = []
    for contract in active_contracts:
        url = SNOWTRACE_TX_URL.format(contract)
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()  # Raise exception for bad status codes
            data = resp.json()
            if "result" not in data:
                logger.warning("No 'result' field in response from %s", contract)
                continue
            
            for tx in data["result"]:
                if tx.get("from"):
                    wallets.add(tx["from"].lower())
                if tx.get("to"):
                    wallets.add(tx["to"].lower())
                
                if len(wallets) >= limit:
                    logger.info(f"✔ Collected {len(wallets)} raw wallets")
                    return list(wallets)
        except requests.exceptions.Timeout as e:
            error_msg = f"Timeout fetching from contract {contract}: {str(e)}"
            logger.error("❌ %s", error_msg, exc_info=True)
            errors_encountered.append(error_msg)
            continue
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error fetching from contract {contract}: {str(e)}"
            logger.error("❌ %s", error_msg, exc_info=True)
            errors_encountered.append(error_msg)
            continue
        except json.JSONDecodeError as e:
            error_msg = f"JSON decode error from contract {contract}: {str(e)}"
            logger.error("❌ %s", error_msg, exc_info=True)
            errors_encountered.append(error_msg)
            continue
        except Exception as e:
            error_msg = f"Unexpected error fetching from contract {contract}: {str(e)}"
            logger.error("❌ %s", error_msg, exc_info=True)
            errors_encountered.append(error_msg)
            continue
    
    # Send error email if we encountered errors and collected few wallets
    if errors_encountered and len(wallets) < limit / 2:
        error_details = "\n".join(errors_encountered)
        send_error_email("Raw Wallet Fetch Errors", 
                        f"Encountered {len(errors_encountered)} errors while fetching raw wallets. Only collected {len(wallets)} wallets.", 
                        error_details)
    
    logger.info(f"✔ Collected {len(wallets)} raw wallets")
    return list(wallets)

# ============================================
# Step 2 — Check if EOA (not a contract)
# ============================================
def is_eoa(address):
    """Check if address is an EOA (not a contract)"""
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(address))
        return code == b''
    except ValueError as e:
        logger.warning("Invalid address format for EOA check %s: %s", address, e)
        return False
    except Exception as e:
        logger.warning("Error checking EOA for %s: %s", address, e)
        return False

# ============================================
# Step 3 — Get USD balance using Moralis
# ============================================
def get_usd_value(address, moralis_api_key):
    """Get USD value of wallet using Moralis API"""
    url = f"https://deep-index.moralis.io/api/v2.2/wallets/{address}"
    headers = {"X-API-Key": moralis_api_key}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            error_msg = f"Moralis API authentication failed (401) for address {address}. Check API key."
            logger.error("❌ %s", error_msg)
            send_error_email("Moralis API Authentication Error", error_msg, f"Status code: {resp.status_code}")
            return 0
        elif resp.status_code == 429:
            error_msg = f"Moralis API rate limit exceeded (429) for address {address}"
            logger.warning("⚠️ %s", error_msg)
            # Don't send email for rate limits, just log
            return 0
        elif resp.status_code != 200:
            logger.warning("Moralis API returned status %d for address %s", resp.status_code, address)
            return 0
        
        data = resp.json()
        chains = data.get("chains", {})
        avax_data = chains.get("43114", {})  # Avalanche chainId
        return float(avax_data.get("usd_value", 0))
    except requests.exceptions.Timeout as e:
        logger.warning("Timeout getting USD value for %s: %s", address, e)
        return 0
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error getting USD value for {address}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Moralis API Request Error", error_msg, str(e))
        return 0
    except (ValueError, KeyError) as e:
        logger.warning("Error parsing USD value response for %s: %s", address, e)
        return 0
    except Exception as e:
        error_msg = f"Unexpected error getting USD value for {address}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Moralis API Error", error_msg, str(e))
        return 0

# ============================================
# ERROR EMAIL NOTIFICATION
# ============================================
def send_error_email(subject, error_message, error_details=None):
    """Send error notification via email"""
    try:
        if not EMAIL_RECIPIENT:
            logger.warning("No EMAIL_RECIPIENT configured, skipping error email")
            return
        
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        
        msg = MIMEMultipart()
        msg['Subject'] = f'🚨 Scraper Error: {subject}'
        msg['From'] = EMAIL_RECIPIENT
        msg['To'] = EMAIL_RECIPIENT
        
        details_section = ""
        if error_details:
            details_section = f"\n\nError Details:\n{error_details}"
        
        body = MIMEText(f"""
Wallet Scraper - Error Alert

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{error_message}{details_section}

Please check the scraper logs for more information.

This is an automated email from your NFT Minting Bot.
        """)
        msg.attach(body)
        
        ses_client.send_raw_email(
            Source=EMAIL_RECIPIENT,
            Destinations=[EMAIL_RECIPIENT],
            RawMessage={'Data': msg.as_string()}
        )
        logger.info("✅ Error email sent successfully")
    except Exception as e:
        logger.error("❌ Failed to send error email: %s", e, exc_info=True)

# ============================================
# SEND COMPLETION EMAIL
# ============================================
def send_completion_email(wallets_collected):
    """Send email notification when scraper completes"""
    try:
        if not EMAIL_RECIPIENT:
            logger.warning("No EMAIL_RECIPIENT configured, skipping email")
            return
        
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        
        msg = MIMEMultipart()
        msg['Subject'] = f'✅ Wallet Scraper Completed - {wallets_collected} Wallets Collected'
        msg['From'] = EMAIL_RECIPIENT
        msg['To'] = EMAIL_RECIPIENT
        
        body = MIMEText(f"""
Wallet Scraper - Completion Report

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

✅ Scraper has successfully completed!

Wallets Collected: {wallets_collected}
Target: {DAILY_TARGET}

The scraped wallets have been saved to: {SCRAPED_WALLETS_FILE}

You can now use these wallets in the minting bot by switching to "scraped" mode.

This is an automated email from your NFT Minting Bot.
        """)
        msg.attach(body)
        
        ses_client.send_raw_email(
            Source=EMAIL_RECIPIENT,
            Destinations=[EMAIL_RECIPIENT],
            RawMessage={'Data': msg.as_string()}
        )
        logger.info("✅ Completion email sent successfully")
    except Exception as e:
        error_msg = f"Failed to send completion email: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        # Try to send error email about email failure (but don't fail if this also fails)
        try:
            send_error_email("Email Send Failure", error_msg, str(e))
        except:
            pass

# ============================================
# SCRAPER MAIN FUNCTION
# ============================================
def run_scraper():
    """Main scraper function - single run mode"""
    logger.info("=" * 60)
    logger.info("🚀 Avalanche Wallet Scraper Starting")
    logger.info(f"🎯 Target: {DAILY_TARGET} wallets")
    logger.info("=" * 60)
    
    # Get Moralis API key
    try:
        moralis_api_key = get_moralis_api_key()
        if not moralis_api_key or moralis_api_key == 'YOUR_MORALIS_API_KEY_HERE':
            error_msg = "Moralis API key is not configured or is using placeholder value"
            logger.error("❌ %s", error_msg)
            send_error_email("Configuration Error", error_msg, "Please set MORALIS_API_KEY or update the hardcoded value in wallet_scraper.py")
            update_scraper_status("stopped", 0, error_msg)
            return
    except Exception as e:
        error_msg = f"Failed to get Moralis API key: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("API Key Error", error_msg, str(e))
        update_scraper_status("stopped", 0, error_msg)
        return
    
    # Load existing wallets and master set
    try:
        existing_wallets, master_set = load_scraped_wallets()
        logger.info(f"📂 Loaded {len(existing_wallets)} existing wallets")
        logger.info(f"📂 Master set size: {len(master_set)}")
    except Exception as e:
        error_msg = f"Failed to load existing wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Load Error", error_msg, str(e))
        update_scraper_status("stopped", 0, error_msg)
        return
    
    # Update status
    try:
        update_scraper_status("running", len(existing_wallets), "Scraper started")
    except Exception as e:
        logger.warning("Failed to update initial status: %s", e)
    
    # Fetch raw wallets
    try:
        raw_wallets = fetch_raw_wallets(RAW_WALLET_TARGET)
        logger.info(f"🔍 Filtering {len(raw_wallets)} raw wallets...")
        
        if len(raw_wallets) == 0:
            error_msg = "No raw wallets collected from Snowtrace API"
            logger.error("❌ %s", error_msg)
            send_error_email("Data Collection Error", error_msg, "Check Snowtrace API availability and network connectivity")
            update_scraper_status("stopped", len(existing_wallets), error_msg)
            return
    except Exception as e:
        error_msg = f"Failed to fetch raw wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Fetch Error", error_msg, str(e))
        update_scraper_status("stopped", len(existing_wallets), error_msg)
        return
    
    cleaned_wallets = []
    checked = 0
    
    for wallet in raw_wallets:
        wallet = wallet.lower()
        checked += 1
        
        # Skip if already in master set
        if wallet in master_set:
            continue
        
        # Skip invalid addresses
        if not w3.is_address(wallet):
            continue
        
        # Check EOA
        if not is_eoa(wallet):
            continue
        
        # USD balance check
        try:
            usd = get_usd_value(wallet, moralis_api_key)
            if usd < USD_THRESHOLD:
                continue
        except Exception as e:
            logger.warning("Error getting USD value for %s, skipping: %s", wallet, e)
            continue
        
        # Valid wallet - add to list
        wallet_entry = {
            "address": wallet,
            "usd_value": usd,
            "used": False,
            "scraped_date": datetime.now().isoformat()
        }
        cleaned_wallets.append(wallet_entry)
        master_set.add(wallet)
        
        logger.info(f"✔ {wallet} | ${usd:.2f} added ({len(cleaned_wallets)}/{DAILY_TARGET})")
        
        # Update status periodically
        if len(cleaned_wallets) % 100 == 0:
            update_scraper_status("running", len(existing_wallets) + len(cleaned_wallets), 
                                f"Progress: {len(cleaned_wallets)}/{DAILY_TARGET}")
        
        # Stop when target reached
        if len(cleaned_wallets) >= DAILY_TARGET:
            logger.info(f"✅ Target reached: {len(cleaned_wallets)} wallets collected")
            break
    
    # Combine with existing wallets
    try:
        all_wallets = existing_wallets + cleaned_wallets
        
        # Save wallets
        save_scraped_wallets(all_wallets, master_set)
        
        total_collected = len(cleaned_wallets)
        logger.info(f"📊 Total new wallets collected: {total_collected}")
        logger.info(f"📊 Total wallets in database: {len(all_wallets)}")
        
        # Update final status
        try:
            update_scraper_status("completed", len(all_wallets), 
                                 f"Successfully collected {total_collected} new wallets")
        except Exception as e:
            logger.error("Failed to update final status: %s", e, exc_info=True)
        
        # Send completion email
        send_completion_email(total_collected)
        
        logger.info("=" * 60)
        logger.info("🎉 Scraper completed successfully!")
        logger.info("=" * 60)
    except Exception as e:
        error_msg = f"Failed to save results or send completion notification: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Completion Error", error_msg, str(e))
        try:
            update_scraper_status("stopped", len(existing_wallets) + len(cleaned_wallets), error_msg)
        except:
            pass

# ============================================
# MAIN ENTRY POINT
# ============================================
if __name__ == "__main__":
    # Save PID
    with open(SCRAPER_PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    try:
        run_scraper()
    except KeyboardInterrupt:
        logger.info("👋 Scraper stopped by user")
        try:
            update_scraper_status("stopped", 0, "Stopped by user")
        except:
            pass
    except Exception as e:
        error_msg = f"Critical error in scraper: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Critical Scraper Error", error_msg, str(e))
        try:
            update_scraper_status("stopped", 0, f"Error: {str(e)}")
        except:
            pass
    finally:
        # Remove PID file
        if os.path.exists(SCRAPER_PID_FILE):
            os.remove(SCRAPER_PID_FILE)

