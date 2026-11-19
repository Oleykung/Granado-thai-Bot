
import discord
from discord.ext import commands, tasks
import datetime
import json
import os
import asyncio
import re
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "0").strip()
ROLE_MENTION = os.getenv("ROLE_MENTION", "@everyone").strip()

try:
    CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else 0
except:
    CHANNEL_ID = 0

# Timezone fix Windows
try:
    from zoneinfo import ZoneInfo
    try:
        BANGKOK = ZoneInfo("Asia/Bangkok")
    except:
        BANGKOK = datetime.timezone(datetime.timedelta(hours=7))
except:
    BANGKOK = datetime.timezone(datetime.timedelta(hours=7))

print(f"TOKEN: {'✅' if TOKEN else '❌'} | CHANNEL: {CHANNEL_ID}")

# Load bosses
try:
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    BOSSES = cfg.get("bosses", [])
except:
    BOSSES = []

# เก็บเวลาบอสที่โดนฆ่า - นับถอยหลังเกิดใหม่
# Format: {boss_name: {"death": datetime, "respawn": datetime, "killer": str, "channel_id": int}}
boss_deaths = {}

# โหลดจากไฟล์ถ้ามี (กันบอทรีสตาร์ทแล้วลืม)
DEATH_FILE = "boss_deaths.json"
try:
    if os.path.exists(DEATH_FILE):
        with open(DEATH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for name, info in data.items():
                boss_deaths[name] = {
                    "death": datetime.datetime.fromisoformat(info["death"]),
                    "respawn": datetime.datetime.fromisoformat(info["respawn"]),
                    "killer": info["killer"],
                    "channel_id": info.get("channel_id", CHANNEL_ID)
                }
        print(f"📂 โหลดประวัติฆ่าบอส {len(boss_deaths)} ตัว")
except Exception as e:
    print(f"⚠️ โหลดประวัติไม่ได้: {e}")

def save_deaths():
    try:
        data = {}
        for name, info in boss_deaths.items():
            data[name] = {
                "death": info["death"].isoformat(),
                "respawn": info["respawn"].isoformat(),
                "killer": info["killer"],
                "channel_id": info["channel_id"]
            }
        with open(DEATH_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ เซฟไม่ได้: {e}")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=["!", "บ!", "."], intents=intents, help_command=None)

def parse_time(t_str):
    try:
        h, m = map(int, t_str.split(":"))
        return h, m
    except:
        return 0,0

def get_offset_time(base_time_str, offset_min):
    h, m = parse_time(base_time_str)
    now = datetime.datetime.now(BANGKOK)
    dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    dt = dt + datetime.timedelta(minutes=offset_min)
    return dt.strftime("%H:%M")

def get_next_bosses(limit=10):
    now = datetime.datetime.now(BANGKOK)
    upcoming = []
    for minutes_ahead in range(0, 24*60):
        check_time = now + datetime.timedelta(minutes=minutes_ahead)
        check_str = check_time.strftime("%H:%M")
        for boss in BOSSES:
            if check_str in boss.get("times", []):
                diff = minutes_ahead
                if diff == 0:
                    upcoming.append((boss, check_str, "ตอนนี้!", diff))
                else:
                    upcoming.append((boss, check_str, f"อีก {diff} นาที", diff))
        if len(upcoming) >= limit:
            break
    return upcoming

def find_boss_by_name(name_input):
    """หาบอสจากชื่อที่พิมพ์มา"""
    if not name_input:
        return None
    name_lower = name_input.lower().strip()
    for boss in BOSSES:
        b_name = boss["name"]
        b_clean = re.sub(r'[^a-zA-Z0-9ก-ฮะ-์\s]', '', b_name).lower().strip()
        if name_lower in b_name.lower() or name_lower in b_clean or b_clean in name_lower:
            return boss
        # เช็คคำย่อย
        for word in name_lower.split():
            if word and len(word) >= 3 and word in b_name.lower():
                return boss
    return None

def parse_custom_time(text):
    """แปลงข้อความเวลาเป็น timedelta เช่น 2ชม, 30นาที, 1h30m, 2:30"""
    if not text:
        return None
    text = text.lower().strip()
    # แบบ 1:30 (ชั่วโมง:นาที)
    m = re.match(r'^(\d+):(\d+)$', text)
    if m:
        h, mins = int(m.group(1)), int(m.group(2))
        return datetime.timedelta(hours=h, minutes=mins)
    
    total = datetime.timedelta()
    found = False
    # ชม, ชั่วโมง, h, hour
    for pattern in [r'(\d+)\s*ชม', r'(\d+)\s*ชั่วโมง', r'(\d+)\s*h', r'(\d+)\s*hour']:
        mm = re.search(pattern, text)
        if mm:
            total += datetime.timedelta(hours=int(mm.group(1)))
            found = True
    # นาที, น, m, min
    for pattern in [r'(\d+)\s*นาที', r'(\ด+)\s*น\b', r'(\d+)\s*m\b', r'(\d+)\s*min']:
        mm = re.search(pattern, text)
        if mm:
            try:
                total += datetime.timedelta(minutes=int(mm.group(1)))
                found = True
            except:
                pass
    # แบบตัวเลขล้วน เช่น 90 = 90 นาที
    if not found:
        m = re.match(r'^\d+$', text)
        if m:
            # ถ้า <=5 ตีเป็นชั่วโมง, มากกว่าเป็นนาที
            val = int(text)
            if val <= 5:
                return datetime.timedelta(hours=val)
            else:
                return datetime.timedelta(minutes=val)
    return total if found and total.total_seconds() > 0 else None

def extract_boss_and_time(full_text):
    """แยกชื่อบอสกับเวลา เช่น 'World Boss 2ชม' -> ('World Boss', timedelta)"""
    if not full_text:
        return full_text, None
    parts = full_text.strip().split()
    if not parts:
        return full_text, None
    last = parts[-1]
    td = parse_custom_time(last)
    if td:
        boss_name = " ".join(parts[:-1]).strip()
        return boss_name, td
    # ลอง 2 คำสุดท้าย เช่น '1 ชั่วโมง'
    if len(parts) >= 2:
        last2 = " ".join(parts[-2:])
        td = parse_custom_time(last2)
        if td:
            boss_name = " ".join(parts[:-2]).strip()
            return boss_name, td
    return full_text, None

def get_next_scheduled_time(boss):
    """หาเวลาบอสเกิดรอบถัดไปจาก config"""
    now = datetime.datetime.now(BANGKOK)
    times = boss.get("times", [])
    if not times:
        return now + datetime.timedelta(hours=2)
    for minutes_ahead in range(1, 24*60):
        check = now + datetime.timedelta(minutes=minutes_ahead)
        if check.strftime("%H:%M") in times:
            return check
    return now + datetime.timedelta(hours=2)

# ==================== LOOPS ====================
@tasks.loop(seconds=60)
async def boss_checker():
    now = datetime.datetime.now(BANGKOK)
    now_str = now.strftime("%H:%M")
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    for boss in BOSSES:
        for b_time in boss.get("times", []):
            pre10 = get_offset_time(b_time, -10)
            pre5 = get_offset_time(b_time, -5)
            embed = None
            if now_str == pre10:
                embed = discord.Embed(title=f"⏰ อีก 10 นาที {boss['name']} จะเกิด!", description=f"{boss.get('desc','')}\nเวลาเกิด: **{b_time} น.**", color=int(boss.get("color","FF0000"),16))
            elif now_str == pre5:
                embed = discord.Embed(title=f"⚠️ อีก 5 นาที {boss['name']} จะเกิด!", description=f"{boss.get('desc','')}\nเวลาเกิด: **{b_time} น.**", color=0xFFFF00)
            elif now_str == b_time:
                embed = discord.Embed(title=f"🔥 {boss['name']} เกิดแล้ว!", description=f"{boss.get('desc','')}", color=0x00FF00)
            if embed:
                embed.set_footer(text="Granado Espada M TH | GMT+7")
                try:
                    content = ROLE_MENTION if ROLE_MENTION else None
                    await channel.send(content=content, embed=embed)
                    await asyncio.sleep(1)
                except:
                    pass

@tasks.loop(seconds=60)
async def death_countdown_checker():
    """เช็คนับถอยหลังบอสที่โดนฆ่าไป"""
    now = datetime.datetime.now(BANGKOK)
    to_remove = []
    for boss_name, info in list(boss_deaths.items()):
        respawn = info["respawn"]
        # แปลงให้มี timezone ถ้าไม่มี
        if respawn.tzinfo is None:
            respawn = respawn.replace(tzinfo=BANGKOK)
        diff = (respawn - now).total_seconds()
        channel = bot.get_channel(info["channel_id"]) or bot.get_channel(CHANNEL_ID)
        if not channel:
            continue
        
        # ใกล้เกิด 10 นาที, 5 นาที, เกิดแล้ว
        if 599 < diff <= 660:  # 10 นาที
            embed = discord.Embed(title=f"⏰ อีก 10 นาที {boss_name} จะเกิดใหม่!", description=f"โดนฆ่าโดย {info['killer']} ตอน {info['death'].strftime('%H:%M')}\nเกิดใหม่: **{respawn.strftime('%H:%M')} น.**", color=0xFF8C00)
            embed.set_footer(text="นับถอยหลังจากตอนฆ่า")
            try:
                await channel.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)
            except:
                pass
        elif 299 < diff <= 360:  # 5 นาที
            embed = discord.Embed(title=f"⚠️ อีก 5 นาที {boss_name} จะเกิดใหม่!", description=f"เตรียมตัว! โดนฆ่าโดย {info['killer']}", color=0xFFFF00)
            try:
                await channel.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)
            except:
                pass
        elif 0 < diff <= 60:  # เกิดแล้ว
            embed = discord.Embed(title=f"🔥 {boss_name} เกิดใหม่แล้ว!", description=f"โดนฆ่าไปเมื่อ {info['death'].strftime('%H:%M')} โดย {info['killer']}\nรีบไปตีเลย!", color=0x00FF00)
            embed.set_footer(text="นับถอยหลังครบแล้ว")
            try:
                await channel.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)
            except:
                pass
            to_remove.append(boss_name)
        elif diff <= 0:
            to_remove.append(boss_name)
    
    for name in to_remove:
        if name in boss_deaths:
            del boss_deaths[name]
    if to_remove:
        save_deaths()

