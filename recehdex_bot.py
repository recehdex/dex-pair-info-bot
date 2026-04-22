import asyncio
from web3 import Web3
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import logging
from datetime import datetime
import os
import requests

# Konfigurasi
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

# Address
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"
FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"

RPC_URL = "https://seed-richechain.com"
EXPLORER_URL = "https://richescan.com"
DEX_URL = "https://dex.cryptoreceh.com"
PAIR_INFO_URL = "https://dex.cryptoreceh.com/info"
CREATE_TOKEN_URL = "https://app.cryptoreceh.com"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner.png"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ABIs
PAIR_ABI = [
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "_reserve0", "type": "uint112"}, {"name": "_reserve1", "type": "uint112"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

TOKEN_ABI = [
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
]

FACTORY_ABI = [
    {"constant": True, "inputs": [], "name": "allPairsLength", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "uint256"}], "name": "allPairs", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

def get_token_info(token_address):
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except:
        return "Unknown", 18

def get_top_pairs():
    """Ambil top 3 pair berdasarkan likuiditas USD"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        
        logger.info(f"Scanning {total_pairs} pairs...")
        
        pairs_data = []
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair_contract = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair_contract.functions.token0().call()
                token1 = pair_contract.functions.token1().call()
                reserves = pair_contract.functions.getReserves().call()
                
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                reserve0 = reserves[0] / (10 ** token0_dec)
                reserve1 = reserves[1] / (10 ** token1_dec)
                
                # Cari USD reserve
                usd_reserve = 0
                other_symbol = ""
                other_address = ""
                price = 0
                
                if token0.lower() == USD_ADDRESS.lower():
                    usd_reserve = reserve0
                    other_symbol = token1_symbol
                    other_address = token1
                    price = reserve1 / reserve0 if reserve0 > 0 else 0
                elif token1.lower() == USD_ADDRESS.lower():
                    usd_reserve = reserve1
                    other_symbol = token0_symbol
                    other_address = token0
                    price = reserve0 / reserve1 if reserve1 > 0 else 0
                
                if usd_reserve > 0 and price > 0:
                    liquidity_usd = usd_reserve * 2
                    pairs_data.append({
                        "symbol": other_symbol,
                        "address": other_address,
                        "price": price,
                        "liquidity": liquidity_usd,
                        "pair_address": pair_address
                    })
            except:
                continue
        
        # Sort by liquidity (descending) and take top 3
        pairs_data.sort(key=lambda x: x['liquidity'], reverse=True)
        return pairs_data[:3]
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return []

async def get_banner():
    """Download banner"""
    try:
        response = requests.get(BANNER_URL, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

async def main():
    logger.info("Starting RecehDEX Bot...")
    
    if not w3.is_connected():
        logger.error("Cannot connect to Riche Chain")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Get top 3 pairs
    top_pairs = get_top_pairs()
    
    if not top_pairs:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="⚠️ No active pairs found",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Build message
    message = "<b>🏆 RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "<code>━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Format price
        if pair['price'] < 0.000001:
            price_str = f"${pair['price']:.12f}"
        elif pair['price'] < 0.0001:
            price_str = f"${pair['price']:.10f}"
        elif pair['price'] < 0.01:
            price_str = f"${pair['price']:.8f}"
        elif pair['price'] < 1:
            price_str = f"${pair['price']:.6f}"
        else:
            price_str = f"${pair['price']:.4f}"
        
        message += f"<b>{idx}. {pair['symbol']}/USD</b>\n"
        message += f"   💰 Price: <code>{price_str}</code>\n"
        message += f"   💧 Liquidity: <code>${pair['liquidity']:,.2f}</code>\n"
        message += f"   🔗 <a href='{DEX_URL}?inputCurrency={USD_ADDRESS}&outputCurrency={pair['address']}'>Trade Now</a>\n\n"
    
    message += "<code>━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
    message += f"<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
    
    # Tombol inline
    keyboard = [
        [
            InlineKeyboardButton("📊 RecehDEX", url=DEX_URL),
            InlineKeyboardButton("ℹ️ PairInfo", url=PAIR_INFO_URL),
        ],
        [
            InlineKeyboardButton("✨ Create Token", url=CREATE_TOKEN_URL),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Download banner
    banner = await get_banner()
    
    if banner:
        # Kirim banner + caption + tombol
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=banner,
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        logger.info("Sent banner + top 3 pairs")
    else:
        # Kirim message aja
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        logger.info("Sent top 3 pairs (no banner)")

if __name__ == "__main__":
    asyncio.run(main())
