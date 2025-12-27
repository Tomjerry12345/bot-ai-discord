import discord
from discord.ext import commands
import json
import os
from datetime import datetime
import aiohttp
import asyncio
import sys

# ============================================
# ENVIRONMENT SETUP
# ============================================

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("📁 .env file loaded (local mode)")
except ImportError:
    print("📦 dotenv not found, using Replit Secrets")

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN') or os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY') or os.getenv('GROQ_API_KEY')

if GROQ_API_KEY:
    GROQ_API_KEY = GROQ_API_KEY.strip()
    print("✅ GROQ_API_KEY loaded successfully")
else:
    print("⚠️ GROQ_API_KEY tidak ditemukan!")
    print("💡 Bot akan jalan tapi AI tidak akan aktif")

if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN tidak ditemukan di environment!")
    print("💡 Set di Replit Secrets atau .env file")
    sys.exit(1)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Storage
KNOWLEDGE_FILE = 'toram_knowledge.json'
MAX_CONVERSATIONS = 100  # Limit conversation history

def load_knowledge():
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            print("⚠️ Error loading knowledge, creating new")
            return {"qa_pairs": [], "documents": [], "conversations": []}
    return {"qa_pairs": [], "documents": [], "conversations": []}

def save_knowledge(knowledge):
    try:
        # Limit conversations to prevent file bloat
        if len(knowledge["conversations"]) > MAX_CONVERSATIONS:
            knowledge["conversations"] = knowledge["conversations"][-MAX_CONVERSATIONS:]
        
        with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving knowledge: {e}")

knowledge_base = load_knowledge()

# ============================================
# SEARCH WITH SCORING
# ============================================

def search_knowledge(query):
    """Search dengan scoring dan limit hasil"""
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]
    
    if not query_words:
        return knowledge_base["qa_pairs"][:20]
    
    scored_results = []
    
    for qa in knowledge_base["qa_pairs"]:
        question_lower = qa["question"].lower()
        answer_lower = qa["answer"].lower()
        
        score = 0
        if query_lower in question_lower:
            score += 10
        if query_lower in answer_lower:
            score += 5
            
        for word in query_words:
            if word in question_lower:
                score += 3
            if word in answer_lower:
                score += 1
        
        if score > 0:
            scored_results.append((score, qa))
    
    scored_results.sort(reverse=True, key=lambda x: x[0])
    return [item[1] for item in scored_results[:20]]  # Reduced to 20

# ============================================
# AI RESPONSE - OPTIMIZED
# ============================================

async def get_ai_response(question, all_data):
    """AI response dengan error handling yang lebih baik"""
    groq_api_key = GROQ_API_KEY
    
    if not groq_api_key:
        if all_data:
            return f"🤖 Dari database:\n\n{all_data[0]['answer']}"
        return "⚠️ GROQ_API_KEY belum diset!"
    
    groq_api_key = groq_api_key.strip().replace('\n', '').replace('\r', '')
    
    if len(groq_api_key) < 40:
        if all_data:
            return f"🤖 Dari database:\n\n{all_data[0]['answer']}"
        return "⚠️ API key tidak valid!"
    
    # Limit data
    max_items = 10
    limited_data = all_data[:max_items]
    
    # Build context
    context_parts = []
    total_chars = 0
    max_context_chars = 1500
    
    for item in limited_data:
        entry = f"Q: {item['question']}\nA: {item['answer']}"
        if total_chars + len(entry) > max_context_chars:
            break
        context_parts.append(entry)
        total_chars += len(entry)
    
    context_text = "\n\n".join(context_parts) if context_parts else "Tidak ada data relevan"
    
    try:
        # Increased timeout for Replit
        timeout = aiohttp.ClientTimeout(total=25)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "Kamu AI helper Toram Online. Jawab singkat dan jelas maksimal 300 kata."
                    },
                    {
                        "role": "user", 
                        "content": f"""DATABASE:
{context_text}

PERTANYAAN: {question}

Jawab berdasarkan database di atas. Jika tidak ada info, bilang tidak tahu."""
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 500,
                "top_p": 0.9
            }
            
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data
            ) as resp:
                
                if resp.status == 200:
                    result = await resp.json()
                    answer = result['choices'][0]['message']['content']
                    return answer[:1500] if len(answer) > 1500 else answer
                    
                elif resp.status == 401:
                    if limited_data:
                        return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_🔑 API key bermasalah_"
                    return "🔑 API key tidak valid!"
                    
                elif resp.status == 429:
                    if limited_data:
                        return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_⚠️ API rate limit_"
                    return "⚠️ API rate limit!"
                    
                else:
                    if limited_data:
                        return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}"
                    return f"❌ API Error ({resp.status})"
                    
    except asyncio.TimeoutError:
        if limited_data:
            return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_⏱️ Koneksi lambat_"
        return "⏱️ Timeout! Coba lagi."
        
    except Exception as e:
        print(f"❌ AI Error: {str(e)[:200]}")
        if limited_data:
            return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}"
        return "❌ Error, coba lagi!"

