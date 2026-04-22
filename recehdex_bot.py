import asyncio
import aiohttp
from web3 import Web3
from telegram import Bot
from telegram.constants import ParseMode
import logging
from datetime import datetime
from typing import Dict, Tuple
import os
import json

# Konfigurasi dari environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

# Contract Addresses
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"
WRIC_ADDRESS = "0xEa126036c94Ab6A384A25A70e29E2fE2D4a91e68"
FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"

# Configuration
RPC_URL = "https://seed-richechain.com:8586/"
CHAIN_ID = 132026
EXPLORER_URL = "https://richescan.com"
DEX_URL = "https://dex.cryptoreceh.com/riche"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner.png"

# Web3 connection using HTTP (lebih stabil untuk GitHub Actions)
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# File cache untuk menyimpan state antar run
CACHE_FILE = "pairs_cache.json"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ABIs
PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

TOKEN_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "allPairsLength",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "", "type": "uint256"}],
        "name": "allPairs",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]

def load_cache():
    """Load cached pair data from file"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    """Save pair data to cache file"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def get_token_info(token_address: str) -> Tuple[str, int]:
    """Get token symbol and decimals"""
    try:
        token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        symbol = token_contract.functions.symbol().call()
        decimals = token_contract.functions.decimals().call()
        return symbol, decimals
    except Exception as e:
        logger.error(f"Error getting token info for {token_address}: {e}")
        return "Unknown", 18

