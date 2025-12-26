import discord
from discord.ext import commands
import json
import os
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Storage
KNOWLEDGE_FILE = 'toram_knowledge.json'

def load_knowledge():
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"qa_pairs": [], "documents": [], "conversations": []}

def save_knowledge(knowledge):
    with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(knowledge, f, ensure_ascii=False, indent=2)

knowledge_base = load_knowledge()

# ============================================
# SIMPLE SEARCH - NO FILTERING
# ============================================

# def search_knowledge(query):
#     """Simple search - kirim semua data ke AI, biar AI yang filter"""
#     results = []
#     query_lower = query.lower()
    
#     # Cari semua yang ada keyword-nya (minimal match)
#     for qa in knowledge_base["qa_pairs"]:
#         question_lower = qa["question"].lower()
#         answer_lower = qa["answer"].lower()
        
#         # Check if ANY word from query exists
#         if any(word in question_lower or word in answer_lower 
#                for word in query_lower.split()):
#             results.append({
#                 "question": qa["question"],
#                 "answer": qa["answer"],
#                 "images": qa.get("images", [])
#             })
    
#     return results

def search_knowledge(query):
    """Search dengan scoring dan limit hasil"""
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]  # Skip kata pendek
    
    if not query_words:
        return knowledge_base["qa_pairs"][:20]  # Fallback
    
    scored_results = []
    
    for qa in knowledge_base["qa_pairs"]:
        question_lower = qa["question"].lower()
        answer_lower = qa["answer"].lower()
        
        score = 0
        # Exact match = prioritas tertinggi
        if query_lower in question_lower:
            score += 10
        if query_lower in answer_lower:
            score += 5
            
        # Word match
        for word in query_words:
            if word in question_lower:
                score += 3
            if word in answer_lower:
                score += 1
        
        if score > 0:
            scored_results.append((score, qa))
    
    # Sort dan limit ke 25 hasil terbaik (Replit friendly)
    scored_results.sort(reverse=True, key=lambda x: x[0])
    return [item[1] for item in scored_results[:25]]


# ============================================
# AI RESPONSE - FULL CONTROL TO AI
# ============================================

# async def get_ai_response(question, all_data):
#     """AI yang tentukan context, filter, dan format sendiri"""
#     groq_api_key = os.environ.get("GROQ_API_KEY")
    
#     if not groq_api_key:
#         if all_data:
#             return f"🤖 Dari database:\n\n{all_data[0]['answer']}"
#         return "⚠️ GROQ_API_KEY belum diset!"
    
#     # Kirim SEMUA data mentah, tanpa filter apapun
#     context_text = "\n\n".join([
#         f"Q: {item['question']}\nA: {item['answer']}"
#         for item in all_data
#     ]) if all_data else "Database kosong"
    
#     try:
#         async with aiohttp.ClientSession() as session:
#             headers = {
#                 "Authorization": f"Bearer {groq_api_key}",
#                 "Content-Type": "application/json"
#             }
            
#             data = {
#                 "model": "llama-3.3-70b-versatile",
#                 "messages": [
#                     {
#                         "role": "user", 
#                         "content": f"""Kamu AI helper game Toram Online.

# DATABASE:
# {context_text}

# PERTANYAAN USER: {question}

# INSTRUKSI:
# - Analisis sendiri data mana yang relevan
# - Filter sendiri info yang perlu ditampilkan
# - Format output sesuai kebutuhan (list/detail/singkat)
# - Jika user minta "tanpa X" atau "jangan Y", skip bagian itu
# - Jawab natural dan to the point"""
#                     }
#                 ],
#                 "temperature": 0.3,
#                 "max_tokens": 2000
#             }
            
#             async with session.post(
#                 "https://api.groq.com/openai/v1/chat/completions",
#                 headers=headers,
#                 json=data
#             ) as resp:
#                 if resp.status == 200:
#                     result = await resp.json()
#                     return result['choices'][0]['message']['content']
#                 else:
#                     if all_data:
#                         return f"🤖 Dari database:\n\n{all_data[0]['answer']}"
#                     return "❌ Error API"
#     except Exception as e:
#         if all_data:
#             return f"🤖 Dari database:\n\n{all_data[0]['answer']}\n\n_(AI offline)_"
#         return f"❌ Error: {str(e)}"

