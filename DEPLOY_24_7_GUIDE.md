# Granado Espada M TH - Boss Bot 24H + Countdown (Render Ready)

## ฟีเจอร์เวอร์ชันล่าสุด (มีนับถอยหลัง)
- ⏰ แจ้งเตือนบอสอัตโนมัติตามตาราง (10นาที/5นาที/ตอนเกิด)
- 💀 !ฆ่า ชื่อบอส [เวลา] -> นับถอยหลังเกิดใหม่ + แจ้งเตือน
  ตัวอย่าง: !ฆ่า World Boss / !ฆ่า Saber Tiger 2ชม / !ฆ่า Stone Cortes 30นาที
- ⏳ !นับถอยหลัง / !countdown -> ดูบอสทั้งหมดที่กำลังนับ
- 👹 !บอส / !ต่อไป / !เวลา / !ช่วย / !ทดสอบ
- 🌐 Flask Keep-Alive รองรับ Render 24H

## วิธี Deploy บน Render.com ให้รัน 24 ชม.

### ขั้นตอนที่ 1: อัปโหลดขึ้น GitHub
1. ไป https://github.com/new สร้าง repo ชื่อ granado-boss-bot (Public)
2. อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์นี้ขึ้นไป (ยกเว้น .env - มี .gitignore กันไว้แล้ว)

### ขั้นตอนที่ 2: Deploy บน Render
1. ไป https://dashboard.render.com -> สมัครด้วย GitHub
2. New + -> Web Service -> เลือก repo granado-boss-bot
3. ตั้งค่า:
   Build Command: pip install -r requirements.txt
   Start Command: python bot.py
4. เลื่อนลง Environment -> Add:
   DISCORD_TOKEN = Token บอทคุณ (จาก https://discord.com/developers/applications)
   CHANNEL_ID = ID ห้อง Discord (เปิด Developer Mode แล้วคลิกขวาห้อง Copy ID)
   ROLE_MENTION = @everyone
5. กด Create Web Service -> รอ 2 นาที ดู Logs ถ้าขึ้น ✅ บอทออนไลน์ = สำเร็จ!

### ขั้นตอนที่ 3: กันหลับด้วย UptimeRobot (สำคัญ!)
Render ฟรีจะหลับหลัง 15 นาทีถ้าไม่มีคนเข้า ต้องใช้ตัวปลุก
1. ก็อป URL ที่ Render ให้มา เช่น https://granado-boss-bot.onrender.com
2. ไป https://uptimerobot.com สมัครฟรี -> Add New Monitor
   Type: HTTP(s) / URL: วาง URL จาก Render / Interval: 5 minutes / Create
3. เสร็จ! บอทจะออนไลน์ 24 ชม. แท้ๆ

เช็คว่าออนไลน์: เปิด URL Render จะขึ้น "Bot ... is Online! Time: ..."

### คำสั่งบอท
!บอส - ดูบอสทั้งหมด
!ต่อไป - ดูบอสใกล้เกิด
!ฆ่า World Boss - ฆ่า + นับถอยหลังตามตาราง
!ฆ่า Saber Tiger 2ชม - นับ 2 ชม.
!นับถอยหลัง - ดูบอสที่นับอยู่
!ล้าง - ล้างนับถอยหลัง
!เวลา - เช็คเวลาไทย
!ช่วย - ดูวิธีใช้
