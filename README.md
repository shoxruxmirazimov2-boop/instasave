# Instagram Video Downloader Telegram Bot

Bu loyiha Telegram bot bo‘lib, foydalanuvchidan Instagram post URL oladi va videoni yuklab, chatga yuboradi.

Tayyorlash va ishga tushirish (Windows Powershell misoli):

1. Virtual muhit yaratish va faollashtirish:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Paketlarni o‘rnatish:

```powershell
pip install -r requirements.txt
```

3. Telegram token va admin sozlamalarini `.env` faylga qo‘shish:

```powershell
TELEGRAM_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=123456789
REQUIRED_CHANNELS=@kanal1,@kanal2
```

4. Botni ishga tushirish:

```powershell
python bot.py
```

Admin komandalari:
- `/admin` — admin panel
- `/stats` — bot statistikasi
- `/setchannel <kanal>` — majburiy kanalni o‘rnatish
- `/broadcast <matn>` — barcha foydalanuvchilarga reklama yuborish
- `/setcontact <matn>` — admin kontakt/telefon matnini o‘rnatadi (har videoning izohi sifatida ko‘rinadi)

Eslatma:
- Telegram bot API orqali yuklanadigan fayllar odatda ~50MB cheklovi bor. Shu sababli juda katta videolar yuborilmasligi mumkin.
- Ba'zi private/ma'lum sahifalardan yuklash uchun `yt-dlp` cookies yoki autentifikatsiya talab qilishi mumkin.
- `ADMIN_IDS` maydoniga admin bo‘lishi kerak bo‘lgan Telegram user IDlarini qo‘shing.
