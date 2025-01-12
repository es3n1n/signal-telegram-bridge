from multiprocessing import Process
from time import sleep

from loguru import logger

from .modules import signal, telegram


def main() -> None:
    processes = (
        Process(target=signal.start),
        Process(target=telegram.start),
    )

    logger.info(f'Starting {len(processes)} processes')
    for process in processes:
        process.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info(f'Stopping {len(processes)} processes')
        for process in processes:
            process.terminate()


if __name__ == '__main__':
    main()
