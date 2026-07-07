# ----- library import-----
import logging


class PollingEndpointAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # ----- exclude all long-polling noise from the console logs -----
        log_msg = record.getMessage()
        if "/api/otp/status" in log_msg or "/api/otp/choice/status" in log_msg:
            return False
        return True
