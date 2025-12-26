import discord
from discord.ext import commands
import json
import os
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
import signal
import sys
from difflib import SequenceMatcher

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
# GRACEFUL SHUTDOWN
# ============================================

def signal_handler(sig, frame):
    print('\n\n🛑 Shutdown...')
    save_knowledge(knowledge_base)
    print('👋 Bot stopped!')
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================
# SMART SEARCH & DETECTION
# ============================================

def search_knowledge_smart(query, return_raw=True):
    """Universal search untuk semua kategori - cek pertanyaan DAN jawaban"""
    results = []
    query_lower = query.lower()
    
    # Filter noise words
    noise_words = ['list', 'semua', 'all', 'kode', 'ada', 'apa', 'saja', 'cari', 'mana', 'daftar']
    keywords = [word for word in query_lower.split() if word not in noise_words]
    
    if not keywords:
        keywords = query_lower.split()
    
    # Cari semua matching results
    for qa in knowledge_base["qa_pairs"]:
        question_lower = qa["question"].lower()
        answer_lower = qa["answer"].lower()
        
        # Hitung score dari pertanyaan DAN jawaban
        question_score = sum(1 for kw in keywords if kw in question_lower)
        answer_score = sum(1 for kw in keywords if kw in answer_lower)
        
        # Total score (prioritaskan match di pertanyaan)
        total_score = (question_score * 2) + answer_score
        
        if total_score > 0:
            results.append({
                "question": qa["question"],
                "answer": qa["answer"],
                "images": qa.get("images", []),
                "score": total_score,
                "match_type": "both" if question_score > 0 and answer_score > 0 
                             else "question" if question_score > 0 
                             else "answer"
            })
    
    # Sort by relevance
    results.sort(key=lambda x: x["score"], reverse=True)
    
    if return_raw:
        return results
    
    # Formatted untuk AI context
    if not results:
        return "Tidak ada data di database."
    
    formatted = "\n\n".join([
        f"Q: {r['question']}\nA: {r['answer']}"
        for r in results[:10]
    ])
    
    return formatted


def detect_query_type(question):
    """Auto-detect jenis pertanyaan"""
    q_lower = question.lower()
    
    # Detect LIST request
    is_list = any(word in q_lower for word in [
        'list', 'semua', 'all', 'semuanya', 'ada apa', 'apa saja',
        'daftar', 'banyak'
    ])
    
    # Detect CODE/ID request
    is_code = any(word in q_lower for word in [
        'kode', 'id', 'code', 'nomor'
    ])
    
    # Extract category
    category = None
    categories = ['buff', 'monster', 'boss', 'quest', 'item', 'lokasi', 
                  'farming', 'crysta', 'equipment', 'skill', 'build']
    
    for cat in categories:
        if cat in q_lower:
            category = cat
            break
    
    # Determine type
    if is_list:
        return {'type': 'list', 'category': category, 'is_code': is_code}
    elif is_code:
        return {'type': 'single', 'category': category, 'is_code': is_code}
    else:
        return {'type': 'complex', 'category': category, 'is_code': False}

# ============================================
# AI RESPONSE - UPDATED WITH SMART FILTERING
# ============================================

