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
    file_handler.setLevel(logging.INFO)
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
    if os.path.exists(SCRAPED_WALLETS_FILE):
        try:
            with open(SCRAPED_WALLETS_FILE, "r") as f:
                data = json.load(f)
                wallets = data.get("wallets", [])
                master_set = set(data.get("master_set", []))
                return wallets, master_set
        except Exception as e:
            logger.error("Error loading scraped wallets: %s", e)
            return [], set()
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
    except Exception as e:
        logger.error("❌ Error saving scraped wallets: %s", e)

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
        logger.error("❌ Error updating status: %s", e)

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
    
    for contract in active_contracts:
        url = SNOWTRACE_TX_URL.format(contract)
        try:
            resp = requests.get(url, timeout=30)
            data = resp.json()
            if "result" not in data:
                continue
            
            for tx in data["result"]:
                if tx.get("from"):
                    wallets.add(tx["from"].lower())
                if tx.get("to"):
                    wallets.add(tx["to"].lower())
                
                if len(wallets) >= limit:
                    logger.info(f"✔ Collected {len(wallets)} raw wallets")
                    return list(wallets)
        except Exception as e:
            logger.warning("Error fetching from %s: %s", contract, e)
            continue
    
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
        if resp.status_code != 200:
            return 0
        data = resp.json()
        chains = data.get("chains", {})
        avax_data = chains.get("43114", {})  # Avalanche chainId
        return float(avax_data.get("usd_value", 0))
    except Exception as e:
        logger.warning("Error getting USD value for %s: %s", address, e)
        return 0

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
        logger.error("❌ Failed to send completion email: %s", e)

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
    except Exception as e:
        logger.error("❌ Failed to get Moralis API key: %s", e)
        update_scraper_status("stopped", 0, f"Failed to get API key: {str(e)}")
        return
    
    # Load existing wallets and master set
    existing_wallets, master_set = load_scraped_wallets()
    logger.info(f"📂 Loaded {len(existing_wallets)} existing wallets")
    logger.info(f"📂 Master set size: {len(master_set)}")
    
    # Update status
    update_scraper_status("running", len(existing_wallets), "Scraper started")
    
    # Fetch raw wallets
    raw_wallets = fetch_raw_wallets(RAW_WALLET_TARGET)
    logger.info(f"🔍 Filtering {len(raw_wallets)} raw wallets...")
    
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
        usd = get_usd_value(wallet, moralis_api_key)
        if usd < USD_THRESHOLD:
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
    all_wallets = existing_wallets + cleaned_wallets
    
    # Save wallets
    save_scraped_wallets(all_wallets, master_set)
    
    total_collected = len(cleaned_wallets)
    logger.info(f"📊 Total new wallets collected: {total_collected}")
    logger.info(f"📊 Total wallets in database: {len(all_wallets)}")
    
    # Update final status
    update_scraper_status("completed", len(all_wallets), 
                         f"Successfully collected {total_collected} new wallets")
    
    # Send completion email
    send_completion_email(total_collected)
    
    logger.info("=" * 60)
    logger.info("🎉 Scraper completed successfully!")
    logger.info("=" * 60)

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
        update_scraper_status("stopped", 0, "Stopped by user")
    except Exception as e:
        logger.error("❌ Critical error: %s", e, exc_info=True)
        update_scraper_status("stopped", 0, f"Error: {str(e)}")
    finally:
        # Remove PID file
        if os.path.exists(SCRAPER_PID_FILE):
            os.remove(SCRAPER_PID_FILE)

