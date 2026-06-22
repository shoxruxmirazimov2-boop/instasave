import asyncio
import json
import logging
import os
import tempfile
import shutil
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp


load_dotenv()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_IDS = [int(x.strip()) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip().isdigit()]
BOT_DATA_FILE = os.path.join(os.path.dirname(__file__), 'bot_data.json')
BOT_TAG = os.environ.get('BOT_TAG', '@insta_savevideosbot')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DATA = {
    'users': {},
    'stats': {
        'requests': 0,
        'videos_sent': 0,
        'broadcasts': 0,
    },
    'required_channels': [],
    'contact_text': '',
    'pending': {},
}


def load_data():
    if not os.path.exists(BOT_DATA_FILE):
        return DEFAULT_DATA.copy()
    try:
        with open(BOT_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {**DEFAULT_DATA, **data}
    except Exception:
        return DEFAULT_DATA.copy()


def save_data(data):
    try:
        with open(BOT_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error('Data save error: %s', e)


DATA = load_data()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def update_user_info(update: Update):
    user = update.effective_user
    if user is None:
        return
    user_id = str(user.id)
    info = DATA['users'].get(user_id, {})
    info.update({
        'username': user.username or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'language_code': user.language_code or '',
    })
    DATA['users'][user_id] = info
    save_data(DATA)


async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    required_channels = DATA.get('required_channels', [])
    if not required_channels or user is None or is_admin(user.id):
        return True

    missing = []
    for ch in required_channels:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
                continue
            else:
                missing.append(ch)
        except Exception as e:
            logger.warning('Channel check error for %s: %s', ch, e)
            missing.append(ch)

    if not missing:
        return True

    await update.message.reply_text(
        f'Iltimos, avval quyidagi kanallarga obuna bo‘ling: {", ".join(missing)}'
    )
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_info(update)
    text = 'Salom! Instagram linkini yuboring — men videoni yuklab yuboraman.'
    if DATA.get('required_channel'):
        text += f"\n\nBotdan foydalanish uchun quyidagi kanalga obuna bo‘lish kerak: {DATA['required_channel']}"
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        '/start - Botni ishga tushirish',
        '/help - Bu yordam matni',
        'Instagram url yuborish - video yuklash',
    ]
    if is_admin(update.effective_user.id if update.effective_user else 0):
        commands.extend([
            '/admin - Admin panel',
            '/stats - Statistika ko‘rish',
            '/setchannel <username_or_id> - Majburiy kanal o‘rnatish',
            '/broadcast <matn> - Hammaga reklama yuborish',
        ])
    await update.message.reply_text('\n'.join(commands))


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        await update.message.reply_text(f'Sizning Telegram ID: {user.id}')
    else:
        await update.message.reply_text('Foydalanuvchi ma`lumot topilmadi.')


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = ADMIN_IDS
    text = f'Konfiguratsiyadagi ADMIN_IDS: {admins}'
    # also show whether the requester is an admin
    req_id = update.effective_user.id if update.effective_user else 0
    text += f'\nSiz adminmisiz: {is_admin(req_id)}'
    await update.message.reply_text(text)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text('Siz admin emassiz.')
        return

    required_channels = DATA.get('required_channels', [])
    required_channel = ', '.join(required_channels) if required_channels else 'yo‘q'
    keyboard = [
        [InlineKeyboardButton('Statistika', callback_data='admin_stats')],
        [InlineKeyboardButton('Majburiy kanalni o‘rnatish', callback_data='admin_setchannel')],
        [InlineKeyboardButton('Reklama yuborish', callback_data='admin_broadcast')],
        [InlineKeyboardButton('Kontakt (telefon)', callback_data='admin_setcontact')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    contact = DATA.get('contact_text', '') or 'yo‘q'
    text = (
        'Admin panel:\n'
        f'Kanallar: {required_channel}\n'
        f'Kontakt: {contact}\n\n'
        'Quyidagilardan birini tanlang:'
    )
    await update.message.reply_text(text, reply_markup=reply_markup)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    user_id = query.from_user.id if query.from_user else 0
    if not is_admin(user_id):
        await query.answer('Siz admin emassiz.', show_alert=True)
        return

    callback = query.data
    if callback == 'admin_stats':
        await stats_command(update, context)
    elif callback == 'admin_setchannel':
        await query.answer()
        await query.edit_message_text(
            'Iltimos, /setchannel <kanal_username_yoki_id> komandasini kiriting.'
        )
    elif callback == 'admin_broadcast':
        await query.answer()
        await query.edit_message_text(
            'Iltimos, /broadcast <xabar> komandasini kiriting.'
        )
    elif callback == 'admin_setcontact':
        await query.answer()
        # enter inline flow: mark admin as awaiting contact tag input
        admin_id = str(query.from_user.id if query.from_user else 0)
        DATA['pending'][admin_id] = 'set_contact'
        save_data(DATA)
        await query.edit_message_text(
            'Iltimos, endi to‘g‘ridan-to‘g‘ri tagni yuboring (masalan @mytag).'
        )
    else:
        await query.answer()


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text('Siz admin emassiz.')
        return

    total_users = len(DATA['users'])
    stats = DATA.get('stats', {})
    required_channels = DATA.get('required_channels', [])
    req_text = ', '.join(required_channels) if required_channels else 'yo‘q'
    text = (
        f'Foydalanuvchilar: {total_users}\n'
        f'So‘rovlar: {stats.get("requests", 0)}\n'
        f'Yuborilgan videolar: {stats.get("videos_sent", 0)}\n'
        f'Reklama yuborishlar: {stats.get("broadcasts", 0)}\n'
        f'Majburiy kanallar: {req_text}\n'
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text)
    else:
        await update.message.reply_text(text)


async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text('Siz admin emassiz.')
        return

    raw = ' '.join(context.args).strip()
    if not raw:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                'Foydalanish: /setchannel @kanal_yoki_id yoki /setchannel @kanal1,@kanal2'
            )
        else:
            await update.message.reply_text('Foydalanish: /setchannel @kanal_yoki_id yoki /setchannel @kanal1,@kanal2')
        return

    # accept comma-separated or space-separated list of channels
    parts = [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]
    DATA['required_channels'] = parts
    save_data(DATA)
    await update.message.reply_text(f'Majburiy kanallar o‘rnatildi: {", ".join(parts)}')


async def set_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text('Siz admin emassiz.')
        return

    contact = ' '.join(context.args).strip()
    if not contact:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                'Foydalanish: /setcontact Telefon yoki boshqa aloqa matnini kiriting'
            )
        else:
            await update.message.reply_text('Foydalanish: /setcontact Telefon yoki boshqa aloqa matnini kiriting')
        return

    DATA['contact_text'] = contact
    save_data(DATA)
    await update.message.reply_text(f'Kontakt matni o‘rnatildi: {contact}')


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text('Siz admin emassiz.')
        return

    message_text = ' '.join(context.args).strip()
    if not message_text:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                'Foydalanish: /broadcast Bu yerga reklama matnini yozing'
            )
        else:
            await update.message.reply_text('Foydalanish: /broadcast Bu yerga reklama matnini yozing')
        return

    counter = 0
    fail_count = 0
    for user_id_str in list(DATA['users'].keys()):
        try:
            await context.bot.send_message(chat_id=int(user_id_str), text=message_text)
            counter += 1
        except Exception as e:
            logger.warning('Broadcast xatolik %s -> %s', user_id_str, e)
            fail_count += 1

    DATA['stats']['broadcasts'] = DATA['stats'].get('broadcasts', 0) + 1
    save_data(DATA)

    await update.message.reply_text(
        f'Reklama yuborildi: {counter} ta foydalanuvchiga. Xatoliklar: {fail_count}'
    )