# ============================================
# IMPORT FROM TXT
# ============================================

def load_qa_from_txt(file_path):
    """Load Q&A dari file txt"""
    if not os.path.exists(file_path):
        return 0

    added = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '|' not in line:
                    continue

                question, answer = line.split('|', 1)
                question = question.strip()
                answer = answer.strip()

                if question and answer:
                    knowledge_base["qa_pairs"].append({
                        "question": question,
                        "answer": answer,
                        "taught_by": "TXT_IMPORT",
                        "timestamp": str(datetime.now())
                    })
                    added += 1

        save_knowledge(knowledge_base)
    except Exception as e:
        print(f"Error importing txt: {e}")
    
    return added

@bot.command(name='importtxt')
@commands.has_permissions(administrator=True)
async def import_txt(ctx, filename: str = "data_qa.txt"):
    """Import Q&A dari file txt"""
    async with ctx.typing():
        added = load_qa_from_txt(filename)

    if added == 0:
        await ctx.reply(f"❌ Tidak ada data dari `{filename}`")
    else:
        await ctx.reply(f"✅ **{added} Q&A** diimport dari `{filename}`")

# ============================================
# COMMAND: TANYA
# ============================================

@bot.command(name='tanya', aliases=['ask', 'ai', 't'])
async def ask_ai(ctx, *, question):
    """Tanya ke AI"""
    
    if len(question) < 3:
        await ctx.reply("❓ Pertanyaan terlalu pendek!")
        return
    
    async with ctx.typing():
        try:
            all_data = search_knowledge(question)
            
            # Collect images (max 2)
            images_found = []
            if all_data:
                for item in all_data[:8]:
                    if 'images' in item and item['images']:
                        images_found.extend(item['images'][:1])
                        if len(images_found) >= 2:
                            break
            
            response = await get_ai_response(question, all_data)
            
            embed = discord.Embed(
                title="🤖 Toram AI Helper",
                description=response[:4000],
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            if images_found:
                embed.set_image(url=images_found[0])
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ {len(images_found)} gambar")
            else:
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name}")
            
            await ctx.reply(embed=embed, mention_author=False)
            
            # Save conversation (non-blocking)
            asyncio.create_task(save_conversation_async(question, response, str(ctx.author)))
            
        except Exception as e:
            print(f"❌ Error in ask_ai: {str(e)}")
            await ctx.reply("❌ Terjadi error! Coba lagi atau gunakan `!list`")

async def save_conversation_async(question, response, user):
    """Save conversation without blocking"""
    try:
        knowledge_base["conversations"].append({
            "question": question[:200],
            "answer": response[:300],
            "user": user,
            "timestamp": str(datetime.now())
        })
        save_knowledge(knowledge_base)
    except:
        pass

# ============================================
# COMMAND: TEACH
# ============================================