# ==================== EVENTS ====================
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(f"📩 {message.content} จาก {message.author} ใน #{message.channel.name}")
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"\n✅ บอทออนไลน์: {bot.user}")
    print(f"⏰ เวลาไทย: {datetime.datetime.now(BANGKOK).strftime('%H:%M:%S')}")
    print(f"📜 คำสั่ง: !บอส !ต่อไป !ฆ่า !นับถอยหลัง")
    if not boss_checker.is_running():
        boss_checker.start()
    if not death_countdown_checker.is_running():
        death_countdown_checker.start()
    print(f"💀 โหลดประวัติฆ่า {len(boss_deaths)} ตัว")

# ==================== COMMANDS ====================
@bot.command(name="บอส", aliases=["boss", "bosslist"])
async def boss_list(ctx):
    embed = discord.Embed(title="👹 รายชื่อบอสทั้งหมด", description="เวลาไทย GMT+7", color=0x3498db)
    for boss in BOSSES:
        times = " / ".join(boss.get("times", []))
        embed.add_field(name=f"{boss['name']}", value=f"⏰ {times}\n{boss.get('desc','')}", inline=False)
    embed.set_footer(text=f"ใช้ !ต่อไป ดูบอสใกล้เกิด | {datetime.datetime.now(BANGKOK).strftime('%H:%M')}")
    await ctx.send(embed=embed)

