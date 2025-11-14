# wallet_scraper.py - Avalanche Active Wallet Scraper (Covalent + Snowtrace + Free RPC)
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

# ---------------------------
# API KEYS
# ---------------------------
SNOWTRACE_API_KEY = "rs_e6e107e844449d143f5cd825"
COVALENT_API_KEY = "cqt_rQGRckM6MCcQHYTYPyPfCjFtxKmh"

EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

# ---------------------------
# Snowtrace API base URL
# ---------------------------
SNOWTRACE_BASE_URL = "https://api.snowtrace.io/api"

# ---------------------------
# Covalent balances_v2 endpoint
# ---------------------------
COVALENT_BALANCES_URL = "https://api.covalenthq.com/v1/43114/address/{address}/balances_v2/?key=" + COVALENT_API_KEY

# ============================================
# RPC SETUP
# ============================================
w3 = Web3(Web3.HTTPProvider(AVAX_RPC))


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
    """Fetch raw wallet addresses from Snowtrace using tokentx and txlistinternal endpoints"""
    wallets = set()
    logger.info("📡 Collecting active wallets (raw) from Snowtrace API...")
    logger.info("🔍 Using tokentx (ERC20 swaps) + txlistinternal (AVAX swaps) endpoints")
    
    # Using known active contracts (DEX Routers)
    active_contracts = [
        "0xE54Ca86531e17Ef3616d22Ca28b0D458b6C89106",  # Pangolin Router
        "0x9e90F9B1C0904b8C474b05c226c1E18b1dA53fC7",  # Trader Joe Router
    ]
    
    errors_encountered = []
    endpoints_processed = 0
    
    for contract in active_contracts:
        logger.info(f"📡 Processing contract: {contract}")
        
        # 1. ERC20 token transfers (captures swaps via tokens)
        tokentx_url = (
            f"{SNOWTRACE_BASE_URL}"
            f"?module=account&action=tokentx"
            f"&contractaddress={contract}"
            f"&page=1&offset=10000&sort=desc&apikey={SNOWTRACE_API_KEY}"
        )
        
        # 2. Internal TX (captures AVAX swaps via internal calls)
        internaltx_url = (
            f"{SNOWTRACE_BASE_URL}"
            f"?module=account&action=txlistinternal"
            f"&address={contract}"
            f"&page=1&offset=10000&sort=desc&apikey={SNOWTRACE_API_KEY}"
        )
        
        # Process both endpoints for each contract
        for endpoint_name, url in [("tokentx", tokentx_url), ("txlistinternal", internaltx_url)]:
            try:
                logger.debug(f"Fetching {endpoint_name} for {contract}...")
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                
                if "result" not in data:
                    logger.warning(f"No 'result' field in {endpoint_name} response from {contract}")
                    continue
                
                result_count = len(data["result"]) if isinstance(data["result"], list) else 0
                logger.info(f"✅ {endpoint_name} for {contract}: {result_count} transactions found")
                
                for tx in data["result"]:
                    if tx.get("from"):
                        wallets.add(tx["from"].lower())
                    if tx.get("to"):
                        wallets.add(tx["to"].lower())
                    
                    if len(wallets) >= limit:
                        logger.info(f"✔ Collected {len(wallets)} raw wallets (target reached)")
                        return list(wallets)
                
                endpoints_processed += 1
                
            except requests.exceptions.Timeout as e:
                error_msg = f"Timeout fetching {endpoint_name} from contract {contract}: {str(e)}"
                logger.warning("⚠️ %s", error_msg)
                errors_encountered.append(error_msg)
                continue
            except requests.exceptions.RequestException as e:
                error_msg = f"Request error fetching {endpoint_name} from contract {contract}: {str(e)}"
                logger.error("❌ %s", error_msg, exc_info=True)
                errors_encountered.append(error_msg)
                continue
            except json.JSONDecodeError as e:
                error_msg = f"JSON decode error from {endpoint_name} for contract {contract}: {str(e)}"
                logger.error("❌ %s", error_msg, exc_info=True)
                errors_encountered.append(error_msg)
                continue
            except Exception as e:
                error_msg = f"Unexpected error fetching {endpoint_name} from contract {contract}: {str(e)}"
                logger.error("❌ %s", error_msg, exc_info=True)
                errors_encountered.append(error_msg)
                continue
    
    # Log summary
    logger.info("=" * 60)
    logger.info(f"📊 Collection Summary:")
    logger.info(f"   ✅ Endpoints processed: {endpoints_processed}/4")
    logger.info(f"   ✅ Unique wallets collected: {len(wallets)}")
    logger.info(f"   ⚠️  Errors encountered: {len(errors_encountered)}")
    logger.info("=" * 60)
    
    # Send error email if we encountered errors and collected few wallets
    if errors_encountered and len(wallets) < limit / 2:
        error_details = "\n".join(errors_encountered[:10])  # Limit to first 10 errors
        send_error_email("Raw Wallet Fetch Errors", 
                        f"Encountered {len(errors_encountered)} errors while fetching raw wallets. Only collected {len(wallets)} wallets (target: {limit}).", 
                        error_details)
    
    if len(wallets) < 100:
        logger.warning(f"⚠️ Low wallet count: {len(wallets)} wallets collected. This may affect filtering results.")
    
    logger.info(f"✔ Total raw wallets collected: {len(wallets)}")
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
# Step 3 — Get USD balance using Covalent
# ============================================
def get_usd_value(address):
    """Get USD token value using Covalent balances_v2 endpoint"""
    url = COVALENT_BALANCES_URL.format(address=address)
    try:
        resp = requests.get(url, timeout=25)
        if resp.status_code == 401:
            error_msg = f"Covalent API authentication failed (401) for address {address}. Check API key."
            logger.error("❌ %s", error_msg)
            send_error_email("Covalent API Authentication Error", error_msg, f"Status code: {resp.status_code}")
            return 0
        elif resp.status_code == 429:
            error_msg = f"Covalent API rate limit exceeded (429) for address {address}"
            logger.warning("⚠️ %s", error_msg)
            # Don't send email for rate limits, just log
            return 0
        elif resp.status_code != 200:
            logger.warning("Covalent returned status %d for %s", resp.status_code, address)
            return 0
        
        data = resp.json()
        # Covalent returns data.items[], each item has 'quote' field (USD value)
        total_usd = 0.0
        if "data" in data and isinstance(data["data"], dict):
            items = data["data"].get("items", [])
            for item in items:
                try:
                    q = item.get("quote", 0)
                    if q:
                        total_usd += float(q)
                except (ValueError, TypeError) as e:
                    logger.debug("Error parsing quote for item in %s: %s", address, e)
                    continue
        
        return total_usd
    except requests.exceptions.Timeout as e:
        logger.warning("Timeout getting Covalent USD for %s: %s", address, e)
        return 0
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error getting Covalent USD for {address}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Covalent API Request Error", error_msg, str(e))
        return 0
    except (ValueError, KeyError) as e:
        logger.warning("Error parsing Covalent USD value response for %s: %s", address, e)
        return 0
    except Exception as e:
        error_msg = f"Unexpected error getting Covalent USD for {address}: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Covalent API Error", error_msg, str(e))
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
    logger.info(f"📅 Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🎯 Target: {DAILY_TARGET} wallets")
    logger.info(f"📊 Raw Wallet Target: {RAW_WALLET_TARGET}")
    logger.info(f"💰 USD Threshold: ${USD_THRESHOLD}")
    logger.info(f"📁 Scraped Wallets File: {SCRAPED_WALLETS_FILE}")
    logger.info("=" * 60)
    
    # Check Covalent API key
    logger.info("🔑 Step 1/6: Checking Covalent API key...")
    if not COVALENT_API_KEY:
        error_msg = "Covalent API key is not configured"
        logger.error("❌ %s", error_msg)
        send_error_email("Configuration Error", error_msg, "Please set COVALENT_API_KEY in the script or environment variable")
        update_scraper_status("stopped", 0, error_msg)
        return
    logger.info("✅ Covalent API key available (using GoldRush product)")
    
    # Load existing wallets and master set
    logger.info("📂 Step 2/6: Loading existing scraped wallets...")
    try:
        existing_wallets, master_set = load_scraped_wallets()
        logger.info(f"✅ Loaded {len(existing_wallets)} existing wallets from {SCRAPED_WALLETS_FILE}")
        logger.info(f"✅ Master deduplication set size: {len(master_set)} addresses")
        if len(existing_wallets) > 0:
            used_count = sum(1 for w in existing_wallets if w.get('used', False))
            available_count = len(existing_wallets) - used_count
            logger.info(f"📊 Existing wallets: {available_count} available, {used_count} used")
    except Exception as e:
        error_msg = f"Failed to load existing wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Load Error", error_msg, str(e))
        update_scraper_status("stopped", 0, error_msg)
        return
    
    # Update status
    logger.info("📝 Step 3/6: Updating scraper status...")
    try:
        update_scraper_status("running", len(existing_wallets), "Scraper started")
        logger.info("✅ Status file updated")
    except Exception as e:
        logger.warning("⚠️ Failed to update initial status: %s", e)
    
    # Fetch raw wallets
    logger.info("📡 Step 4/6: Fetching raw wallets from Snowtrace API...")
    logger.info(f"🎯 Target: {RAW_WALLET_TARGET} raw wallet addresses")
    try:
        raw_wallets = fetch_raw_wallets(RAW_WALLET_TARGET)
        logger.info(f"✅ Collected {len(raw_wallets)} raw wallet addresses from Snowtrace")
        
        if len(raw_wallets) == 0:
            error_msg = "No raw wallets collected from Snowtrace API"
            logger.error("❌ %s", error_msg)
            send_error_email("Data Collection Error", error_msg, "Check Snowtrace API availability and network connectivity")
            update_scraper_status("stopped", len(existing_wallets), error_msg)
            return
        
        if len(raw_wallets) < RAW_WALLET_TARGET / 2:
            logger.warning("⚠️ Collected only %d raw wallets (target: %d) - may affect final count", 
                          len(raw_wallets), RAW_WALLET_TARGET)
    except Exception as e:
        error_msg = f"Failed to fetch raw wallets: {str(e)}"
        logger.error("❌ %s", error_msg, exc_info=True)
        send_error_email("Fetch Error", error_msg, str(e))
        update_scraper_status("stopped", len(existing_wallets), error_msg)
        return
    
    # Filter and enrich wallets
    logger.info("🔍 Step 5/6: Filtering and enriching wallets...")
    logger.info(f"📋 Processing {len(raw_wallets)} raw wallets")
    logger.info(f"🎯 Filtering criteria:")
    logger.info(f"   - EOA only (no contracts)")
    logger.info(f"   - USD balance >= ${USD_THRESHOLD}")
    logger.info(f"   - Not in existing master set")
    
    cleaned_wallets = []
    checked = 0
    skipped_duplicate = 0
    skipped_invalid = 0
    skipped_contract = 0
    skipped_low_balance = 0
    
    for wallet in raw_wallets:
        wallet = wallet.lower()
        checked += 1
        
        # Log progress every 1000 wallets
        if checked % 1000 == 0:
            logger.info(f"📊 Progress: Checked {checked}/{len(raw_wallets)} wallets | "
                       f"Valid: {len(cleaned_wallets)} | "
                       f"Skipped: {skipped_duplicate + skipped_invalid + skipped_contract + skipped_low_balance}")
        
        # Skip if already in master set
        if wallet in master_set:
            skipped_duplicate += 1
            continue
        
        # Skip invalid addresses
        if not w3.is_address(wallet):
            skipped_invalid += 1
            continue
        
        # Check EOA
        if not is_eoa(wallet):
            skipped_contract += 1
            continue
        
        # USD balance check (Covalent)
        try:
            usd = get_usd_value(wallet)
            if usd < USD_THRESHOLD:
                skipped_low_balance += 1
                continue
        except Exception as e:
            logger.warning("⚠️ Error getting USD value for %s, skipping: %s", wallet, e)
            skipped_low_balance += 1
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
        
        logger.info(f"✔ [{len(cleaned_wallets)}/{DAILY_TARGET}] {wallet} | ${usd:.2f} USD")
        
        # Update status periodically
        if len(cleaned_wallets) % 100 == 0:
            total_wallets = len(existing_wallets) + len(cleaned_wallets)
            progress_pct = (len(cleaned_wallets) / DAILY_TARGET) * 100
            update_scraper_status("running", total_wallets, 
                                f"Progress: {len(cleaned_wallets)}/{DAILY_TARGET} ({progress_pct:.1f}%)")
            logger.info(f"📈 Status updated: {len(cleaned_wallets)}/{DAILY_TARGET} ({progress_pct:.1f}%)")
        
        # Stop when target reached
        if len(cleaned_wallets) >= DAILY_TARGET:
            logger.info(f"✅ Target reached: {len(cleaned_wallets)} wallets collected")
            break
    
    # Log filtering statistics
    logger.info("=" * 60)
    logger.info("📊 Filtering Statistics:")
    logger.info(f"   ✅ Valid wallets collected: {len(cleaned_wallets)}")
    logger.info(f"   ⏭️  Skipped (duplicate): {skipped_duplicate}")
    logger.info(f"   ⏭️  Skipped (invalid address): {skipped_invalid}")
    logger.info(f"   ⏭️  Skipped (contract, not EOA): {skipped_contract}")
    logger.info(f"   ⏭️  Skipped (low balance < ${USD_THRESHOLD}): {skipped_low_balance}")
    logger.info(f"   📋 Total checked: {checked}")
    logger.info("=" * 60)
    
    # Combine with existing wallets and save
    logger.info("💾 Step 6/6: Saving scraped wallets...")
    try:
        all_wallets = existing_wallets + cleaned_wallets
        
        # Save wallets
        logger.info(f"💾 Saving {len(all_wallets)} total wallets to {SCRAPED_WALLETS_FILE}...")
        save_scraped_wallets(all_wallets, master_set)
        logger.info(f"✅ Wallets saved successfully")
        
        total_collected = len(cleaned_wallets)
        logger.info("=" * 60)
        logger.info("📊 Final Statistics:")
        logger.info(f"   🆕 New wallets collected this run: {total_collected}")
        logger.info(f"   📁 Total wallets in database: {len(all_wallets)}")
        logger.info(f"   🎯 Target was: {DAILY_TARGET}")
        if total_collected < DAILY_TARGET:
            logger.warning(f"   ⚠️  Collected {total_collected} wallets (target: {DAILY_TARGET}) - {DAILY_TARGET - total_collected} short")
        logger.info("=" * 60)
        
        # Update final status
        try:
            status_msg = f"Successfully collected {total_collected} new wallets"
            if total_collected < DAILY_TARGET:
                status_msg += f" ({DAILY_TARGET - total_collected} short of target)"
            update_scraper_status("completed", len(all_wallets), status_msg)
            logger.info("✅ Final status updated")
        except Exception as e:
            logger.error("❌ Failed to update final status: %s", e, exc_info=True)
        
        # Send completion email
        logger.info("📧 Sending completion email...")
        send_completion_email(total_collected)
        
        logger.info("=" * 60)
        logger.info("🎉 Scraper completed successfully!")
        logger.info(f"⏱️  End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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

