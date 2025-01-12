import base64
import mimetypes
from asyncio import run

from aiogram import Dispatcher, types
from loguru import logger

from bridge.accounts import signal
from bridge.accounts import telegram as bot
from bridge.core.config import settings


dp = Dispatcher()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


async def download(file_name: str, file_id: str) -> str:
    f = await bot.download(file_id)
    if not f:
        raise ValueError

    mime_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
    return f'data:{mime_type};filename={file_name};base64,{b64(f.read())}'


async def _handle_photos(photos: list[types.PhotoSize], filename: str) -> str | None:
    if not photos:
        return None

    best_photo = max(photos, key=lambda p: p.file_size or 0)
    return await download(filename, best_photo.file_id)


def _handle_location(loc: types.Location) -> str:
    text = 'Location:\n'
    text += f'lat: {loc.latitude}\n'
    text += f'long: {loc.longitude}'
    if loc.horizontal_accuracy:
        text += f'\naccuracy: {loc.horizontal_accuracy}'
    if loc.heading:
        text += f'\nheading_deg: {loc.heading}'
    if loc.proximity_alert_radius:
        text += f'\nproximity_dist: {loc.proximity_alert_radius}'
    return text


def _handle_special_text(message: types.Message) -> str | None:  # noqa: PLR0911
    if message.dice:
        return f'{message.dice.emoji} ({message.dice.value})'
    if message.game:
        return f'Game - {message.game.title}'
    if message.poll:
        options = '\n'.join(f'- {option.text}' for option in message.poll.options)
        return f'Poll - {message.poll.question}\n\n{options}'
    if message.venue:
        return f'Venue - {message.venue.title}\nAddress: {message.venue.address}'
    if message.location:
        return _handle_location(message.location)
    if message.new_chat_members:
        return '\n'.join(f'Member {user.full_name} joined' for user in message.new_chat_members)
    if message.left_chat_member:
        return f'Member {message.left_chat_member.full_name} left the chat'
    if message.new_chat_title:
        return f'Chat was renamed to {message.new_chat_title}'
    return None


async def _extract_message(message: types.Message) -> tuple[list[str], str, str]:
    prefix = 'Unknown'
    if message.from_user:
        prefix = message.from_user.full_name

    media_types = {
        'audio': lambda m: (m.audio.file_name or 'audio.mp3', m.audio.file_id),
        'document': lambda m: (
            m.document.file_name or (message.animation.file_name if message.animation else None) or 'document.bin',
            m.document.file_id,
        ),
        'sticker': lambda m: ('sticker.webp', m.sticker.file_id),
        'video': lambda m: (m.video.file_name or 'video.mp4', m.video.file_id),
        'video_note': lambda m: ('video_message.mp4', m.video_note.file_id),
        'voice': lambda m: ('audio_message.ogg', m.voice.file_id),
    }

    attachments = []
    for media_type, get_file_info in media_types.items():
        if getattr(message, media_type, None):
            filename, file_id = get_file_info(message)
            attachments.append(await download(filename, file_id))

    if photo := await _handle_photos(message.photo or [], 'photo.jpg'):
        attachments.append(photo)

    if new_photo := await _handle_photos(message.new_chat_photo or [], 'new_chat_photo.jpg'):
        attachments.append(new_photo)
        return attachments, prefix, 'Chat photo was changed'

    text = message.text or message.caption or ''
    if special_text := _handle_special_text(message):
        text = special_text

    return attachments, prefix, text


@dp.message()
async def on_message(message: types.Message) -> None:
    try:
        index = settings.TELEGRAM_CHATS.index(message.chat.id)
    except ValueError:
        logger.warning(f'Got a message from unknown chat: {message.chat.id}')
        return

    signal_chat: str = settings.SIGNAL_CHATS[index]
    attachments, prefix, text = await _extract_message(message)

    logger.info(
        f'Forwarding a message with {len(attachments)} entities to SIGNAL:{signal_chat} from TG:{message.chat.id}'
    )
    await signal.send(signal_chat, text=f'{prefix}: {text}'.strip(), base64_attachments=attachments)


async def _start() -> None:
    await signal._detect_groups()  # noqa: SLF001
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def start() -> None:
    run(_start())
