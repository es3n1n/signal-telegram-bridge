import mimetypes
from base64 import b64decode
from typing import Any, TypeAlias, cast

from aiogram.types import (
    BufferedInputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    MessageEntity,
)
from loguru import logger
from signalbot import Command, Context

from bridge.accounts import bot_for_signal_user, telegram
from bridge.accounts import signal as bot
from bridge.core.config import settings
from bridge.util.string import add_quote


AnyInputFile: TypeAlias = InputMediaAudio | InputMediaDocument | InputMediaPhoto | InputMediaVideo


def _name(context: Context) -> str:
    return cast(dict[str, dict], context.message.raw_message)['envelope']['sourceName']


async def forward_sticker(chat_id: int, data_message: dict, context: Context) -> Any:
    pers = bot_for_signal_user(context.message.source_uuid)
    sticker_data: dict | None = data_message.get('sticker')
    if not sticker_data:
        logger.error('No sticker data!')
        return None

    sticker_file_path = settings.SIGNAL_CLI_PATH / 'stickers' / sticker_data['packId'] / str(sticker_data['stickerId'])
    if not sticker_file_path.exists():
        return await pers.bot.send_message(chat_id, text=f'{_name(context)} Sent a sticker, but we can not forward it')

    logger.info(f'Forwarding a sticker to TG:{chat_id} from SIGNAL:{context.message.group}')
    if not pers.is_personalized:
        await telegram.send_message(chat_id, text=f'{_name(context)}:')
    return await pers.bot.send_sticker(
        chat_id,
        sticker=BufferedInputFile(
            file=sticker_file_path.read_bytes(),
            filename='sticker.png',
        ),
    )


def _map_entities(prefix_length: int, data_message: dict) -> list[MessageEntity]:
    entities: list[MessageEntity] = []

    for entity in data_message.get('textStyles', []):
        if entity['style'] == 'ITALIC':
            mapped_type = 'italic'
        elif entity['style'] == 'STRIKETHROUGH':
            mapped_type = 'strikethrough'
        elif entity['style'] == 'MONOSPACE':
            mapped_type = 'code'
        elif entity['style'] == 'BOLD':
            mapped_type = 'bold'
        elif entity['style'] == 'SPOILER':
            mapped_type = 'spoiler'
        else:
            logger.warning(f'Unknown style {entity}')
            continue

        entities.append(
            MessageEntity(
                type=mapped_type,
                offset=prefix_length + entity['start'],
                length=entity['length'],
            )
        )

    return entities


async def handle_commands(data_message: dict, context: Context) -> bool:
    message_text: str = data_message.get('message', '')
    if not message_text:
        return False

    if message_text == '/id':
        text: str = f'your id: {context.message.source_uuid}'
        if 'quote' in data_message:
            text += f'\nquoted user id: {data_message["quote"]["authorUuid"]}'

        await bot.send(receiver=context.message.group, text=text)
        return True

    return False


async def forward_message(chat_id: int, data_message: dict, context: Context) -> Any:
    # No need to forward that
    if await handle_commands(data_message, context):
        return None

    pers = bot_for_signal_user(context.message.source_uuid)
    prefix: str = f'{_name(context)}: '

    # No need for prefixes for personalized bots
    if pers.is_personalized:
        prefix = ''

    # Init the entities before we map them so we can push our stuff first with edited prefix
    entities: list[MessageEntity] = []

    # Proceed quote
    quote: dict | None = data_message.get('quote')
    if quote:
        quote_text: str = quote.get('text') or f'Message with {len(quote["attachments"])} attachments'

        started_at = len(prefix)
        prefix += add_quote(quote_text)
        prefix = prefix.strip()
        prefix += '\n'
        end_at = len(prefix)

        entities.append(
            MessageEntity(
                type='blockquote',
                offset=started_at,
                length=end_at - started_at,
            )
        )

    entities.extend(_map_entities(len(prefix), data_message))
    text: str = f'{prefix}{data_message.get("message", "") or ""}'.strip()

    if context.message.attachments_local_filenames:
        media: list[AnyInputFile] = []

        for i, (info, value) in enumerate(
            zip(
                data_message['attachments'],
                context.message.base64_attachments,
                strict=False,
            )
        ):
            tgt_type: type[AnyInputFile] = InputMediaDocument

            mime = info.get('contentType', '') or ''
            if mime.startswith('audio/'):
                tgt_type = InputMediaAudio
            elif mime.startswith('image/'):
                tgt_type = InputMediaPhoto
            elif mime.startswith('video/'):
                tgt_type = InputMediaVideo

            file_name = info['filename'] or info['id']
            if not info['filename'] and mime:
                file_name += f'.{mimetypes.guess_extension(mime)}'

            media.append(
                tgt_type(
                    media=BufferedInputFile(
                        file=b64decode(value),
                        filename=file_name,
                    ),
                    caption=text if i == 0 else None,
                    caption_entities=entities if i == 0 else None,
                )
            )

        logger.info(f'Forwarding message with {len(media)} media TG:{chat_id} from SIGNAL:{context.message.group}')
        return await pers.bot.send_media_group(chat_id, media)

    logger.info(f'Forwarding a text message to TG:{chat_id} from SIGNAL:{context.message.group}')
    return await pers.bot.send_message(chat_id, text=text, entities=entities)


class Listener(Command):
    async def handle(self, context: Context) -> None:
        msg = context.message
        raw_msg = cast(dict[str, dict], msg.raw_message)['envelope']

        if not context.message.is_group():
            return None

        try:
            index = settings.SIGNAL_CHATS.index(context.message.group)
        except ValueError:
            logger.warning(f'Got a message from unknown group: {context.message.group}')
            return None

        # Setup chat
        telegram_chat: int = settings.TELEGRAM_CHATS[index]
        data_message: dict = raw_msg.get('dataMessage', {})

        # Skip reactions
        if 'reaction' in data_message:
            return None

        # Special treatment of stickers
        if 'sticker' in data_message:
            return await forward_sticker(telegram_chat, data_message, context)

        return await forward_message(telegram_chat, data_message, context)


def start() -> None:
    bot.register(Listener())
    bot.start()