@bot.command(name="ต่อไป", aliases=["next", "nextboss", "บอสต่อไป"])
async def next_boss(ctx):
    upcoming = get_next_bosses(10)
    if not upcoming:
        await ctx.send("ไม่เจอบอสใน 24 ชม.")
        return
    embed = discord.Embed(title="🔥 บอสที่ใกล้จะเกิด", description=f"เวลาตอนนี้: **{datetime.datetime.now(BANGKOK).strftime('%H:%M:%S')}**", color=0xff0000)
    for boss, b_time, when, diff in upcoming:
        if diff == 0:
            embed.add_field(name=f"🔴 {boss['name']} - ตอนนี้!", value=f"⏰ {b_time} | {boss.get('desc','')}", inline=False)
        else:
            embed.add_field(name=f"{boss['name']}", value=f"⏰ {b_time} ({when}) | {boss.get('desc','')}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="เวลา", aliases=["time", "now"])
async def current_time(ctx):
    now = datetime.datetime.now(BANGKOK)
    embed = discord.Embed(title="⏰ เวลาเซิร์ฟเวอร์", color=0x00ff00)
    embed.add_field(name="เวลาไทย GMT+7", value=f"**{now.strftime('%Y-%m-%d %H:%M:%S')}**", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="ทดสอบ", aliases=["test", "เทส"])
async def test_alert(ctx):
    embed = discord.Embed(title="✅ บอททำงานปกติ!", description=f"ห้องนี้: {ctx.channel.id}\nเวลาไทย: {datetime.datetime.now(BANGKOK).strftime('%H:%M:%S')}", color=0x00ff00)
    await ctx.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)