async def get_ai_response_with_context(question, context):
    """Call Groq AI dengan context - AI yang analisis & filter sendiri"""
    groq_api_key = os.environ.get("GROQ_API_KEY")
    
    if not groq_api_key:
        if context and context != "Tidak ada data di database.":
            return f"🤖 Dari database:\n\n{context}"
        return "⚠️ GROQ_API_KEY belum diset!"
    
    system_prompt = """Kamu adalah AI helper Toram Online Indonesia yang PINTAR ANALISIS REQUEST USER.

TUGAS UTAMA:
1. **ANALISIS PERTANYAAN USER** - pahami apa yang diminta dan TIDAK diminta
2. **FILTER DATA** sesuai request user
3. **FORMAT OUTPUT** yang clean dan relevant

ATURAN FILTERING:
- Jika user bilang "jangan tampilkan stat" / "jangan stat" / "tanpa stat" → SKIP semua bagian Stat/Effect
- Jika user bilang "tanpa lokasi" / "jangan tempat" / "hide location" → SKIP bagian Tempat/Lokasi/Drop
- Jika user bilang "nama saja" / "list aja" / "hanya nama" → HANYA tampilkan nama item
- Jika user bilang "singkat" → Ringkas info penting saja
- Jika ada keyword NEGATIVE (jangan, tanpa, hide, exclude, kecuali) → IKUTI requestnya!

CONTOH REQUEST & RESPONSE:

❌ SALAH (User: "list xtall senjata jangan tampilkan stat nya"):
Arbogazella (senjata)
Stat:
* Daya Jarak Jauh +7%
* Accuracy +14%
[... menampilkan semua stat yang seharusnya di-skip]

✅ BENAR (User: "list xtall senjata jangan tampilkan stat nya"):
**Xtall Senjata:**
• Arbogazella (senjata)
• Jeandoux (senjata) 
• Kalajengkel (normal)
• Machina (senjata)
• Gwaimol (senjata)

[Total: 5 xtall]

✅ BENAR (User: "list xtall senjata"):
**Xtall Senjata:**

• **Arbogazella (senjata)**
  Stat: Daya Jarak Jauh +7%, Accuracy +14%, MaxHP -28%
  
• **Jeandoux (senjata)**
  Stat: Critical Damage +7, STR +3%, Aggro -10%

[Tampilkan stat karena user TIDAK minta filter]

STYLE JAWABAN:
- **Singkat** untuk list request (bullet points)
- **Detail** untuk pertanyaan spesifik
- **Tanpa stat/lokasi** jika user minta exclude
- Pakai emoji relevan (jangan berlebihan)
- Format markdown: **bold** untuk judul

PRIORITAS:
1. PAHAMI dulu apa yang user TIDAK mau lihat
2. Filter data sesuai request
3. Tampilkan HANYA yang diminta
4. Jujur bilang "tidak tahu" jika tidak ada info"""

    user_prompt = f"""Database info:
{context if context else "Belum ada data spesifik."}

Pertanyaan user: {question}

INGAT: Analisis dulu apa yang user minta dan TIDAK minta, lalu jawab sesuai!"""
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,  # Lower = more consistent filtering
                "max_tokens": 2000
            }
            
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result['choices'][0]['message']['content']
                else:
                    if context and context != "Tidak ada data di database.":
                        return f"🤖 Dari database:\n\n{context}"
                    return "❌ Error API"
    except Exception as e:
        if context and context != "Tidak ada data di database.":
            return f"🤖 Dari database:\n\n{context}\n\n_(AI offline)_"
        return f"❌ Error: {str(e)}"

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
                    "timestamp": str(datetime.now()),
                    "is_detailed": len(answer) > 200 or '\n' in answer
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
# COMMAND: TANYA (SIMPLIFIED - AI DOES THE WORK)
# ============================================