@bot.command(name='teach', aliases=['ajari', 'train'])
async def teach_bot(ctx, *, content):
    """Ajari bot dengan format: pertanyaan | jawaban"""
    if '|' not in content:
        embed = discord.Embed(
            title="❌ Format Salah!",
            description=(
                "**Format:** `!teach pertanyaan | jawaban`\n\n"
                "**Contoh:**\n"
                "`!teach kode buff maxmp | 3017676`"
            ),
            color=0xED4245
        )
        await ctx.reply(embed=embed)
        return
    
    question, answer = content.split('|', 1)
    question = question.strip()
    answer = answer.strip()
    
    # Deteksi gambar
    image_urls = []
    if ctx.message.attachments:
        for attachment in ctx.message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image_urls.append(attachment.url)
    
    # Simpan ke database
    knowledge_base["qa_pairs"].append({
        "question": question,
        "answer": answer,
        "images": image_urls,
        "taught_by": str(ctx.author),
        "timestamp": str(datetime.now())
    })
    save_knowledge(knowledge_base)
    
    # Embed response
    embed = discord.Embed(title="✅ Berhasil Dipelajari!", color=0x57F287)
    embed.add_field(name="❓ Pertanyaan", value=question, inline=False)
    
    if image_urls:
        answer_with_images = answer
        for i, img_url in enumerate(image_urls, 1):
            answer_with_images += f"\n\n🖼️ **Gambar {i}:** [Lihat]({img_url})"
        embed.add_field(name="💡 Jawaban", value=answer_with_images, inline=False)
        embed.set_image(url=image_urls[0])
    else:
        embed.add_field(name="💡 Jawaban", value=answer, inline=False)
    
    await ctx.reply(embed=embed)

# ============================================
# DATABASE COMMANDS
# ============================================

@bot.command(name='knowledge', aliases=['database', 'db', 'info'])
async def show_knowledge(ctx):
    """Lihat stats knowledge base"""
    qa_count = len(knowledge_base["qa_pairs"])
    
    embed = discord.Embed(title="📚 Toram AI Knowledge Base", color=0x5865F2)
    embed.add_field(name="💬 Q&A", value=f"{qa_count} pasangan", inline=True)
    
    if knowledge_base["qa_pairs"]:
        recent = "\n".join([
            f"• {qa['question'][:50]}..." if len(qa['question']) > 50 else f"• {qa['question']}"
            for qa in knowledge_base["qa_pairs"][-5:]
        ])
        embed.add_field(name="🆕 Q&A Terbaru", value=recent or "Kosong", inline=False)
    
    await ctx.reply(embed=embed)

@bot.command(name='list')
async def list_qa(ctx, page: int = 1):
    """List semua Q&A (paginated)"""
    per_page = 10
    total = len(knowledge_base["qa_pairs"])
    
    if total == 0:
        await ctx.reply("📭 Belum ada Q&A. Ajari aku pakai `!teach`")
        return
    
    max_page = (total + per_page - 1) // per_page
    page = max(1, min(page, max_page))
    
    start = (page - 1) * per_page
    end = start + per_page
    qa_list = knowledge_base["qa_pairs"][start:end]
    
    embed = discord.Embed(
        title=f"📋 Daftar Q&A (Halaman {page}/{max_page})",
        color=0x5865F2
    )
    
    for i, qa in enumerate(qa_list, start=start+1):
        embed.add_field(
            name=f"{i}. {qa['question'][:60]}",
            value=qa['answer'][:100] + ("..." if len(qa['answer']) > 100 else ""),
            inline=False
        )
    
    embed.set_footer(text=f"Total: {total} Q&A | Gunakan !list <page>")
    await ctx.reply(embed=embed)