@bot.command(name="ช่วย", aliases=["help", "คำสั่ง"])
async def help_cmd(ctx):
    embed = discord.Embed(title="📜 คำสั่งบอท Granado Espada M TH", color=0x3498db)
    embed.add_field(name="👹 !บอส", value="ดูบอสทั้งหมด", inline=False)
    embed.add_field(name="🔥 !ต่อไป", value="ดูบอสใกล้เกิด", inline=False)
    embed.add_field(name="💀 !ฆ่า ชื่อบอส [เวลา]", value="ฆ่าบอส + นับถอยหลังเกิดใหม่\nตัวอย่าง: `!ฆ่า World Boss`\n`!ฆ่า Saber Tiger 2ชม`\n`!ฆ่า Stone Cortes 30นาที`\n`!ฆ่า Elder Capybara 1:30`", inline=False)
    embed.add_field(name="⏳ !นับถอยหลัง", value="ดูบอสที่กำลังนับถอยหลังเกิดใหม่", inline=False)
    embed.add_field(name="⏰ !เวลา", value="เช็คเวลาไทย", inline=False)
    embed.add_field(name="🗑️ !ล้าง", value="ล้างนับถอยหลังทั้งหมด", inline=False)
    embed.set_footer(text="Prefix: ! . บ! | พิมพ์ !ช่วย ดูวิธีใช้")
    await ctx.send(embed=embed)