@bot.command(name='tanya', aliases=['ask', 'ai', 't'])
async def ask_ai(ctx, *, question):
    """Tanya ke AI - AI yang analisis & filter sendiri"""
    async with ctx.typing():
        # Search database
        results = search_knowledge_smart(question, return_raw=True)
        
        # ✨ BARU: Collect images dari results
        images_found = []
        
        # Format context for AI
        if results:
            context_parts = []
            for r in results[:15]:
                # Text context
                context_parts.append(f"Q: {r['question']}\nA: {r['answer']}")
                
                # ✨ BARU: Collect images if exists
                if 'images' in r and r['images']:
                    images_found.extend(r['images'])
            
            context = "\n\n---\n\n".join(context_parts)
        else:
            context = "Tidak ada data di database."
        
        # Let AI handle everything: analysis, filtering, formatting
        response = await get_ai_response_with_context(question, context)
        
        # Detect if it's a list/structured response
        is_list_response = (
            response.count('•') > 3 or 
            response.count('\n') > 5 or
            'Total:' in response or
            '**' in response
        )
        
        # Create embed
        if is_list_response:
            embed = discord.Embed(
                title="📋 Hasil Pencarian",
                description=response[:4000],  # Discord limit
                color=0x5865F2,
                timestamp=datetime.now()
            )
        else:
            embed = discord.Embed(
                title="🤖 Toram AI Helper",
                description=response[:4000],
                color=0x5865F2,
                timestamp=datetime.now()
            )
        
        # ✨ BARU: Add images to embed
        if images_found:
            # Tampilkan gambar pertama di embed
            embed.set_image(url=images_found[0])
            
            # Footer dengan info gambar
            if len(images_found) > 1:
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ {len(images_found)} gambar tersimpan")
            else:
                embed.set_footer(text=f"Ditanya oleh {ctx.author.name} | 🖼️ 1 gambar")
        else:
            embed.set_footer(text=f"Ditanya oleh {ctx.author.name}")
        
        await ctx.reply(embed=embed, mention_author=False)
        
        # Save conversation
        knowledge_base["conversations"].append({
            "question": question,
            "answer": response[:500] if len(response) > 500 else response,
            "user": str(ctx.author),
            "timestamp": str(datetime.now())
        })
        save_knowledge(knowledge_base)

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
                "`!teach kode buff maxmp | 3017676`\n"
                "`!teach crysta altadar arm | ATK +8%, MaxHP +800`\n"
                "`!teach lokasi venena | Dark Dragon Shrine level 130+`"
            ),
            color=0xED4245
        )
        await ctx.reply(embed=embed)
        return
    
    question, answer = content.split('|', 1)
    question = question.strip()
    answer = answer.strip()
    
    # ✨ TAMBAHAN: Deteksi gambar
    image_urls = []
    if ctx.message.attachments:
        for attachment in ctx.message.attachments:
            if attachment.content_type.startswith('image/'):
                image_urls.append(attachment.url)
    
    # Simpan ke database
    knowledge_base["qa_pairs"].append({
        "question": question,
        "answer": answer,
        "images": image_urls,  # ✨ BARU
        "taught_by": str(ctx.author),
        "timestamp": str(datetime.now()),
        "is_detailed": len(answer) > 200 or '\n' in answer
    })
    save_knowledge(knowledge_base)
    
    # Embed response
    embed = discord.Embed(title="✅ Berhasil Dipelajari!", color=0x57F287)
    embed.add_field(name="❓ Pertanyaan", value=question, inline=False)
    embed.add_field(name="💡 Jawaban", value=answer, inline=False)
    
    # ✨ Tampilkan gambar
    if image_urls:
        embed.add_field(name="🖼️ Gambar", value=f"{len(image_urls)} gambar tersimpan", inline=False)
        embed.set_image(url=image_urls[0])  # Tampilkan gambar pertama
    
    await ctx.reply(embed=embed)

# ============================================
# DATABASE COMMANDS
# ============================================

@bot.command(name='knowledge', aliases=['database', 'db', 'info'])
async def show_knowledge(ctx):
    """Lihat stats knowledge base"""
    qa_count = len(knowledge_base["qa_pairs"])
    doc_count = len(knowledge_base["documents"])
    conv_count = len(knowledge_base["conversations"])
    
    embed = discord.Embed(title="📚 Toram AI Knowledge Base", color=0x5865F2)
    embed.add_field(name="💬 Q&A", value=f"{qa_count} pasangan", inline=True)
    embed.add_field(name="📄 Dokumen", value=f"{doc_count} docs", inline=True)
    embed.add_field(name="🗨️ History", value=f"{conv_count} chat", inline=True)
    
    if knowledge_base["qa_pairs"]:
        recent = "\n".join([
            f"• {qa['question'][:50]}..." if len(qa['question']) > 50 else f"• {qa['question']}"
            for qa in knowledge_base["qa_pairs"][-5:]
        ])
        embed.add_field(name="🆕 Q&A Terbaru", value=recent or "Kosong", inline=False)
    
    await ctx.reply(embed=embed)

@bot.command(name='search', aliases=['cari', 's'])
async def search_db(ctx, *, query):
    """Cari info di database"""
    results = search_knowledge_smart(query, return_raw=False)
    
    if results == "Tidak ada data di database.":
        embed = discord.Embed(
            title="❌ Tidak Ditemukan",
            description=f"Tidak ada hasil untuk: **{query}**\n\nAjari aku dengan `!teach`",
            color=0xED4245
        )
    else:
        embed = discord.Embed(
            title=f"🔍 Hasil: {query}",
            description=results,
            color=0x5865F2
        )
    
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