async def get_ai_response(question, all_data):
    """AI response dengan batasan ketat untuk Replit"""
    groq_api_key = os.environ.get("GROQ_API_KEY")
    
    if not groq_api_key:
        if all_data:
            return f"🤖 Dari database:\n\n{all_data[0]['answer']}"
        return "⚠️ GROQ_API_KEY belum diset!"
    
    # LIMIT data yang dikirim (penting untuk Replit!)
    max_items = 20  # Maksimal 20 Q&A
    limited_data = all_data[:max_items]
    
    # Build context dengan batasan karakter
    context_parts = []
    total_chars = 0
    max_context_chars = 2500  # Batasan ketat untuk Replit
    
    for item in limited_data:
        entry = f"Q: {item['question']}\nA: {item['answer']}"
        if total_chars + len(entry) > max_context_chars:
            break
        context_parts.append(entry)
        total_chars += len(entry)
    
    context_text = "\n\n".join(context_parts) if context_parts else "Tidak ada data relevan"
    
    try:
        # Timeout ketat untuk Replit
        timeout = aiohttp.ClientTimeout(total=12)
        
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
                        "content": "Kamu AI helper Toram Online. Jawab singkat, jelas, dan to the point. Maksimal 400 kata."
                    },
                    {
                        "role": "user", 
                        "content": f"""DATABASE:
{context_text}

PERTANYAAN: {question}

Jawab berdasarkan database di atas. Jika tidak ada info, bilang tidak tahu."""
                    }
                ],
                "temperature": 0.2,  # Lebih rendah = lebih konsisten
                "max_tokens": 800,   # Dikurangi untuk response cepat
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
                    # Truncate jika terlalu panjang
                    return answer[:2000] if len(answer) > 2000 else answer
                    
                elif resp.status == 429:  # Rate limit
                    print("⚠️ Rate limit Groq API")
                    if limited_data:
                        return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_⚠️ API sedang sibuk_"
                    return "⚠️ API rate limit, coba lagi sebentar!"
                    
                else:
                    error_text = await resp.text()
                    print(f"❌ API Error {resp.status}: {error_text[:200]}")
                    if limited_data:
                        return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}"
                    return f"❌ API Error ({resp.status})"
                    
    except asyncio.TimeoutError:
        print("⏱️ Timeout - Replit connection slow")
        if limited_data:
            return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_⏱️ Koneksi lambat, gunakan data lokal_"
        return "⏱️ Timeout! Coba lagi atau gunakan !list untuk lihat data."
        
    except aiohttp.ClientError as e:
        print(f"❌ Network error: {str(e)}")
        if limited_data:
            return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_❌ Network error_"
        return "❌ Koneksi bermasalah, coba lagi!"
        
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        if limited_data:
            return f"🤖 **Dari database:**\n\n{limited_data[0]['answer']}\n\n_⚠️ Fallback mode_"
        return f"❌ Error: {str(e)[:100]}"

# ============================================
# IMPORT FROM TXT
# ============================================

def load_qa_from_txt(file_path):
    """Load Q&A dari file txt"""
    if not os.path.exists(file_path):
        print(f"❌ File tidak ditemukan: {file_path}")
        return 0

    added = 0
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

# @bot.command(name='tanya', aliases=['ask', 'ai', 't'])
# async def ask_ai(ctx, *, question):
#     """Tanya ke AI"""
#     async with ctx.typing():
#         # Get all matching data (no filtering)
#         all_data = search_knowledge(question)
        
#         # Collect images
#         images_found = []
#         if all_data:
#             for item in all_data:
#                 if 'images' in item and item['images']:
#                     images_found.extend(item['images'])
        
#         # AI process everything
#         response = await get_ai_response(question, all_data)
        
