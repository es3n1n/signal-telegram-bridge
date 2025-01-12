import mimetypes
from base64 import b64decode
from typing import Any, TypeAlias, cast

from aiogram.types import (
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    MessageEntity,
)
from aiogram.types.input_file import BufferedInputFile
from loguru import logger
from signalbot import Command, Context

from bridge.accounts import signal as bot
from bridge.accounts import telegram
from bridge.core.config import settings


AnyInputFile: TypeAlias = InputMediaAudio | InputMediaDocument | InputMediaPhoto | InputMediaVideo


def _name(context: Context) -> str:
    return cast(dict[str, dict], context.message.raw_message)['envelope']['sourceName']


async def forward_sticker(chat_id: int, data_message: dict, context: Context) -> Any:
    sticker_data: dict | None = data_message.get('sticker')
    if not sticker_data:
        logger.error('No sticker data!')
        return None

    sticker_file_path = settings.SIGNAL_CLI_PATH / 'stickers' / sticker_data['packId'] / str(sticker_data['stickerId'])
    if not sticker_file_path.exists():
        return await telegram.send_message(chat_id, text=f'{_name(context)} Sent a sticker, but we can not forward it')

    logger.info(f'Forwarding a sticker to TG:{chat_id} from SIGNAL:{context.message.group}')
    await telegram.send_message(chat_id, text=f'{_name(context)}:')
    return await telegram.send_sticker(
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


async def forward_message(chat_id: int, data_message: dict, context: Context) -> Any:
    prefix: str = f'{_name(context)}: '
    text: str = f'{prefix}{data_message.get("message", "") or ""}'.strip()
    entities = _map_entities(len(prefix), data_message)

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
        return await telegram.send_media_group(chat_id, media)

    logger.info(f'Forwarding a text message to TG:{chat_id} from SIGNAL:{context.message.group}')
    return await telegram.send_message(chat_id, text=text, entities=entities)


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

        # Forward a sticker if there is one
        data_message: dict = raw_msg.get('dataMessage', {})
        if 'sticker' in data_message:
            return await forward_sticker(telegram_chat, data_message, context)

        return await forward_message(telegram_chat, data_message, context)


def start() -> None:
    bot.register(Listener())
    bot.start()