# ============================================
# COMMAND: UPDATE (IMPROVED) - Fuzzy Search + Konfirmasi
# ============================================

def find_similar_questions(query, threshold=0.6):
    """Cari pertanyaan yang mirip (fuzzy match)"""
    from difflib import SequenceMatcher
    
    query_lower = query.lower()
    matches = []
    
    for i, qa in enumerate(knowledge_base["qa_pairs"]):
        question_lower = qa["question"].lower()
        
        # Exact match
        if query_lower == question_lower:
            return [(i, qa, 1.0)]  # Perfect match
        
        # Similarity score
        ratio = SequenceMatcher(None, query_lower, question_lower).ratio()
        
        # Contains check
        if query_lower in question_lower or question_lower in query_lower:
            ratio = max(ratio, 0.7)
        
        if ratio >= threshold:
            matches.append((i, qa, ratio))
    
    # Sort by similarity
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[:5]  # Top 5 results

@bot.command(name='update', aliases=['edit', 'ubah'])
async def update_knowledge(ctx, *, content):
    """Update Q&A yang sudah ada - Format: keyword | jawaban baru"""
    if '|' not in content:
        embed = discord.Embed(
            title="❌ Format Salah!",
            description=(
                "**Format:** `!update keyword | jawaban baru`\n\n"
                "**Contoh:**\n"
                "`!update mq bab | [data baru dengan bab 15]`\n"
                "`!update buff maxmp | 3017676 (updated)`\n\n"
                "💡 Tidak perlu ketik pertanyaan lengkap, cukup keyword!"
            ),
            color=0xED4245
        )
        await ctx.reply(embed=embed)
        return
    
    keyword, new_answer = content.split('|', 1)
    keyword = keyword.strip()
    new_answer = new_answer.strip()
    
    # Cari pertanyaan yang mirip
    matches = find_similar_questions(keyword, threshold=0.5)
    
    if not matches:
        embed = discord.Embed(
            title="❌ Tidak Ditemukan",
            description=f"Tidak ada pertanyaan yang mirip dengan **'{keyword}'**\n\n"
                       f"Mau tambah baru? Gunakan:\n`!teach {keyword} | {new_answer[:50]}...`",
            color=0xED4245
        )
        await ctx.reply(embed=embed)
        return
    
    # Jika cuma 1 hasil dan similarity > 0.9, langsung update
    if len(matches) == 1 and matches[0][2] >= 0.9:
        await _do_update(ctx, matches[0][0], matches[0][1], new_answer)
        return
    
    # Multiple results - minta konfirmasi
    embed = discord.Embed(
        title="🔍 Beberapa Hasil Ditemukan",
        description=f"Pilih mana yang mau diupdate untuk **'{keyword}'**:",
        color=0xFEE75C
    )
    
    for idx, (db_index, qa, similarity) in enumerate(matches, start=1):
        answer_preview = qa["answer"][:100] + ("..." if len(qa["answer"]) > 100 else "")
        embed.add_field(
            name=f"{idx}. {qa['question']} ({int(similarity*100)}% match)",
            value=f"```{answer_preview}```",
            inline=False
        )
    
    embed.set_footer(text="Reply dengan nomor (1-5) dalam 30 detik, atau 'cancel' untuk batal")
    
    msg = await ctx.reply(embed=embed)
    
    # Wait for user response
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        response = await bot.wait_for('message', timeout=30.0, check=check)
        
        if response.content.lower() in ['cancel', 'batal', 'tidak', 'no']:
            await ctx.send("❌ Update dibatalkan.")
            return
        
        try:
            choice = int(response.content)
            if 1 <= choice <= len(matches):
                selected = matches[choice - 1]
                await _do_update(ctx, selected[0], selected[1], new_answer)
            else:
                await ctx.send(f"❌ Pilih nomor 1-{len(matches)}")
        except ValueError:
            await ctx.send("❌ Kirim nomor atau 'cancel'")
            
    except TimeoutError:
        await ctx.send("⏱️ Timeout - update dibatalkan.")


