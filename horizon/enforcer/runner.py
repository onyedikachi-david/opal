import json
import asyncio
import logging
import time

from horizon.config import OPA_PORT
from horizon.logger import get_logger, logger
from horizon.utils import AsyncioEventLoopThread

runner_logger = get_logger("Opa Runner")
opa_logger = get_logger("OPA")

def logging_level_from_string(level: str) -> int:
    """
    logger.log() requires an int logging level
    """
    level = level.lower()
    if level == "info":
        return logging.INFO
    elif level == "critical":
        return logging.CRITICAL
    elif level == "fatal":
        return logging.FATAL
    elif level == "error":
        return logging.ERROR
    elif level == "warning" or level == "warn":
        return logging.WARNING
    elif level == "debug":
        return logging.DEBUG
    # default
    return logging.INFO

class OpaRunner:
    """
    Runs Opa in a subprocess
    """
    def __init__(self, port=OPA_PORT):
        self._port = port
        self._stopped = False
        self._process = None
        self._thread = AsyncioEventLoopThread(name="OpaRunner")

    def start(self):
        logger.info("Launching opa runner")
        self._thread.create_task(self._run_opa_continuously())
        self._thread.start()

    def stop(self):
        logger.info("Stopping opa runner")
        self._stopped = True
        self._terminate_opa()
        time.sleep(1) # will block main thread
        self._thread.stop()

    @property
    def command(self):
        return f"opa run --server -a :{self._port}"

    def _terminate_opa(self):
        runner_logger.info("Stopping OPA")
        self._process.terminate()

    async def _run_opa_continuously(self):
        while not self._stopped:
            runner_logger.info("Running OPA", command=self.command)
            return_code = await self._run_opa_until_terminated()
            runner_logger.info("OPA exited", return_code=return_code)

    async def _run_opa_until_terminated(self) -> int:
        """
        This function runs opa server as a subprocess.
        it returns only when the process terminates.
        """
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait([
            self._log_output(self._process.stdout),
            self._log_output(self._process.stderr)
        ])
        return await self._process.wait()

    async def _log_output(self, stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                log_line = json.loads(line)
                msg = log_line.pop("msg", None)
                level = logging_level_from_string(log_line.pop("level", "info"))
                if msg is not None:
                    opa_logger.log(level, msg, **log_line)
                else:
                    opa_logger.log(level, line)
            except json.JSONDecodeError:
                opa_logger.info(line)

opa_runner = OpaRunner()