# log_helper/logger.py
import logging
import sys
import contextvars
import json

# === Context variables shared across app ===
current_thread_id = contextvars.ContextVar("current_thread_id", default=None)
current_user_email = contextvars.ContextVar("current_user_email", default=None)

LOG_NAME = "bdf_chatbot"

class ContextAwareFilter(logging.Filter):
    """
    Inject Chainlit or manually propagated context (thread_id, user_email)
    into every log record automatically.
    """
    def filter(self, record):
        try:
            import chainlit as cl
            ctx = None
            try:
                ctx = cl.context.current()
            except Exception:
                pass

            # Prefer contextvars first (manual propagation)
            record.thread_id = current_thread_id.get()
            record.user_email = current_user_email.get()

            # If still missing, try live Chainlit context (inside @cl handlers)
            if not record.thread_id and ctx is not None:
                record.thread_id = getattr(ctx, "id", None)
            if not record.user_email:
                user = cl.user_session.get("user")
                if user:
                    record.user_email = getattr(user, "identifier", None)
        except Exception:
            record.thread_id = record.thread_id if hasattr(record, "thread_id") else None
            record.user_email = record.user_email if hasattr(record, "user_email") else None
        return True


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs structured JSON logs with metadata and message separated.
    This prevents multi-line splitting in CloudWatch and makes logs filterable by fields.
    """
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "thread_id": getattr(record, 'thread_id', None),
            "user_email": getattr(record, 'user_email', None),
            "location": f"{record.filename}:{record.lineno}",
            "message": record.getMessage()
        }
        
        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def get_logger():
    logger = logging.getLogger(LOG_NAME)
    logger.propagate = False

    # Avoid duplicate handlers in hot reload / Chainlit dev mode
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)

    # Use JSON formatter to prevent multi-line splitting and enable field-based filtering
    formatter = JSONFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextAwareFilter())

    logger.addHandler(handler)
    return logger