async def _do_update(ctx, found_index, old_qa, new_answer):
    """Helper function untuk eksekusi update"""
    is_long = len(new_answer) > 200 or '\n' in new_answer
    
    knowledge_base["qa_pairs"][found_index] = {
        "question": old_qa["question"],
        "answer": new_answer,
        "taught_by": str(ctx.author),
        "timestamp": str(datetime.now()),
        "is_detailed": is_long,
        "updated_from": old_qa["taught_by"],
        "update_count": old_qa.get("update_count", 0) + 1
    }
    
    save_knowledge(knowledge_base)
    
    embed = discord.Embed(
        title="✅ Knowledge Diupdate!" + (" (Detail)" if is_long else ""),
        color=0x57F287
    )
    
    embed.add_field(name="❓ Pertanyaan", value=old_qa["question"], inline=False)
    
    old_preview = old_qa["answer"][:150] + ("..." if len(old_qa["answer"]) > 150 else "")
    new_preview = new_answer[:150] + ("..." if len(new_answer) > 150 else "")
    
    embed.add_field(name="📜 Sebelumnya", value=f"```{old_preview}```", inline=False)
    embed.add_field(name="🆕 Sekarang", value=f"```{new_preview}```", inline=False)
    
    embed.add_field(
        name="📊 Info", 
        value=f"Update #{knowledge_base['qa_pairs'][found_index]['update_count']} | "
              f"Aslinya dari: {old_qa['taught_by']}", 
        inline=False
    )
    
    embed.set_footer(text=f"Diupdate oleh {ctx.author.name}")
    await ctx.reply(embed=embed)

