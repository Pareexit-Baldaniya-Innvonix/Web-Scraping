# ----- library import -----
import asyncio
from typing import List, Optional

# ----- local import -----
from src.utils.logger import get_logger

logger = get_logger("OTP")


class OtpManager:
    _pending_future: Optional["asyncio.Future[str]"] = None
    _lock = asyncio.Lock()

    _last_error: Optional[str] = None

    _pending_choice_future: Optional["asyncio.Future[str]"] = None
    _choice_options: List[str] = []
    _choice_lock = asyncio.Lock()

    # ----- called by the frontend poller -----
    @classmethod
    def is_waiting(cls) -> bool:
        return cls._pending_future is not None and not cls._pending_future.done()

    # ----- called by the frontend poller to show why it's asking again (e.g. "wrong code") -----
    @classmethod
    def get_error(cls) -> Optional[str]:
        return cls._last_error

    # ----- request otp from the user -----
    @classmethod
    async def request_otp(cls, error: Optional[str] = None) -> "asyncio.Future[str]":
        async with cls._lock:
            if cls._pending_future is not None and not cls._pending_future.done():
                # ----- a request is already pending, reuse it -----
                if error:
                    cls._last_error = error
                return cls._pending_future

            loop = asyncio.get_running_loop()
            cls._pending_future = loop.create_future()
            cls._last_error = error
            logger.info(
                "OTP requested from user. Waiting for dashboard popup submission..."
            )
            return cls._pending_future

    # ----- called by the /api/otp/submit route -----
    @classmethod
    def submit_otp(cls, otp: str) -> bool:
        otp = (otp or "").strip()
        if not otp:
            return False

        if cls._pending_future is None or cls._pending_future.done():
            logger.warning("OTP submitted but no pending OTP request was found.")
            return False

        cls._last_error = None
        cls._pending_future.set_result(otp)
        logger.info(
            "OTP received from dashboard popup and dispatched to the login flow."
        )
        return True

    # ----- called on timeout / cleanup so a stale future never blocks future requests -----
    @classmethod
    def cancel(cls) -> None:
        if cls._pending_future is not None and not cls._pending_future.done():
            cls._pending_future.cancel()
        cls._pending_future = None
        cls._last_error = None

    # ----- called by the frontend poller -----
    @classmethod
    def is_choice_waiting(cls) -> bool:
        return (
            cls._pending_choice_future is not None
            and not cls._pending_choice_future.done()
        )

    # ----- called by the frontend poller to render the option buttons -----
    @classmethod
    def get_choice_options(cls) -> List[str]:
        return list(cls._choice_options)

    # ----- called by the scraper when the delivery-method chooser screen is detected -----
    @classmethod
    async def request_choice(cls, options: List[str]) -> "asyncio.Future[str]":
        async with cls._choice_lock:
            if (
                cls._pending_choice_future is not None
                and not cls._pending_choice_future.done()
            ):
                # ----- a request is already pending, reuse it -----
                return cls._pending_choice_future

            loop = asyncio.get_running_loop()
            cls._pending_choice_future = loop.create_future()
            cls._choice_options = list(options)
            logger.info(
                "OTP delivery-method choice requested from user. Options: %s", options
            )
            return cls._pending_choice_future

    # ----- called by the /api/otp/choice/submit route -----
    @classmethod
    def submit_choice(cls, choice: str) -> bool:
        choice = (choice or "").strip()
        if not choice:
            return False

        if cls._pending_choice_future is None or cls._pending_choice_future.done():
            logger.warning(
                "OTP delivery-method choice submitted but no pending choice request was found."
            )
            return False

        if cls._choice_options and choice not in cls._choice_options:
            logger.warning(
                "Submitted OTP delivery-method choice '%s' does not match any offered option %s.",
                choice,
                cls._choice_options,
            )
            return False

        cls._pending_choice_future.set_result(choice)
        logger.info(
            "OTP delivery-method choice '%s' received from dashboard popup.", choice
        )
        return True

    # ----- called on timeout / cleanup so a stale future never blocks future requests -----
    @classmethod
    def cancel_choice(cls) -> None:
        if (
            cls._pending_choice_future is not None
            and not cls._pending_choice_future.done()
        ):
            cls._pending_choice_future.cancel()
        cls._pending_choice_future = None
        cls._choice_options = []