# ===== คำสั่งฆ่าบอส + นับถอยหลัง =====
@bot.command(name="ฆ่า", aliases=["kill", "ฆ่าบอส", "บอสตาย", "ตาย"])
async def kill_boss(ctx, *, full_text: str = ""):
    if not full_text:
        embed = discord.Embed(title="💀 จะฆ่าตัวไหน?", description="ตัวอย่าง:\n`!ฆ่า World Boss`\n`!ฆ่า Saber Tiger 2ชม`\n`!ฆ่า Stone Cortes 30นาที`\n`!ฆ่า Elder Capybara 1:30`", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    boss_name_input, custom_td = extract_boss_and_time(full_text)
    found_boss = find_boss_by_name(boss_name_input)
    
    now = datetime.datetime.now(BANGKOK)
    killer = ctx.author.display_name
    
    if found_boss:
        display_name = found_boss["name"]
        # คำนวณเวลาเกิดใหม่
        if custom_td:
            respawn = now + custom_td
            time_desc = f"นับถอยหลัง {full_text.split()[-1]} (กำหนดเอง)"
        else:
            respawn = get_next_scheduled_time(found_boss)
            time_desc = f"ตามตารางบอส"
        
        # เก็บลง dict
        boss_deaths[display_name] = {
            "death": now,
            "respawn": respawn,
            "killer": killer,
            "channel_id": ctx.channel.id
        }
        save_deaths()
        
        diff = respawn - now
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)
        if hours > 0:
            countdown_str = f"{hours} ชม. {minutes} นาที"
        else:
            countdown_str = f"{minutes} นาที"
        
        embed = discord.Embed(title=f"💀 {display_name} ตายแล้ว!", description=f"ถูกฆ่าโดย **{killer}**", color=0x8B0000)
        embed.add_field(name="🕒 เวลาตาย", value=now.strftime("%H:%M:%S น."), inline=True)
        embed.add_field(name="⏳ เกิดใหม่ใน", value=f"**{countdown_str}**", inline=True)
        embed.add_field(name="⏰ เวลาเกิดใหม่", value=f"**{respawn.strftime('%H:%M:%S')} น.**", inline=False)
        embed.add_field(name="📝 หมายเหตุ", value=time_desc, inline=False)
        embed.add_field(name="🔔", value="บอทจะแจ้งเตือนก่อนเกิด 10 นาที / 5 นาที / ตอนเกิด", inline=False)
        embed.set_footer(text=f"พิมพ์ !นับถอยหลัง เพื่อดูทั้งหมด")
        await ctx.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)
    else:
        # ไม่เจอในลิส แต่ก็ให้นับถอยหลังได้ (บอสทั่วไป)
        if custom_td:
            respawn = now + custom_td
        else:
            respawn = now + datetime.timedelta(hours=2)  # default 2 ชม.
        
        display_name = boss_name_input or full_text
        boss_deaths[display_name] = {
            "death": now,
            "respawn": respawn,
            "killer": killer,
            "channel_id": ctx.channel.id
        }
        save_deaths()
        
        diff = respawn - now
        minutes = int(diff.total_seconds() // 60)
        
        embed = discord.Embed(title=f"💀 {display_name} ตายแล้ว!", description=f"**{killer}** จัดการเรียบร้อย!", color=0x8B0000)
        embed.add_field(name="⏳ เกิดใหม่ใน", value=f"{minutes} นาที", inline=True)
        embed.add_field(name="⏰ เวลาเกิดใหม่", value=f"{respawn.strftime('%H:%M')} น.", inline=True)
        await ctx.send(embed=embed)

@bot.command(name="นับถอยหลัง", aliases=["countdown", "นับ", "ถอยหลัง", "เคาน์ดาวน์", "cd", "เหลือ"])
async def countdown_list(ctx):
    if not boss_deaths:
        embed = discord.Embed(title="⏳ ไม่มีบอสที่นับถอยหลังอยู่", description="พิมพ์ `!ฆ่า ชื่อบอส` เพื่อเริ่มนับ", color=0x808080)
        await ctx.send(embed=embed)
        return
    
    now = datetime.datetime.now(BANGKOK)
    embed = discord.Embed(title="⏳ บอสที่นับถอยหลังเกิดใหม่", description=f"เวลาตอนนี้: {now.strftime('%H:%M:%S')}", color=0xFF8C00)
    
    for name, info in boss_deaths.items():
        respawn = info["respawn"]
        if respawn.tzinfo is None:
            respawn = respawn.replace(tzinfo=BANGKOK)
        diff = (respawn - now).total_seconds()
        if diff <= 0:
            embed.add_field(name=f"🔥 {name} - เกิดแล้ว!", value=f"ฆ่าโดย {info['killer']} | {info['death'].strftime('%H:%M')}", inline=False)
        else:
            h = int(diff // 3600)
            m = int((diff % 3600) // 60)
            s = int(diff % 60)
            if h > 0:
                left = f"{h}ชม {m}นาที"
            elif m > 0:
                left = f"{m}นาที {s}วิ"
            else:
                left = f"{s}วินาที"
            embed.add_field(name=f"💀 {name}", value=f"⏳ เหลือ **{left}** | เกิด **{respawn.strftime('%H:%M:%S')}** | ฆ่าโดย {info['killer']}", inline=False)
    
    embed.set_footer(text="บอทจะแจ้งเตือนก่อนเกิด 10 นาที / 5 นาที")
    await ctx.send(embed=embed)

@bot.command(name="ล้าง", aliases=["clear", "ล้างนับถอยหลัง", "reset"])
async def clear_countdown(ctx, *, name: str = ""):
    if not name:
        boss_deaths.clear()
        save_deaths()
        await ctx.send("🗑️ ล้างนับถอยหลังทั้งหมดแล้ว!")
    else:
        found = None
        for key in list(boss_deaths.keys()):
            if name.lower() in key.lower():
                found = key
                break
        if found:
            del boss_deaths[found]
            save_deaths()
            await ctx.send(f"🗑️ ลบ {found} ออกจากนับถอยหลังแล้ว")
        else:
            await ctx.send(f"ไม่เจอ {name} ในลิสต์นับถอยหลัง")

@bot.command(name="ชุบ", aliases=["revive", "เกิด"])
async def revive_boss(ctx, *, boss_name: str = ""):
    if not boss_name:
        await ctx.send("จะชุบตัวไหน? เช่น `!ชุบ World Boss`")
        return
    # ลบออกจากนับถอยหลังถ้ามี
    for key in list(boss_deaths.keys()):
        if boss_name.lower() in key.lower():
            del boss_deaths[key]
    save_deaths()
    embed = discord.Embed(title=f"✨ {boss_name} เกิดใหม่แล้ว!", description="รีบไปตีเลย!", color=0x00FF00)
    await ctx.send(content=ROLE_MENTION if ROLE_MENTION else None, embed=embed)

# Keep Alive Flask
try:
    from flask import Flask
    from threading import Thread
    app = Flask(__name__)
    @app.route('/')
    def home():
        return f"Bot {bot.user if hasattr(bot, 'user') and bot.user else 'Loading'} Online! Time: {datetime.datetime.now(BANGKOK)} Deaths: {len(boss_deaths)}"
    @app.route('/health')
    def health():
        return "OK", 200
    def run_flask():
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)
    Thread(target=run_flask, daemon=True).start()
except:
    pass

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ไม่เจอ TOKEN")
    elif CHANNEL_ID == 0:
        print("❌ CHANNEL_ID เป็น 0")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            import traceback
            traceback.print_exc()
