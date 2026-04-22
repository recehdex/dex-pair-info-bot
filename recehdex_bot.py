import asyncio
from web3 import Web3
from telegram import Bot
from telegram.constants import ParseMode
import logging
from datetime import datetime
import os

# Konfigurasi
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

# Address
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"
WRIC_ADDRESS = "0xEa126036c94Ab6A384A25A70e29E2fE2D4a91e68"
FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"

RPC_URL = "https://seed-richechain.com/"
EXPLORER_URL = "https://richescan.com"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ABIs
PAIR_ABI = [
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "_reserve0", "type": "uint112"}, {"name": "_reserve1", "type": "uint112"}, {"name": "_blockTimestampLast", "type": "uint32"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
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

def get_all_pairs():
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        
        logger.info(f"Total pairs: {total_pairs}")
        
        pairs = []
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair_contract = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair_contract.functions.token0().call()
                token1 = pair_contract.functions.token1().call()
                reserves = pair_contract.functions.getReserves().call()
                total_supply = pair_contract.functions.totalSupply().call()
                
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                reserve0 = reserves[0] / (10 ** token0_dec)
                reserve1 = reserves[1] / (10 ** token1_dec)
                lp_supply = total_supply / (10 ** 18)
                
                # Hitung harga dalam USD
                price_usd = 0
                if token0.lower() == USD_ADDRESS.lower():
                    price_usd = reserve1 / reserve0 if reserve0 > 0 else 0
                elif token1.lower() == USD_ADDRESS.lower():
                    price_usd = reserve0 / reserve1 if reserve1 > 0 else 0
                
                # Likuiditas dalam USD
                liquidity_usd = 0
                if token0.lower() == USD_ADDRESS.lower():
                    liquidity_usd = reserve0 * 2
                elif token1.lower() == USD_ADDRESS.lower():
                    liquidity_usd = reserve1 * 2
                
                pairs.append({
                    "address": pair_address,
                    "pair_name": f"{token0_symbol}/{token1_symbol}",
                    "price_usd": price_usd,
                    "liquidity_usd": liquidity_usd,
                    "lp_supply": lp_supply
                })
            except Exception as e:
                continue
        
        # Urutkan berdasarkan likuiditas
        pairs.sort(key=lambda x: x['liquidity_usd'], reverse=True)
        return pairs
    except Exception as e:
        logger.error(f"Error: {e}")
        return []

def format_caption(pairs, start_idx, end_idx):
    """Format caption untuk 5 pair"""
    caption = "<b>🔥 RECEHDEX PAIR LIST</b>\n"
    caption += "<code>═══════════════════════════════</code>\n\n"
    
    for pair in pairs[start_idx:end_idx]:
        # Format harga
        if pair["price_usd"] > 0:
            if pair["price_usd"] < 0.000001:
                price_str = f"${pair['price_usd']:.10f}"
            elif pair["price_usd"] < 0.001:
                price_str = f"${pair['price_usd']:.8f}"
            else:
                price_str = f"${pair['price_usd']:.4f}"
        else:
            price_str = "N/A"
        
        # Format likuiditas
        if pair["liquidity_usd"] > 0:
            liq_str = f"${pair['liquidity_usd']:,.0f}"
        else:
            liq_str = "N/A"
        
        caption += f"<b>🪙 {pair['pair_name']}</b>\n"
        caption += f"   💰 Harga: <code>{price_str}</code>\n"
        caption += f"   💧 Likuiditas: <code>{liq_str}</code>\n"
        caption += f"   📦 LP Supply: <code>{pair['lp_supply']:,.0f}</code>\n"
        caption += f"   🔗 <a href='{EXPLORER_URL}/address/{pair['address']}'>Lihat Pair</a>\n\n"
    
    caption += "<code>═══════════════════════════════</code>\n"
    caption += f"<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>\n"
    
    # Info halaman
    total = len(pairs)
    current_page = (start_idx // 5) + 1
    total_pages = (total + 4) // 5
    caption += f"\n<i>📄 Halaman {current_page} dari {total_pages} (Total {total} pair)</i>"
    
    return caption

async def main():
    logger.info("Starting...")
    
    if not w3.is_connected():
        logger.error("Gagal konek")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    pairs = get_all_pairs()
    
    if not pairs:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="⚠️ Belum ada pair di RecehDEX",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Kirim per 5 pair
    for i in range(0, len(pairs), 5):
        caption = format_caption(pairs, i, i+5)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=caption,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        await asyncio.sleep(1)  # Jeda biar ga kena rate limit
    
    logger.info(f"Berhasil kirim {len(pairs)} pair dalam {((len(pairs)+4)//5)} pesan")

if __name__ == "__main__":
    asyncio.run(main())