#         # Create embed
#         embed = discord.Embed(
#             title="🤖 Toram AI Helper",
#             description=response[:4000],
#             color=0x5865F2,
#             timestamp=datetime.now()
#         )
        
#         # Add images
#         if images_found:
#             embed.set_image(url=images_found[0])
#             if len(images_found) > 1:
#                 embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ {len(images_found)} gambar")
#             else:
#                 embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ 1 gambar")
#         else:
#             embed.set_footer(text=f"Ditanya oleh {ctx.author.name}")
        
#         await ctx.reply(embed=embed, mention_author=False)
        
#         # Save conversation
#         knowledge_base["conversations"].append({
#             "question": question,
#             "answer": response[:500],
#             "user": str(ctx.author),
#             "timestamp": str(datetime.now())
#         })
#         save_knowledge(knowledge_base)

@bot.command(name='tanya', aliases=['ask', 'ai', 't'])
async def ask_ai(ctx, *, question):
    """Tanya ke AI"""
    
    # Quick validation
    if len(question) < 3:
        await ctx.reply("❓ Pertanyaan terlalu pendek!")
        return
    
    async with ctx.typing():
        try:
            # Get matching data
            all_data = search_knowledge(question)
            
            # Collect images (max 3)
            images_found = []
            if all_data:
                for item in all_data[:10]:  # Only check first 10
                    if 'images' in item and item['images']:
                        images_found.extend(item['images'][:1])  # Max 1 per item
                        if len(images_found) >= 3:
                            break
            
            # Get AI response
            response = await get_ai_response(question, all_data)
            
            # Create embed
            embed = discord.Embed(
                title="🤖 Toram AI Helper",
                description=response[:4000],
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            # Add first image only
            if images_found:
                embed.set_image(url=images_found[0])
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ {len(images_found)} gambar | {len(all_data)} data")
            else:
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | {len(all_data)} data ditemukan")
            
            await ctx.reply(embed=embed, mention_author=False)
            
            # Save conversation (async to not block)
            knowledge_base["conversations"].append({
                "question": question[:200],
                "answer": response[:300],
                "user": str(ctx.author),
                "timestamp": str(datetime.now())
            })
            save_knowledge(knowledge_base)
            
        except Exception as e:
            print(f"❌ Error in ask_ai: {str(e)}")
            await ctx.reply(f"❌ Terjadi error: {str(e)[:100]}\n\nCoba lagi atau gunakan `!list`")

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
    
    # Tampilkan jawaban dengan link gambar
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

# ============================================
# BOT EVENTS
# ============================================

# @bot.event
# async def on_ready():
#     print('='*50)
#     print(f'✅ Bot Online: {bot.user}')
#     print(f'📚 Knowledge: {len(knowledge_base["qa_pairs"])} Q&A')
#     print('='*50)
    
#     await bot.change_presence(
#         activity=discord.Activity(
#             type=discord.ActivityType.playing,
#             name="Toram Online | !help"
#         )
#     )

@bot.event
async def on_ready():
    print('='*50)
    print(f'✅ Bot Online: {bot.user}')
    print(f'📚 Knowledge: {len(knowledge_base["qa_pairs"])} Q&A')
    print(f'🌍 Groq API: {"✅ Configured" if os.environ.get("GROQ_API_KEY") else "❌ Missing"}')
    print(f'🔑 Discord Token: {"✅ Set" if os.environ.get("DISCORD_TOKEN") else "❌ Missing"}')
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

# ============================================
# KEEP ALIVE
# ============================================

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running!"

def run():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run, daemon=True).start()

# ============================================
# RUN BOT
# ============================================

if __name__ == "__main__":
    keep_alive()
    
    TOKEN = os.environ.get('DISCORD_TOKEN')
    
    if not TOKEN:
        print("\n❌ DISCORD_TOKEN tidak ditemukan!")
        sys.exit(1)
    else:
        print("🚀 Starting bot...\n")
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            save_knowledge(knowledge_base)
        finally:
            os._exit(0)