def get_pair_info(pair_address: str) -> Dict:
    """Get pair information"""
    try:
        pair_contract = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
        
        token0 = pair_contract.functions.token0().call()
        token1 = pair_contract.functions.token1().call()
        reserves = pair_contract.functions.getReserves().call()
        reserve0 = reserves[0]
        reserve1 = reserves[1]
        total_supply = pair_contract.functions.totalSupply().call()
        
        token0_symbol, token0_decimals = get_token_info(token0)
        token1_symbol, token1_decimals = get_token_info(token1)
        
        # Determine which token is USD
        usd_reserve = 0
        other_reserve = 0
        other_symbol = ""
        other_address = ""
        
        if token0.lower() == USD_ADDRESS.lower():
            usd_reserve = reserve0 / (10 ** token0_decimals)
            other_reserve = reserve1 / (10 ** token1_decimals)
            other_symbol = token1_symbol
            other_address = token1
        elif token1.lower() == USD_ADDRESS.lower():
            usd_reserve = reserve1 / (10 ** token1_decimals)
            other_reserve = reserve0 / (10 ** token0_decimals)
            other_symbol = token0_symbol
            other_address = token0
        
        if usd_reserve == 0:
            return None
        
        price = other_reserve / usd_reserve
        total_liquidity_usd = usd_reserve * 2
        
        return {
            "pair_address": pair_address,
            "pair_name": f"{other_symbol}/USD",
            "other_symbol": other_symbol,
            "other_address": other_address,
            "price": price,
            "usd_reserve": usd_reserve,
            "other_reserve": other_reserve,
            "total_liquidity_usd": total_liquidity_usd,
            "total_supply": total_supply / (10 ** 18),
            "token0_symbol": token0_symbol,
            "token1_symbol": token1_symbol,
            "last_update": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting pair info for {pair_address}: {e}")
        return None

def get_all_pairs() -> Dict:
    """Get all pairs from factory"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        pairs_count = factory.functions.allPairsLength().call()
        
        logger.info(f"Total pairs in factory: {pairs_count}")
        
        pairs = {}
        for i in range(min(pairs_count, 200)):  # Max 200 pairs
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair_info = get_pair_info(pair_address)
                
                if pair_info and pair_info['price'] > 0:
                    pairs[pair_address] = pair_info
                    logger.info(f"Found active pair: {pair_info['pair_name']} - Price: ${pair_info['price']:.10f}")
            except Exception as e:
                continue
        
        logger.info(f"Found {len(pairs)} active pairs with USD")
        return pairs
    except Exception as e:
        logger.error(f"Error getting pairs: {e}")
        return {}

def format_telegram_message(pair_info: Dict, is_new: bool = False) -> str:
    """Format professional Telegram message"""
    
    status = "🆕 NEW PAIR LISTED" if is_new else "🔄 PAIR UPDATE"
    
    # Format numbers
    price_str = f"${pair_info['price']:.10f}".rstrip('0').rstrip('.')
    liquidity_str = f"${pair_info['total_liquidity_usd']:,.2f}"
    lp_supply_str = f"{pair_info['total_supply']:,.0f}"
    usd_reserve_str = f"${pair_info['usd_reserve']:,.2f}"
    other_reserve_str = f"{pair_info['other_reserve']:,.2f}"
    
    # Trading link
    trade_url = f"{DEX_URL}?inputCurrency={USD_ADDRESS}&outputCurrency={pair_info['other_address']}"
    
    message = f"""
<a href="{BANNER_URL}">&#8205;</a>

<b>📢 {status}</b>

<b>🏦 RECEHDEX DEX</b>

<b>🪙 Pair:</b> <code>{pair_info['pair_name']}</code>

<b>💰 Current Price:</b> <code>{price_str}</code>

<b>💧 Total Liquidity:</b> <code>{liquidity_str}</code>

<b>📊 LP Token Supply:</b> <code>{lp_supply_str}</code>

<b>📦 Pool Reserves:</b>
<code>  USD: {usd_reserve_str}</code>
<code>  {pair_info['other_symbol']}: {other_reserve_str}</code>

<b>🔗 Quick Links:</b>
• <a href="{trade_url}">Trade on RecehDEX</a>
• <a href="{EXPLORER_URL}/address/{pair_info['pair_address']}">View on Explorer</a>

<code>━━━━━━━━━━━━━━━━━━━━</code>
<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
<i>⚡ Data from Riche Chain</i>
"""
    return message

async def send_telegram_update(bot: Bot, message: str):
    """Send update to Telegram"""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False
        )
        logger.info("Telegram message sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")
        return False

async def send_startup_message(bot: Bot):
    """Send startup notification"""
    message = f"""
<a href="{BANNER_URL}">&#8205;</a>

<b>✅ RECEHDEX BOT ONLINE</b>

<code>━━━━━━━━━━━━━━━━━━━━</code>

<b>🔗 Network:</b> <code>Riche Chain (ID: {CHAIN_ID})</code>
<b>📡 Status:</b> <code>Monitoring Active</code>
<b>🕐 Started:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</code>

<b>📊 Monitoring pairs with USD peg</b>
<b>🔄 Update interval:</b> <code>5 minutes</code>

<code>━━━━━━━━━━━━━━━━━━━━</code>

<i>⚡ Bot will send notifications for new pairs and price changes</i>
"""
    await send_telegram_update(bot, message)

async def main():
    """Main function - runs once per GitHub Action trigger"""
    logger.info("=" * 50)
    logger.info("RecehDEX Telegram Bot Started")
    logger.info("=" * 50)
    
    # Check connection
    if not w3.is_connected():
        logger.error("Failed to connect to Riche Chain")
        return
    
    logger.info(f"Connected to Riche Chain")
    logger.info(f"Current block: {w3.eth.block_number}")
    
    # Initialize bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Load previous cache
    cache = load_cache()
    logger.info(f"Loaded {len(cache)} pairs from cache")
    
    # Get current pairs
    current_pairs = get_all_pairs()
    
    if not current_pairs:
        logger.warning("No pairs found")
        return
    
    # Check for new pairs and price changes
    updates_sent = 0
    price_change_threshold = 5  # 5% price change
    
    for pair_address, pair_info in current_pairs.items():
        should_send = False
        is_new = False
        
        if pair_address not in cache:
            # New pair detected
            logger.info(f"New pair detected: {pair_info['pair_name']}")
            should_send = True
            is_new = True
        else:
            # Check price change
            cached_price = cache[pair_address].get('price', 0)
            current_price = pair_info['price']
            
            if cached_price > 0:
                price_change = abs((current_price - cached_price) / cached_price) * 100
                if price_change >= price_change_threshold:
                    logger.info(f"Price change for {pair_info['pair_name']}: {price_change:.2f}%")
                    should_send = True
        
        if should_send:
            message = format_telegram_message(pair_info, is_new)
            if await send_telegram_update(bot, message):
                updates_sent += 1
            await asyncio.sleep(2)  # Delay between messages
    
    # Send summary if no updates
    if updates_sent == 0:
        logger.info("No new pairs or significant price changes detected")
        # Optional: Send heartbeat every hour
        last_run = cache.get('_last_run', '')
        if not last_run or (datetime.now() - datetime.fromisoformat(last_run)).seconds > 3600:
            heartbeat_msg = f"""
<a href="{BANNER_URL}">&#8205;</a>

<b>💓 RECEHDEX BOT HEARTBEAT</b>

<code>━━━━━━━━━━━━━━━━━━━━</code>

<b>📊 Monitoring Status:</b> <code>Active</code>
<b>🪙 Active Pairs:</b> <code>{len(current_pairs)}</code>
<b>🕐 Last Check:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</code>

<b>💰 Top Pairs by Liquidity:</b>
"""
            # Add top 3 pairs by liquidity
            sorted_pairs = sorted(current_pairs.values(), key=lambda x: x['total_liquidity_usd'], reverse=True)[:3]
            for pair in sorted_pairs:
                heartbeat_msg += f"\n<code>  • {pair['pair_name']}: ${pair['total_liquidity_usd']:,.0f}</code>"
            
            heartbeat_msg += "\n\n<code>━━━━━━━━━━━━━━━━━━━━</code>\n<i>⚡ Bot running normally</i>"
            
            await send_telegram_update(bot, heartbeat_msg)
    
    # Update cache
    cache.update(current_pairs)
    cache['_last_run'] = datetime.now().isoformat()
    save_cache(cache)
    
    logger.info(f"Bot completed - Sent {updates_sent} updates")
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