@bot.command(name='append', aliases=['tambah', 'add'])
async def append_knowledge(ctx, *, content):
    """Append info ke Q&A existing - Format: keyword | info tambahan"""
    if '|' not in content:
        embed = discord.Embed(
            title="❌ Format Salah!",
            description=(
                "**Format:** `!append keyword | info tambahan`\n\n"
                "**Contoh:**\n"
                "`!append mq bab | Bab 15: Dragon Scale x1, Mythril x10`\n\n"
                "💡 Keyword cukup sebagian saja!"
            ),
            color=0xED4245
        )
        await ctx.reply(embed=embed)
        return
    
    keyword, additional = content.split('|', 1)
    keyword = keyword.strip()
    additional = additional.strip()
    
    # Cari dengan fuzzy search
    matches = find_similar_questions(keyword, threshold=0.5)
    
    if not matches:
        await ctx.reply(f"❌ **'{keyword}'** tidak ditemukan. Gunakan `!teach` untuk buat baru.")
        return
    
    # Auto-select jika cuma 1 hasil dan sangat mirip
    if len(matches) == 1 and matches[0][2] >= 0.8:
        await _do_append(ctx, matches[0][0], matches[0][1], additional)
        return
    
    # Multiple results - konfirmasi
    embed = discord.Embed(
        title="🔍 Pilih Yang Mana?",
        description=f"Beberapa hasil untuk **'{keyword}'**:",
        color=0xFEE75C
    )
    
    for idx, (db_index, qa, similarity) in enumerate(matches, start=1):
        answer_preview = qa["answer"][:80] + ("..." if len(qa["answer"]) > 80 else "")
        embed.add_field(
            name=f"{idx}. {qa['question']}",
            value=f"```{answer_preview}```",
            inline=False
        )
    
    embed.set_footer(text="Reply dengan nomor dalam 30 detik")
    await ctx.reply(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        response = await bot.wait_for('message', timeout=30.0, check=check)
        choice = int(response.content)
        
        if 1 <= choice <= len(matches):
            selected = matches[choice - 1]
            await _do_append(ctx, selected[0], selected[1], additional)
        else:
            await ctx.send(f"❌ Pilih 1-{len(matches)}")
    except (ValueError, TimeoutError):
        await ctx.send("❌ Dibatalkan")

async def _do_append(ctx, found_index, old_qa, additional):
    """Helper untuk append"""
    new_answer = old_qa["answer"] + "\n" + additional
    
    knowledge_base["qa_pairs"][found_index]["answer"] = new_answer
    knowledge_base["qa_pairs"][found_index]["timestamp"] = str(datetime.now())
    knowledge_base["qa_pairs"][found_index]["updated_by"] = str(ctx.author)
    
    save_knowledge(knowledge_base)
    
    embed = discord.Embed(title="➕ Info Ditambahkan!", color=0x57F287)
    embed.add_field(name="❓ Pertanyaan", value=old_qa["question"], inline=False)
    embed.add_field(name="➕ Ditambahkan", value=additional[:500], inline=False)
    embed.set_footer(text=f"Total: {len(new_answer)} karakter")
    
    await ctx.reply(embed=embed)

@bot.command(name='find', aliases=['cek', 'lookup'])
async def find_question(ctx, *, keyword):
    """Cari pertanyaan dengan fuzzy search"""
    matches = find_similar_questions(keyword, threshold=0.4)
    
    if not matches:
        await ctx.reply(f"❌ Tidak ada yang mirip dengan **'{keyword}'**")
        return
    
    embed = discord.Embed(
        title=f"🔍 Hasil Pencarian: {keyword}",
        description=f"Ditemukan {len(matches)} hasil:",
        color=0x5865F2
    )
    
    for idx, (db_index, qa, similarity) in enumerate(matches, start=1):
        answer_preview = qa["answer"][:200] + ("..." if len(qa["answer"]) > 200 else "")
        
        embed.add_field(
            name=f"{idx}. {qa['question']} ({int(similarity*100)}% match)",
            value=f"```{answer_preview}```\n"
                  f"*Diajarkan: {qa['taught_by']} | Index: #{db_index+1}*",
            inline=False
        )
    
    await ctx.reply(embed=embed)

@bot.command(name='reset')
@commands.has_permissions(administrator=True)
async def reset_knowledge(ctx, section='all'):
    """Reset database (Admin only)"""
    if section == 'all':
        knowledge_base["qa_pairs"] = []
        knowledge_base["documents"] = []
        knowledge_base["conversations"] = []
        msg = "🗑️ Semua data direset!"
    elif section == 'qa':
        knowledge_base["qa_pairs"] = []
        msg = "🗑️ Q&A direset!"
    elif section == 'docs':
        knowledge_base["documents"] = []
        msg = "🗑️ Dokumen direset!"
    else:
        await ctx.reply("❌ Pilihan: all, qa, docs")
        return
    
    save_knowledge(knowledge_base)
    await ctx.reply(msg)

# ============================================
# HELP COMMAND (SIMPLE & CLEAR)
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
        value=(
            "`!tanya <pertanyaan>` - Tanya ke AI\n"
            "`!search <keyword>` - Cari di database\n"
            "`!find <keyword>` - Cari lebih detail\n"
            "`!list [page]` - Lihat semua data"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎓 Mengajari Bot",
        value=(
            "`!teach pertanyaan | jawaban` - Ajari bot\n"
        ),
        inline=False
    )
    
    embed.add_field(
        name="✏️ Edit Data",
        value=(
            "`!update keyword | jawaban` - Ganti data lama\n"
            "`!append keyword | info` - Tambah info\n"
            "`!delete <nomor>` - Hapus data"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 Database",
        value=(
            "`!knowledge` - Info database\n"
            "`!reset` - Reset database (Admin)"
        ),
        inline=False
    )
    
    embed.set_footer(text="Powered by Groq AI")
    await ctx.reply(embed=embed)

# ============================================
# BOT EVENTS
# ============================================

@bot.event
async def on_ready():
    print('='*50)
    print(f'✅ Bot Online: {bot.user}')
    print(f'📚 Knowledge: {len(knowledge_base["qa_pairs"])} Q&A')
    print(f'🌐 Servers: {len(bot.guilds)}')
    print('='*50)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
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
        print(f"Error: {error}")

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
        print("Set di Replit Secrets atau .env file\n")
        sys.exit(1)
    else:
        print("🚀 Starting bot...\n")
        try:
            bot.run(TOKEN)
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
            save_knowledge(knowledge_base)
            print("👋 Stopped!")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            save_knowledge(knowledge_base)
        finally:
            os._exit(0)