def download_instagram_video(url, tmpdir):
    ydl_opts = {
        'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if isinstance(info, dict) and 'entries' in info and info['entries']:
            entry = info['entries'][0]
            filename = ydl.prepare_filename(entry)
        else:
            filename = ydl.prepare_filename(info)
        if os.path.exists(filename):
            return filename
        for f in os.listdir(tmpdir):
            if f.lower().endswith(('.mp4', '.mkv', '.webm')):
                return os.path.join(tmpdir, f)
        raise FileNotFoundError('Downloaded file not found')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_info(update)
    text = update.message.text or ''

    # Check pending admin actions first (inline flows)
    user = update.effective_user
    if user:
        pending = DATA.get('pending', {})
        action = pending.get(str(user.id))
        if action == 'set_contact':
            # Only admins can perform this
            if not is_admin(user.id):
                await update.message.reply_text('Siz admin emassiz.')
            else:
                tag = text.strip()
                if not tag:
                    await update.message.reply_text('Iltimos, teg yoki matnni yuboring.')
                else:
                    DATA['contact_text'] = tag
                    # clear pending
                    pending.pop(str(user.id), None)
                    DATA['pending'] = pending
                    save_data(DATA)
                    await update.message.reply_text(f'Tag o‘rnatildi: {tag}')
            return
    if 'instagram.com' not in text:
        await update.message.reply_text('Iltimos, Instagram postiga oid URL yuboring.')
        return

    if not await check_channel_membership(update, context):
        return

    status_msg = await update.message.reply_text('Yuklanmoqda — iltimos kuting...')
    tmpdir = tempfile.mkdtemp(prefix='insta_dl_')
    try:
        loop = asyncio.get_running_loop()
        last_exc = None
        for attempt in range(2):
            try:
                filepath = await loop.run_in_executor(
                    None, download_instagram_video, text.strip(), tmpdir
                )
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                msg_text = str(e).lower()
                if 'timed out' in msg_text or 'timeout' in msg_text:
                    if attempt == 0:
                        await status_msg.edit_text('Vaqt tugadi, qayta urinilyapti...')
                        continue
                await status_msg.edit_text('Yuklashda xatolik yuz berdi.')
                return

        if last_exc is not None:
            await status_msg.edit_text('Yuklashda xatolik yuz berdi: {}'.format(last_exc))
            return

        size = os.path.getsize(filepath)
        if size > 50 * 1024 * 1024:
            await status_msg.edit_text(
                'Fayl juda katta ({:.1f} MB). Bot orqali yuborib bo‘lmaydi.'.format(size / 1024 / 1024)
            )
            return

        # Send video with retries; only show final error if all retries fail.
        await status_msg.edit_text('Yuklandi — yuborilmoqda...')
        send_success = False
        last_send_exc = None
        contact = DATA.get('contact_text', '')
        caption = BOT_TAG
        if contact:
            caption = f"{BOT_TAG}\n{contact}"

        for attempt in range(2):
            try:
                with open(filepath, 'rb') as f:
                    await update.message.reply_video(f, caption=caption)
                send_success = True
                break
            except Exception as e:
                last_send_exc = e
                logger.warning('Send attempt %s failed: %s', attempt + 1, e)
                if attempt == 0:
                    # Inform user we're retrying, but do not show raw exception
                    try:
                        await status_msg.edit_text('Yuborishda muammo — qayta urinilyapti...')
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                else:
                    # final attempt failed
                    try:
                        await status_msg.edit_text('Yuborishda xatolik yuz berdi.')
                    except Exception:
                        pass

        if send_success:
            DATA['stats']['videos_sent'] = DATA['stats'].get('videos_sent', 0) + 1
            DATA['stats']['requests'] = DATA['stats'].get('requests', 0) + 1
            save_data(DATA)
            try:
                await status_msg.edit_text('Video muvaffaqiyatli yuborildi.')
            except Exception:
                pass
        else:
            logger.error('All send attempts failed: %s', last_send_exc)
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


def main():
    if not TELEGRAM_TOKEN:
        print('Please set TELEGRAM_TOKEN in your .env file or environment.')
        return

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('admin', admin_panel))
    application.add_handler(CommandHandler('stats', stats_command))
    application.add_handler(CommandHandler('setchannel', set_channel))
    application.add_handler(CommandHandler('setcontact', set_contact))
    application.add_handler(CommandHandler('broadcast', broadcast))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print('Bot ishga tushdi...')
    application.run_polling()


if __name__ == '__main__':
    main()
