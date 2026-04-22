import asyncio
from web3 import Web3
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import logging
from datetime import datetime
import os
import requests

# ================= KONFIGURASI =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ALAMAT CONTRACT (Sudah saya pastikan)
USD_ADDRESS = "0x6dC1bC519a8c861d509351763a6f9aBb6B07b57B"  # USDr
FACTORY_ADDRESS = "0xAeEdf8B9925c6316171f7c2815e387DE596Fa11B"

RPC_URL = "https://seed-richechain.com"
DEX_URL = "https://dex.cryptoreceh.com/riche"
PAIR_INFO_URL = "https://dex.cryptoreceh.com/info"
CREATE_TOKEN_URL = "https://app.cryptoreceh.com"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner.png"

# Koneksi ke Blockchain
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Setup logging biar bisa lihat prosesnya
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= ABI (Cuma yang penting aja) =================
FACTORY_ABI = [
    {"constant": True, "inputs": [], "name": "allPairsLength", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "uint256"}], "name": "allPairs", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

PAIR_ABI = [
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [{"name": "_reserve0", "type": "uint112"}, {"name": "_reserve1", "type": "uint112"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}], "type": "function"}
]

TOKEN_ABI = [
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
]

# ================= FUNGSI BANTUAN =================
def get_token_info(token_address):
    """Ambil simbol dan decimals token."""
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except Exception as e:
        logger.error(f"Gagal ambil info token {token_address}: {e}")
        return "Unknown", 18

def get_top_3_pairs():
    """Fungsi ini dipastikan benar untuk menghitung harga pair USDr/TOKEN."""
    try:
        # 1. Konek ke Factory
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pair di factory: {total_pairs}")

        active_pairs = []

        # 2. Loop semua pair
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair_contract = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)

                token0_address = pair_contract.functions.token0().call().lower()
                token1_address = pair_contract.functions.token1().call().lower()
                reserves = pair_contract.functions.getReserves().call()
                reserve0_raw, reserve1_raw = reserves[0], reserves[1]

                # Cek apakah pair ini adalah USDr/TOKEN
                if token0_address == USD_ADDRESS.lower():
                    # Pair: USDr / TOKEN
                    usd_reserve_raw = reserve0_raw
                    token_reserve_raw = reserve1_raw
                    token_addr = token1_address
                elif token1_address == USD_ADDRESS.lower():
                    # Pair: TOKEN / USDr
                    usd_reserve_raw = reserve1_raw
                    token_reserve_raw = reserve0_raw
                    token_addr = token0_address
                else:
                    # Bukan pair dengan USDr, skip
                    continue

                # Ambil info token (simbol dan decimals)
                token_symbol, token_decimals = get_token_info(token_addr)
                
                # Konversi reserve ke angka normal (misal 1.000.000)
                # Decimals USDr adalah 18, decimals token bisa beda
                usd_reserve = usd_reserve_raw / (10 ** 18)
                token_reserve = token_reserve_raw / (10 ** token_decimals)

                # HITUNG HARGA! Ini rumus yang benar.
                # Harga = Reserve Token / Reserve USD
                if usd_reserve > 0:
                    price = token_reserve / usd_reserve
                else:
                    price = 0

                # Total Likuiditas dalam USD (USDr Reserve * 2)
                liquidity_usd = usd_reserve * 2

                # Filter: Hanya tampilkan yang likuiditasnya > 0
                if liquidity_usd > 1 and price > 0:
                    active_pairs.append({
                        "symbol": token_symbol,
                        "address": token_addr,
                        "price": price,
                        "liquidity": liquidity_usd,
                    })
                    logger.info(f"BERHASIL - Pair {token_symbol}/USDr: Price = ${price:.8f}, Liq = ${liquidity_usd:.2f}")

            except Exception as e:
                logger.error(f"Gagal proses pair index {i}: {e}")
                continue

        # 3. Urutkan dari likuiditas tertinggi, ambil 3 teratas
        active_pairs.sort(key=lambda x: x['liquidity'], reverse=True)
        return active_pairs[:3]

    except Exception as e:
        logger.error(f"GAGAL TOTAL: {e}")
        return []

async function main() {
    logger.info("🚀 Bot RecehDEX Top 3 Pair Dimulai...")

    # Cek koneksi ke Riche Chain
    if not w3.is_connected():
        logger.error("❌ Gagal konek ke Riche Chain.")
        return

    logger.info(f"✅ Konek ke Riche Chain. Block: {w3.eth.block_number}")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Ambil Top 3 Pair
    top_pairs = get_top_3_pairs()

    if not top_pairs:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ Tidak ada pair aktif yang ditemukan.")
        return

    # ================= MEMBUAT PESAN =================
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for idx, pair in enumerate(top_pairs, 1):
        # Format Harga (biar rapi)
        if pair['price'] < 0.0001:
            price_str = f"${pair['price']:.10f}"
        elif pair['price'] < 0.01:
            price_str = f"${pair['price']:.8f}"
        elif pair['price'] < 1:
            price_str = f"${pair['price']:.6f}"
        else:
            price_str = f"${pair['price']:.4f}"
        
        # Format Likuiditas
        liq_str = f"${pair['liquidity']:,.2f}"

        # Link Trade
        trade_url = f"{DEX_URL}?inputCurrency={USD_ADDRESS}&outputCurrency={pair['address']}"

        message += f"<b>{idx}. {pair['symbol']}/USD</b>\n"
        message += f"   💰 Price: <code>{price_str}</code>\n"
        message += f"   💧 Liquidity: <code>{liq_str}</code>\n"
        message += f"   🔗 <a href='{trade_url}'>Trade Now</a>\n\n"

    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"

    # ================= MEMBUAT TOMBOL =================
    keyboard = [
        [
            InlineKeyboardButton("📊 RecehDEX", url=DEX_URL),
            InlineKeyboardButton("ℹ️ PairInfo", url=PAIR_INFO_URL),
        ],
        [InlineKeyboardButton("✨ Create Token", url=CREATE_TOKEN_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ================= KIRIM KE TELEGRAM =================
    # Download Banner
    try:
        response = requests.get(BANNER_URL, timeout=10)
        if response.status_code == 200:
            await bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=response.content,
                caption=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            logger.info("✅ Pesan dengan banner berhasil dikirim.")
        else:
            raise Exception("Gagal download banner")
    except Exception as e:
        logger.error(f"Gagal kirim banner: {e}, mengirim pesan teks saja.")
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        logger.info("✅ Pesan teks berhasil dikirim.")

if __name__ == "__main__":
    asyncio.run(main())
