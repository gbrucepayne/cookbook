# gunicorn.conf.py
import json
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Binding and worker settings
port = os.getenv('PORT', '5001')
bind = f"0.0.0.0:{port}"
workers = 3
timeout = 60

# Formatter for internal logs
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat() + "Z",
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': { '()': JsonFormatter },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'formatter': 'json',
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
    'loggers': {
        'app': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'alembic': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
        },
        'gunicorn.error': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
            # 'qualname': 'gunicorn.error',
        },
        'gunicorn.access': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
            # 'qualname': 'gunicorn.access',
        }
    }
}


def on_starting(server):
    """Fires exactly once when the master Gunicorn process starts up.
    Before any of the worker processes fork.
    """
    logger = logging.getLogger("app")
    logger.info("Cookbook Web Server initialized in production mode")