@bot.command(name='delete', aliases=['hapus'])
@commands.has_permissions(manage_messages=True)
async def delete_qa(ctx, index: int):
    """Hapus Q&A berdasarkan nomor"""
    if 1 <= index <= len(knowledge_base["qa_pairs"]):
        deleted = knowledge_base["qa_pairs"].pop(index - 1)
        save_knowledge(knowledge_base)
        await ctx.reply(f"✅ Dihapus: **{deleted['question']}**")
    else:
        await ctx.reply(f"❌ Index {index} tidak valid! Lihat pakai `!list`")

@bot.command(name='reset')
@commands.has_permissions(administrator=True)
async def reset_knowledge(ctx):
    """Reset database (Admin only)"""
    knowledge_base["qa_pairs"] = []
    knowledge_base["documents"] = []
    knowledge_base["conversations"] = []
    save_knowledge(knowledge_base)
    await ctx.reply("🗑️ Semua data direset!")

# ============================================
# HELP COMMAND
# ============================================

@bot.command(name='help', aliases=['toram', 'bantuan'])
async def help_command(ctx):
    """Panduan bot"""
    embed = discord.Embed(
        title="🎮 Toram AI Bot",
        description="Bot AI yang bisa belajar dari kamu!",
        color=0x5865F2
    )
    
    embed.add_field(
        name="💬 Bertanya",
        value="`!tanya <pertanyaan>` - Tanya ke AI\n`!list [page]` - Lihat semua data",
        inline=False
    )
    
    embed.add_field(
        name="🎓 Mengajari Bot",
        value="`!teach pertanyaan | jawaban` - Ajari bot",
        inline=False
    )
    
    embed.add_field(
        name="📊 Database",
        value="`!knowledge` - Info database\n`!delete <nomor>` - Hapus data\n`!reset` - Reset database (Admin)",
        inline=False
    )
    
    embed.set_footer(text="Powered by Groq AI")
    await ctx.reply(embed=embed)

@bot.command(name='testapi')
@commands.has_permissions(administrator=True)
async def test_api(ctx):
    """Test Groq API connection"""
    await ctx.reply("🔍 Testing Groq API...")
    
    if not GROQ_API_KEY:
        await ctx.reply("❌ GROQ_API_KEY tidak ditemukan!")
        return
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "Say: OK"}],
                "max_tokens": 5
            }
            
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    await ctx.reply(f"✅ API Working!\n```{result['choices'][0]['message']['content']}```")
                else:
                    error = await resp.text()
                    await ctx.reply(f"❌ API Error {resp.status}:\n```{error[:500]}```")
    except Exception as e:
        await ctx.reply(f"❌ Connection Error:\n```{str(e)[:500]}```")

# ============================================
# BOT EVENTS
# ============================================

@bot.event
async def on_ready():
    print('='*50)
    print(f'✅ Bot Online: {bot.user}')
    print(f'📚 Knowledge: {len(knowledge_base["qa_pairs"])} Q&A')
    print(f'🌍 Groq API: {"✅ Configured" if GROQ_API_KEY else "❌ Missing"}')
    print('='*50)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Toram Online | !help"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"❌ Parameter kurang! Coba `!help`")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ Kamu gak punya izin!")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Command error: {error}")

# ============================================
# KEEP ALIVE - SIMPLIFIED
# ============================================

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route('/health')
def health():
    return {
        "status": "online",
        "bot": str(bot.user) if bot.is_ready() else "starting...",
        "guilds": len(bot.guilds) if bot.is_ready() else 0
    }

def run():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
    print("✅ Keep-alive started on port 8080")

# ============================================
# RUN BOT
# ============================================

if __name__ == "__main__":
    keep_alive()
    
    if not DISCORD_TOKEN:
        print("\n❌ DISCORD_TOKEN tidak ditemukan!")
        sys.exit(1)
    else:
        print("🚀 Starting bot...\n")
        try:
            bot.run(DISCORD_TOKEN)
        except KeyboardInterrupt:
            print("\n👋 Bot stopped by user")
            save_knowledge(knowledge_base)
        except Exception as e:
            print(f"\n❌ Fatal Error: {e}")
            save_knowledge(knowledge_base)
            sys.exit(1)