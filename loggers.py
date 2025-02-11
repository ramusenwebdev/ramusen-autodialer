import logging
import os

log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# File log untuk masing-masing logger
app_log_filename = os.path.join(log_dir, 'application.log')
autodialer_log_filename = os.path.join(log_dir, 'autodialer.log')
ranablast_log_filename = os.path.join(log_dir, 'ranablast.log')

# Logger untuk aplikasi (application)
app_logger = logging.getLogger('application')
app_logger.setLevel(logging.DEBUG)  # Ubah level log sesuai kebutuhan

app_file_handler = logging.FileHandler(app_log_filename)
app_stream_handler = logging.StreamHandler()

app_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app_file_handler.setFormatter(app_formatter)
app_stream_handler.setFormatter(app_formatter)

app_logger.addHandler(app_file_handler)
app_logger.addHandler(app_stream_handler)

# Logger untuk autodialer (autodialer)
autodialer_logger = logging.getLogger('autodialer')
autodialer_logger.setLevel(logging.DEBUG)  # Ubah level log sesuai kebutuhan

autodialer_file_handler = logging.FileHandler(autodialer_log_filename)
autodialer_stream_handler = logging.StreamHandler()

autodialer_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
autodialer_file_handler.setFormatter(autodialer_formatter)
autodialer_stream_handler.setFormatter(autodialer_formatter)

autodialer_logger.addHandler(autodialer_file_handler)
autodialer_logger.addHandler(autodialer_stream_handler)


# Logger untuk ranablast (ranablast)
ranablast_logger = logging.getLogger('ranablast')
ranablast_logger.setLevel(logging.DEBUG)  # Ubah level log sesuai kebutuhan

ranablast_file_handler = logging.FileHandler(ranablast_log_filename)
ranablast_stream_handler = logging.StreamHandler()

ranablast_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ranablast_file_handler.setFormatter(ranablast_formatter)
ranablast_stream_handler.setFormatter(ranablast_formatter)

ranablast_logger.addHandler(ranablast_file_handler)
ranablast_logger.addHandler(ranablast_stream_handler)